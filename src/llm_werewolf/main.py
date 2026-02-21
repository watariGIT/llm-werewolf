from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import REQUIRED_PLAYER_COUNT
from llm_werewolf.session import GameSessionStore

app = FastAPI(title="LLM人狼")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

game_store = GameSessionStore()

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
