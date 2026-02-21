from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from llm_werewolf.session import GameSessionStore

app = FastAPI(title="LLM人狼")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

game_store = GameSessionStore()


class CreateGameRequest(BaseModel):
    player_names: list[str]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.post("/games")
async def create_game(body: CreateGameRequest) -> JSONResponse:
    """新規ゲームを作成し、一括実行して結果を返す。"""
    game_id, game = game_store.create(body.player_names)
    return JSONResponse(
        content={
            "game_id": game_id,
            "day": game.day,
            "phase": game.phase.value,
            "players": [{"name": p.name, "role": p.role.value, "status": p.status.value} for p in game.players],
            "log": list(game.log),
        },
        status_code=201,
    )


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
    return JSONResponse(
        content={
            "game_id": game_id,
            "day": game.day,
            "phase": game.phase.value,
            "players": [{"name": p.name, "role": p.role.value, "status": p.status.value} for p in game.players],
            "log": list(game.log),
        }
    )
