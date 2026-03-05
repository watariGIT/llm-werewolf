import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import REQUIRED_PLAYER_COUNT
from llm_werewolf.domain.value_objects import Role
from llm_werewolf.engine.llm_config import LLMConfig, load_gm_config, load_llm_config, load_prompt_config
from llm_werewolf.engine.metrics import estimate_cost
from llm_werewolf.session import (
    GameSessionStore,
    GameStep,
    InteractiveSession,
    InteractiveSessionStore,
    SessionLimitExceeded,
    advance_from_execution_result,
    advance_to_discussion,
    get_night_action_candidates,
    get_night_action_type,
    handle_auto_vote,
    handle_night_action,
    handle_user_discuss,
    handle_user_vote,
    skip_to_vote,
)

load_dotenv()

_log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level_name, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# --llm-debug: LLM プロンプト・レスポンス・トークン使用量を標準出力に表示
if os.environ.get("LLM_DEBUG", "").strip():
    logging.getLogger("llm_werewolf.engine.llm_provider").setLevel(logging.DEBUG)
    logging.getLogger("llm_werewolf.engine.game_master").setLevel(logging.DEBUG)
    for _handler in logging.root.handlers:
        _handler.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

_random_mode = bool(os.environ.get("RANDOM_MODE", "").strip())

llm_config: LLMConfig | None = None
gm_config: LLMConfig | None = None

if _random_mode:
    logger.info("=== LLM人狼 ランダムモード ===")
    logger.info("  RandomActionProvider を使用（OPENAI_API_KEY 不要）")
    logger.info("==============================")
else:
    try:
        llm_config = load_llm_config()
    except ValueError as e:
        logger.error("プレイヤーAI設定の読み込みに失敗しました: %s", e)
        sys.exit(1)

    try:
        gm_config = load_gm_config()
    except ValueError as e:
        logger.error("GM-AI設定の読み込みに失敗しました: %s", e)
        sys.exit(1)

try:
    prompt_config = load_prompt_config()
except ValueError as e:
    logger.error("プロンプト設定の読み込みに失敗しました: %s", e)
    sys.exit(1)

if not _random_mode and llm_config is not None and gm_config is not None:
    logger.info("=== LLM人狼 設定情報 ===")
    logger.info("  プレイヤーAI: model=%s, temperature=%s", llm_config.model_name, llm_config.temperature)
    logger.info("  GM-AI:       model=%s, temperature=%s", gm_config.model_name, gm_config.temperature)
    logger.info(
        "  発言ログ上限: player=%d, gm=%d", prompt_config.max_recent_statements, prompt_config.gm_max_recent_statements
    )
    logger.info("  LLM_DEBUG=%s, LOG_LEVEL=%s", bool(os.environ.get("LLM_DEBUG", "").strip()), _log_level_name)
    logger.info("  OPENAI_API_KEY: 設定済み")
    logger.info("========================")

app = FastAPI(title="LLM人狼")


@app.exception_handler(SessionLimitExceeded)
async def session_limit_exceeded_handler(request: Request, exc: SessionLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429, content={"detail": "セッション数が上限に達しました。しばらくしてから再試行してください。"}
    )


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

game_store = GameSessionStore()
interactive_store = InteractiveSessionStore()

MAX_PLAYER_NAME_LENGTH = 50
MAX_MESSAGE_LENGTH = 500

_DAY_HEADER_PREFIX = "--- Day "
_NIGHT_HEADER_PREFIX = "--- Night "
_SPEECH_PREFIX = "[発言] "
_EXECUTION_PREFIX = "[処刑] "
_VOTE_PREFIX = "[投票] "
_ATTACK_PREFIX = "[襲撃] "
_THINKING_PREFIX = "[思考] "


def _collect_debug_info(session: InteractiveSession) -> dict[str, Any]:
    """デバッグモード用のAI内部情報を収集する。"""
    debug_players: dict[str, dict[str, Any]] = {}
    for p in session.game.players:
        if p.name == session.human_player_name:
            continue
        provider = session.providers.get(p.name)
        if provider is None:
            continue
        # MetricsCollectingProvider があれば累計、なければ last_ を使用
        metrics = session.player_metrics.get(p.name)
        if metrics is not None:
            input_tokens = metrics.total_input_tokens
            output_tokens = metrics.total_output_tokens
            cache_read = metrics.total_cache_read_input_tokens
        else:
            input_tokens = getattr(provider, "last_input_tokens", 0)
            output_tokens = getattr(provider, "last_output_tokens", 0)
            cache_read = getattr(provider, "last_cache_read_input_tokens", 0)
        model_name = llm_config.model_name if llm_config is not None else ""
        cost = estimate_cost(model_name, input_tokens, output_tokens, cache_read)
        debug_players[p.name] = {
            "role": p.role.value,
            "personality": getattr(provider, "_personality", ""),
            "last_thinking": getattr(provider, "last_thinking", ""),
            "last_input_tokens": input_tokens,
            "last_output_tokens": output_tokens,
            "last_cache_read_input_tokens": cache_read,
            "last_cost": f"${cost:.6f}" if cost is not None else "N/A",
        }
    result: dict[str, Any] = {"players": debug_players}

    gm = session.gm_provider
    gm_input = 0
    gm_output = 0
    gm_cache = 0
    gm_cost: float | None = None
    if gm is not None:
        gm_input = gm.last_input_tokens
        gm_output = gm.last_output_tokens
        gm_cache = gm.last_cache_read_input_tokens
        gm_model_name = gm_config.model_name if gm_config is not None else ""
        gm_cost = estimate_cost(gm_model_name, gm_input, gm_output, gm_cache)
        result["gm"] = {
            "last_input_tokens": gm_input,
            "last_output_tokens": gm_output,
            "last_cache_read_input_tokens": gm_cache,
            "last_cost": f"${gm_cost:.6f}" if gm_cost is not None else "N/A",
        }

    # 合計の計算
    total_input = sum(pi["last_input_tokens"] for pi in debug_players.values())
    total_output = sum(pi["last_output_tokens"] for pi in debug_players.values())
    total_cache = sum(pi["last_cache_read_input_tokens"] for pi in debug_players.values())
    total_cost_usd = 0.0
    cost_available = True
    for pi in debug_players.values():
        c = estimate_cost(
            model_name, pi["last_input_tokens"], pi["last_output_tokens"], pi["last_cache_read_input_tokens"]
        )
        if c is not None:
            total_cost_usd += c
        else:
            cost_available = False
    if gm is not None:
        total_input += gm_input
        total_output += gm_output
        total_cache += gm_cache
        if gm_cost is not None:
            total_cost_usd += gm_cost
        else:
            cost_available = False
    result["totals"] = {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cache_read_input_tokens": total_cache,
        "cost": f"${total_cost_usd:.6f}" if cost_available else "N/A",
    }

    return result


def _format_cost(provider: object) -> str:
    """プロバイダーのトークン情報からコスト文字列を生成する。"""
    input_tokens = getattr(provider, "last_input_tokens", 0)
    output_tokens = getattr(provider, "last_output_tokens", 0)
    cache_read = getattr(provider, "last_cache_read_input_tokens", 0)
    model_name = llm_config.model_name if llm_config is not None else ""
    cost = estimate_cost(model_name, input_tokens, output_tokens, cache_read)
    return f"${cost:.6f}" if cost is not None else "N/A"


def _extract_thinking_map(game: GameState) -> dict[str, list[str]]:
    """ゲームログから発言順に対応する思考ログを抽出する。

    Returns:
        {player_name: [thinking_text, ...]} の辞書。議論の発言順に対応。
    """
    thinking_map: dict[str, list[str]] = {}
    current_day = 0
    for entry in game.log:
        if entry.startswith(_DAY_HEADER_PREFIX):
            parts = entry[len(_DAY_HEADER_PREFIX) :].split(" ", 1)
            try:
                current_day = int(parts[0])
            except (ValueError, IndexError):
                pass
        elif entry.startswith(_THINKING_PREFIX) and current_day == game.day:
            # "[思考] PlayerName: thinking text"
            rest = entry[len(_THINKING_PREFIX) :]
            if ": " in rest:
                name, text = rest.split(": ", 1)
                thinking_map.setdefault(name, []).append(text)
    return thinking_map


def _extract_vote_thinking(game: GameState) -> dict[str, str]:
    """当日の投票フェーズの思考を抽出する。

    ゲームログの投票フェーズでは [思考] が先に記録され、その後 [投票] が記録される。
    当日の [投票] ログより前にある [思考] のうち、[発言] 以降のものを投票思考として返す。

    Returns:
        {player_name: thinking_text} の辞書
    """
    vote_thinking: dict[str, str] = {}
    current_day = 0
    in_vote_phase = False
    pending_thinking: dict[str, str] = {}

    for entry in game.log:
        if entry.startswith(_DAY_HEADER_PREFIX):
            parts = entry[len(_DAY_HEADER_PREFIX) :].split(" ", 1)
            try:
                current_day = int(parts[0])
            except (ValueError, IndexError):
                pass
            in_vote_phase = False
            pending_thinking = {}
        elif entry.startswith(_NIGHT_HEADER_PREFIX):
            in_vote_phase = False
            pending_thinking = {}
        elif current_day == game.day:
            if entry.startswith(_VOTE_PREFIX):
                # 投票ログに到達 → pending_thinking を確定
                in_vote_phase = True
                if pending_thinking:
                    vote_thinking.update(pending_thinking)
                    pending_thinking = {}
            elif entry.startswith(_THINKING_PREFIX) and not in_vote_phase:
                rest = entry[len(_THINKING_PREFIX) :]
                if ": " in rest:
                    name, text = rest.split(": ", 1)
                    # 最後の思考を保持（議論中の思考は発言で上書きされる）
                    pending_thinking[name] = text
            elif entry.startswith(_SPEECH_PREFIX):
                # 発言ログ → 議論中の思考をクリアして投票思考の開始を待つ
                speaker = entry[len(_SPEECH_PREFIX) :].split(": ", 1)[0]
                pending_thinking.pop(speaker, None)

    return vote_thinking


def _extract_night_thinking(game: GameState, night_number: int) -> dict[str, str]:
    """指定された夜フェーズの思考を抽出する。

    Returns:
        {player_name: thinking_text} の辞書
    """
    night_thinking: dict[str, str] = {}
    in_target_night = False

    for entry in game.log:
        if entry.startswith(_NIGHT_HEADER_PREFIX):
            parts = entry[len(_NIGHT_HEADER_PREFIX) :].split(" ", 1)
            try:
                night_num = int(parts[0])
            except (ValueError, IndexError):
                night_num = -1
            in_target_night = night_num == night_number
        elif entry.startswith(_DAY_HEADER_PREFIX):
            if in_target_night:
                break  # 対象の夜が終わった
        elif in_target_night and entry.startswith(_THINKING_PREFIX):
            rest = entry[len(_THINKING_PREFIX) :]
            if ": " in rest:
                name, text = rest.split(": ", 1)
                night_thinking[name] = text

    return night_thinking


def _extract_thinking_by_day(game: GameState) -> dict[int, dict[str, Any]]:
    """全日の思考ログを日別に抽出する。

    議論中の思考は [発言] が続いた場合のみ discussion に確定する。
    [発言] なしで [投票] が来た場合は vote に分類される。

    Returns:
        {day: {"discussion": {name: [text, ...]}, "vote": {name: text}, "night": {name: text}}}
    """
    result: dict[int, dict[str, Any]] = {}
    current_day = 0
    current_night = 0
    in_night = False
    in_vote_phase = False
    # pending_thinking: 思考を一時保持し、[発言] or [投票] で確定先を決める
    pending_thinking: dict[str, str] = {}

    for entry in game.log:
        if entry.startswith(_DAY_HEADER_PREFIX):
            parts = entry[len(_DAY_HEADER_PREFIX) :].split(" ", 1)
            try:
                current_day = int(parts[0])
            except (ValueError, IndexError):
                pass
            in_night = False
            in_vote_phase = False
            pending_thinking = {}
            if current_day not in result:
                result[current_day] = {"discussion": {}, "vote": {}, "night": {}}
        elif entry.startswith(_NIGHT_HEADER_PREFIX):
            parts = entry[len(_NIGHT_HEADER_PREFIX) :].split(" ", 1)
            try:
                current_night = int(parts[0])
            except (ValueError, IndexError):
                pass
            in_night = True
            in_vote_phase = False
            pending_thinking = {}
        elif in_night:
            if entry.startswith(_THINKING_PREFIX):
                rest = entry[len(_THINKING_PREFIX) :]
                if ": " in rest:
                    name, text = rest.split(": ", 1)
                    day_data = result.get(current_night, {"discussion": {}, "vote": {}, "night": {}})
                    result[current_night] = day_data
                    day_data["night"][name] = text
        elif current_day > 0:
            if entry.startswith(_VOTE_PREFIX):
                in_vote_phase = True
                if pending_thinking:
                    day_data = result[current_day]
                    day_data["vote"].update(pending_thinking)
                    pending_thinking = {}
            elif entry.startswith(_THINKING_PREFIX) and not in_vote_phase:
                rest = entry[len(_THINKING_PREFIX) :]
                if ": " in rest:
                    name, text = rest.split(": ", 1)
                    pending_thinking[name] = text
            elif entry.startswith(_SPEECH_PREFIX):
                speaker = entry[len(_SPEECH_PREFIX) :].split(": ", 1)[0]
                # 発言が来たので、その話者の pending_thinking を discussion に確定
                if speaker in pending_thinking:
                    day_data = result[current_day]
                    day_data["discussion"].setdefault(speaker, []).append(pending_thinking.pop(speaker))

    return result


def _extract_discussions_by_day(game: GameState) -> dict[int, list[str]]:
    """ゲームログから日ごとの発言を抽出する。

    Returns:
        {day: ["PlayerName: message", ...]} の辞書
    """
    discussions: dict[int, list[str]] = {}
    current_day = 0
    for entry in game.log:
        if entry.startswith(_DAY_HEADER_PREFIX):
            # "--- Day 1 （昼フェーズ） ---" から日数を抽出
            parts = entry[len(_DAY_HEADER_PREFIX) :].split(" ", 1)
            try:
                current_day = int(parts[0])
            except (ValueError, IndexError):
                pass
        elif entry.startswith(_SPEECH_PREFIX) and current_day > 0:
            msg = entry[len(_SPEECH_PREFIX) :]
            if current_day not in discussions:
                discussions[current_day] = []
            discussions[current_day].append(msg)
    return discussions


def _extract_current_execution_logs(game: GameState) -> list[str]:
    """ゲームログから当日の処刑ログを抽出する。

    Returns:
        "[処刑] " プレフィックスを除去した処刑ログ文字列のリスト
    """
    execution_logs: list[str] = []
    current_day = 0
    for entry in game.log:
        if entry.startswith(_DAY_HEADER_PREFIX):
            parts = entry[len(_DAY_HEADER_PREFIX) :].split(" ", 1)
            try:
                current_day = int(parts[0])
            except (ValueError, IndexError):
                pass
        elif entry.startswith(_EXECUTION_PREFIX) and current_day == game.day:
            execution_logs.append(entry[len(_EXECUTION_PREFIX) :])
    return execution_logs


def _extract_events_by_day(game: GameState) -> dict[int, list[tuple[str, str]]]:
    """ゲームログから日ごとの公開イベント（投票・処刑・襲撃）を抽出する。

    Returns:
        {day: [(event_type, text), ...]} の辞書。
        event_type は "vote", "execution", "attack" のいずれか。
    """
    events: dict[int, list[tuple[str, str]]] = {}
    current_day = 0
    for entry in game.log:
        if entry.startswith(_DAY_HEADER_PREFIX):
            parts = entry[len(_DAY_HEADER_PREFIX) :].split(" ", 1)
            try:
                current_day = int(parts[0])
            except (ValueError, IndexError):
                pass
        elif entry.startswith(_NIGHT_HEADER_PREFIX):
            # Night N は Day N の続き（同じ day に紐づける）
            pass
        elif entry.startswith(_VOTE_PREFIX) and current_day > 0:
            events.setdefault(current_day, []).append(("vote", entry[len(_VOTE_PREFIX) :]))
        elif entry.startswith(_EXECUTION_PREFIX) and current_day > 0:
            events.setdefault(current_day, []).append(("execution", entry[len(_EXECUTION_PREFIX) :]))
        elif entry.startswith(_ATTACK_PREFIX) and current_day > 0:
            events.setdefault(current_day, []).append(("attack", entry[len(_ATTACK_PREFIX) :]))
    return events


class CreateGameRequest(BaseModel):
    player_names: list[str]

    @field_validator("player_names")
    @classmethod
    def validate_player_names(cls, v: list[str]) -> list[str]:
        if len(v) != REQUIRED_PLAYER_COUNT:
            raise ValueError(f"player_names must contain exactly {REQUIRED_PLAYER_COUNT} names")
        for name in v:
            if not name or not name.strip():
                raise ValueError("player name must not be empty")
            if len(name) > MAX_PLAYER_NAME_LENGTH:
                raise ValueError(f"player name must be at most {MAX_PLAYER_NAME_LENGTH} characters")
        if len(set(v)) != len(v):
            raise ValueError("player_names must be unique")
        return v


def _serialize_player(player: Player) -> dict[str, Any]:
    return {"name": player.name, "role": player.role.value, "status": player.status.value}


def _serialize_game(game_id: str, game: GameState) -> dict[str, Any]:
    return {
        "game_id": game_id,
        "day": game.day,
        "phase": game.phase.value,
        "players": [_serialize_player(p) for p in game.players],
        "log": list(game.log),
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


# --- 一括実行 API ---


@app.post("/games")
async def create_game(body: CreateGameRequest) -> JSONResponse:
    """新規ゲームを作成し、一括実行して結果を返す。"""
    game_id, game = game_store.create(body.player_names, config=llm_config)
    return JSONResponse(content=_serialize_game(game_id, game), status_code=201)


@app.get("/games")
async def list_games() -> JSONResponse:
    """全セッション一覧を返す。"""
    sessions = game_store.list_sessions()
    return JSONResponse(
        content={
            "games": [
                {
                    "game_id": game_id,
                    "day": game.day,
                    "phase": game.phase.value,
                    "player_count": len(game.players),
                    "alive_count": len(game.alive_players),
                }
                for game_id, game in sessions.items()
            ]
        }
    )


@app.get("/games/{game_id}")
async def get_game(game_id: str) -> JSONResponse:
    """ゲーム状態を取得する。"""
    game = game_store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return JSONResponse(content=_serialize_game(game_id, game))


# --- インタラクティブ Web UI ---


ROLE_MAP: dict[str, Role] = {
    "villager": Role.VILLAGER,
    "seer": Role.SEER,
    "werewolf": Role.WEREWOLF,
    "knight": Role.KNIGHT,
    "medium": Role.MEDIUM,
    "madman": Role.MADMAN,
}


@app.post("/play")
async def create_interactive_game(player_name: str = Form(...), role: str = Form("random")) -> RedirectResponse:
    """インタラクティブゲームを作成してリダイレクトする。"""
    name = player_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名前を入力してください")
    if len(name) > MAX_PLAYER_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"名前は{MAX_PLAYER_NAME_LENGTH}文字以内で入力してください")

    if role != "random" and role not in ROLE_MAP:
        raise HTTPException(status_code=400, detail="無効な役職です")
    selected_role = ROLE_MAP.get(role) if role != "random" else None
    session = interactive_store.create(name, role=selected_role, config=llm_config)
    return RedirectResponse(url=f"/play/{session.game_id}", status_code=303)


@app.get("/play/{game_id}", response_class=HTMLResponse)
async def play_game(request: Request, game_id: str, debug: str = "") -> HTMLResponse:
    """ゲーム画面を表示する。"""
    session = interactive_store.get(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")

    debug_mode = debug == "1"

    human_player = session.game.find_player(session.human_player_name)
    human_is_alive = human_player is not None and human_player.is_alive

    # display_order に基づく表示順ソート用インデックス
    display_index = {name: i for i, name in enumerate(session.display_order)}

    # 投票候補（自分以外の生存者、display_order 順）
    vote_candidates = sorted(
        [p for p in session.game.alive_players if p.name != session.human_player_name],
        key=lambda p: display_index.get(p.name, 999),
    )

    # 夜行動のコンテキスト（display_order 順）
    night_action_type = get_night_action_type(session) if session.step == GameStep.NIGHT_ACTION else None
    night_action_candidates_raw = get_night_action_candidates(session) if session.step == GameStep.NIGHT_ACTION else []
    night_action_candidates = sorted(night_action_candidates_raw, key=lambda p: display_index.get(p.name, 999))

    # display_order に基づくプレイヤー表示順（ゲーム中固定）
    name_to_player = {p.name: p for p in session.game.players}
    ordered_players = [name_to_player[name] for name in session.display_order if name in name_to_player]

    # 過去日の議論ログ（当日より前の日のみ）
    all_discussions = _extract_discussions_by_day(session.game)
    past_discussions = {day: msgs for day, msgs in sorted(all_discussions.items()) if day < session.game.day}

    # 過去日の公開イベント（投票・処刑・襲撃）
    all_events = _extract_events_by_day(session.game)
    past_events = {day: evts for day, evts in sorted(all_events.items()) if day < session.game.day}

    # 過去日の一覧（議論とイベントの両方をカバー）
    past_days = sorted(set(past_discussions.keys()) | set(past_events.keys()))

    # 当日の処刑ログ
    current_execution_logs = _extract_current_execution_logs(session.game)

    # 人狼の仲間情報（人間プレイヤーが人狼の場合）
    werewolf_allies: list[Player] = []
    if human_player and human_player.role == Role.WEREWOLF:
        werewolf_allies = [p for p in session.game.alive_werewolves if p.name != session.human_player_name]

    context: dict[str, Any] = {
        "session": session,
        "game": session.game,
        "step": session.step.value,
        "human_player": human_player,
        "human_is_alive": human_is_alive,
        "vote_candidates": vote_candidates,
        "night_action_type": night_action_type,
        "night_action_candidates": night_action_candidates,
        "game_id": game_id,
        "ordered_players": ordered_players,
        "current_execution_logs": current_execution_logs,
        "past_discussions": past_discussions,
        "past_events": past_events,
        "past_days": past_days,
        "werewolf_allies": werewolf_allies,
        "debug_mode": debug_mode,
    }
    if debug_mode:
        context["debug_info"] = _collect_debug_info(session)
        context["thinking_map"] = _extract_thinking_map(session.game)
        context["vote_thinking"] = _extract_vote_thinking(session.game)
        context["night_thinking"] = _extract_night_thinking(session.game, session.game.day - 1)
        all_thinking = _extract_thinking_by_day(session.game)
        context["past_thinking"] = {day: data for day, data in all_thinking.items() if day < session.game.day}

    return templates.TemplateResponse(request, "game.html", context)


@app.post("/play/{game_id}/next")
async def advance_game(game_id: str) -> RedirectResponse:
    """次のステップへ進む。"""
    session = interactive_store.get(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")

    human_player = session.game.find_player(session.human_player_name)
    human_is_alive = human_player is not None and human_player.is_alive

    advanced = False
    if session.step == GameStep.ROLE_REVEAL:
        advance_to_discussion(session)
        advanced = True
    elif session.step == GameStep.DISCUSSION and not human_is_alive:
        skip_to_vote(session)
        advanced = True
    elif session.step == GameStep.VOTE and not human_is_alive:
        handle_auto_vote(session)
        advanced = True
    elif session.step == GameStep.EXECUTION_RESULT:
        advance_from_execution_result(session)
        advanced = True
    elif session.step == GameStep.NIGHT_RESULT:
        advance_to_discussion(session)
        advanced = True

    if not advanced:
        raise HTTPException(status_code=400, detail="このステップでは /next を使用できません")

    interactive_store.save(session)
    return RedirectResponse(url=f"/play/{game_id}", status_code=303)


@app.post("/play/{game_id}/discuss")
async def submit_discussion(game_id: str, message: str = Form("")) -> RedirectResponse:
    """ユーザー発言を送信する。"""
    session = interactive_store.get(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")

    if session.step != GameStep.DISCUSSION:
        raise HTTPException(status_code=400, detail="Invalid step")

    text = message.strip() or "..."
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH]
    handle_user_discuss(session, text)
    interactive_store.save(session)
    return RedirectResponse(url=f"/play/{game_id}", status_code=303)


@app.post("/play/{game_id}/night-action")
async def submit_night_action(game_id: str, target: str = Form(...)) -> RedirectResponse:
    """ユーザーの夜行動（占い or 襲撃対象）を送信する。"""
    session = interactive_store.get(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")

    if session.step != GameStep.NIGHT_ACTION:
        raise HTTPException(status_code=400, detail="Invalid step")

    # バリデーション: 対象が候補に含まれているか
    candidates = get_night_action_candidates(session)
    candidate_names = {p.name for p in candidates}
    if target not in candidate_names:
        raise HTTPException(status_code=400, detail="無効な対象です")

    handle_night_action(session, target)
    interactive_store.save(session)
    return RedirectResponse(url=f"/play/{game_id}", status_code=303)


@app.get("/play/{game_id}/export")
async def export_game_log(game_id: str) -> JSONResponse:
    """ゲームログを JSON 形式でエクスポートする。"""
    session = interactive_store.get(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")

    return JSONResponse(
        content={"log": list(session.game.log)},
        headers={"Content-Disposition": f'attachment; filename="game-log-{game_id}.json"'},
    )


@app.post("/play/{game_id}/vote")
async def submit_vote(game_id: str, target: str = Form(...)) -> RedirectResponse:
    """ユーザー投票を送信する。"""
    session = interactive_store.get(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")

    if session.step != GameStep.VOTE:
        raise HTTPException(status_code=400, detail="Invalid step")

    # バリデーション: 自分には投票不可、死亡者には投票不可
    alive_names = {p.name for p in session.game.alive_players}
    if target == session.human_player_name:
        raise HTTPException(status_code=400, detail="自分には投票できません")
    if target not in alive_names:
        raise HTTPException(status_code=400, detail="無効な投票先です")

    handle_user_vote(session, target)
    interactive_store.save(session)
    return RedirectResponse(url=f"/play/{game_id}", status_code=303)


# --- SSE (Server-Sent Events) エンドポイント ---


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """SSE イベント文字列を生成する。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _get_session_or_raise(game_id: str) -> InteractiveSession:
    """セッションを取得する。存在しない場合は HTTPException を送出する。"""
    session = interactive_store.get(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return session


def _make_sse_callbacks(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue[dict[str, Any] | None],
    session: InteractiveSession | None = None,
    debug_mode: bool = False,
) -> tuple[Any, Any, Any]:
    """SSE 用の on_progress / on_message / on_token_chunk コールバックを生成する。

    コールバックはワーカースレッドから呼ばれるため loop.call_soon_threadsafe を使用する。
    debug_mode が有効な場合、on_message 後に debug イベントを送信する。
    """

    def on_progress(player_name: str, action_type: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"event": "progress", "player": player_name, "action": action_type})

    def on_message(player_name: str, text: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"event": "message", "player": player_name, "text": text})
        if debug_mode and session is not None:
            provider = session.providers.get(player_name)
            if provider is not None:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "event": "debug",
                        "player": player_name,
                        "thinking": getattr(provider, "last_thinking", ""),
                        "input_tokens": getattr(provider, "last_input_tokens", 0),
                        "output_tokens": getattr(provider, "last_output_tokens", 0),
                        "cache_read_tokens": getattr(provider, "last_cache_read_input_tokens", 0),
                        "cost": _format_cost(provider),
                    },
                )

    def on_token_chunk(player_name: str, chunk: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"event": "token", "player": player_name, "chunk": chunk})

    return on_progress, on_message, on_token_chunk


async def _sse_stream(queue: asyncio.Queue[dict[str, Any] | None]) -> AsyncGenerator[str, None]:
    """SSE イベントキューからストリームを生成する。None で終了。"""
    while True:
        item = await queue.get()
        if item is None:
            yield _sse_event("done", {})
            break
        event_type = item.pop("event")
        yield _sse_event(event_type, item)


@app.post("/play/{game_id}/sse/next")
async def sse_advance_game(request: Request, game_id: str) -> StreamingResponse:
    """次のステップへ進む（SSE ストリーム版）。"""
    session = _get_session_or_raise(game_id)
    debug_mode = request.query_params.get("debug") == "1"

    human_player = session.game.find_player(session.human_player_name)
    human_is_alive = human_player is not None and human_player.is_alive

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    on_progress, on_message, on_token_chunk = _make_sse_callbacks(loop, queue, session, debug_mode)

    def process() -> None:
        try:
            if session.step == GameStep.ROLE_REVEAL:
                advance_to_discussion(
                    session, on_progress=on_progress, on_message=on_message, on_token_chunk=on_token_chunk
                )
            elif session.step == GameStep.DISCUSSION and not human_is_alive:
                skip_to_vote(session, on_progress=on_progress, on_message=on_message, on_token_chunk=on_token_chunk)
            elif session.step == GameStep.VOTE and not human_is_alive:
                handle_auto_vote(session, on_progress=on_progress)
            elif session.step == GameStep.EXECUTION_RESULT:
                advance_from_execution_result(session, on_progress=on_progress)
            elif session.step == GameStep.NIGHT_RESULT:
                advance_to_discussion(
                    session, on_progress=on_progress, on_message=on_message, on_token_chunk=on_token_chunk
                )
            interactive_store.save(session)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, process)
    return StreamingResponse(_sse_stream(queue), media_type="text/event-stream")


@app.post("/play/{game_id}/sse/discuss")
async def sse_submit_discussion(request: Request, game_id: str, message: str = Form("")) -> StreamingResponse:
    """ユーザー発言を送信する（SSE ストリーム版）。"""
    session = _get_session_or_raise(game_id)
    debug_mode = request.query_params.get("debug") == "1"

    if session.step != GameStep.DISCUSSION:
        raise HTTPException(status_code=400, detail="Invalid step")

    text = message.strip() or "..."
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH]

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    on_progress, on_message, on_token_chunk = _make_sse_callbacks(loop, queue, session, debug_mode)

    def process() -> None:
        try:
            handle_user_discuss(
                session, text, on_progress=on_progress, on_message=on_message, on_token_chunk=on_token_chunk
            )
            interactive_store.save(session)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, process)
    return StreamingResponse(_sse_stream(queue), media_type="text/event-stream")


@app.post("/play/{game_id}/sse/vote")
async def sse_submit_vote(request: Request, game_id: str, target: str = Form(...)) -> StreamingResponse:
    """ユーザー投票を送信する（SSE ストリーム版）。"""
    session = _get_session_or_raise(game_id)
    debug_mode = request.query_params.get("debug") == "1"

    if session.step != GameStep.VOTE:
        raise HTTPException(status_code=400, detail="Invalid step")

    alive_names = {p.name for p in session.game.alive_players}
    if target == session.human_player_name:
        raise HTTPException(status_code=400, detail="自分には投票できません")
    if target not in alive_names:
        raise HTTPException(status_code=400, detail="無効な投票先です")

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    on_progress, _, _ = _make_sse_callbacks(loop, queue, session, debug_mode)

    def process() -> None:
        try:
            handle_user_vote(session, target, on_progress=on_progress)
            interactive_store.save(session)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, process)
    return StreamingResponse(_sse_stream(queue), media_type="text/event-stream")


@app.post("/play/{game_id}/sse/night-action")
async def sse_submit_night_action(request: Request, game_id: str, target: str = Form(...)) -> StreamingResponse:
    """ユーザーの夜行動を送信する（SSE ストリーム版）。"""
    session = _get_session_or_raise(game_id)
    debug_mode = request.query_params.get("debug") == "1"

    if session.step != GameStep.NIGHT_ACTION:
        raise HTTPException(status_code=400, detail="Invalid step")

    candidates = get_night_action_candidates(session)
    candidate_names = {p.name for p in candidates}
    if target not in candidate_names:
        raise HTTPException(status_code=400, detail="無効な対象です")

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    on_progress, _, _ = _make_sse_callbacks(loop, queue, session, debug_mode)

    def process() -> None:
        try:
            handle_night_action(session, target, on_progress=on_progress)
            interactive_store.save(session)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, process)
    return StreamingResponse(_sse_stream(queue), media_type="text/event-stream")
