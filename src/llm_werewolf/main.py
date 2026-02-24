import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import REQUIRED_PLAYER_COUNT
from llm_werewolf.domain.value_objects import Role
from llm_werewolf.engine.llm_config import load_llm_config
from llm_werewolf.session import (
    GameSessionStore,
    GameStep,
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

try:
    llm_config = load_llm_config()
except ValueError as e:
    logger.error(str(e))
    sys.exit(1)

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
async def play_game(request: Request, game_id: str) -> HTMLResponse:
    """ゲーム画面を表示する。"""
    session = interactive_store.get(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")

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

    return templates.TemplateResponse(
        request,
        "game.html",
        {
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
        },
    )


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
