from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import REQUIRED_PLAYER_COUNT
from llm_werewolf.session import (
    GameSessionStore,
    GameStep,
    InteractiveSession,
    InteractiveSessionStore,
    advance_to_discussion,
    execute_night_phase,
    handle_auto_vote,
    handle_user_discuss,
    handle_user_vote,
    skip_to_vote,
)

app = FastAPI(title="LLM人狼")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

game_store = GameSessionStore()
interactive_store = InteractiveSessionStore()

MAX_PLAYER_NAME_LENGTH = 50


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
    game_id, game = game_store.create(body.player_names)
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


def _get_human_player(session: InteractiveSession) -> Player | None:
    """セッションからユーザープレイヤーを取得する。"""
    for p in session.game.players:
        if p.name == session.human_player_name:
            return p
    return None


@app.post("/play")
async def create_interactive_game(player_name: str = Form(...)) -> RedirectResponse:
    """インタラクティブゲームを作成してリダイレクトする。"""
    name = player_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名前を入力してください")
    if len(name) > MAX_PLAYER_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"名前は{MAX_PLAYER_NAME_LENGTH}文字以内で入力してください")

    session = interactive_store.create(name)
    return RedirectResponse(url=f"/play/{session.game_id}", status_code=303)


@app.get("/play/{game_id}", response_class=HTMLResponse)
async def play_game(request: Request, game_id: str) -> HTMLResponse:
    """ゲーム画面を表示する。"""
    session = interactive_store.get(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")

    human_player = _get_human_player(session)
    human_is_alive = human_player is not None and human_player.is_alive

    # 投票候補（自分以外の生存者）
    vote_candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]

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
            "game_id": game_id,
        },
    )


@app.post("/play/{game_id}/next")
async def advance_game(game_id: str) -> RedirectResponse:
    """次のステップへ進む。"""
    session = interactive_store.get(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")

    human_player = _get_human_player(session)
    human_is_alive = human_player is not None and human_player.is_alive

    if session.step == GameStep.ROLE_REVEAL:
        advance_to_discussion(session)
    elif session.step == GameStep.DISCUSSION and not human_is_alive:
        skip_to_vote(session)
    elif session.step == GameStep.VOTE and not human_is_alive:
        handle_auto_vote(session)
    elif session.step == GameStep.EXECUTION_RESULT:
        execute_night_phase(session)
    elif session.step == GameStep.NIGHT_RESULT:
        advance_to_discussion(session)

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

    handle_user_discuss(session, message.strip() or "...")
    interactive_store.save(session)
    return RedirectResponse(url=f"/play/{game_id}", status_code=303)


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
