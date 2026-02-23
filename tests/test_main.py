"""main.py エンドポイントのテスト。"""

import random
from unittest.mock import patch

from starlette.testclient import TestClient

from llm_werewolf.main import app, game_store, interactive_store
from llm_werewolf.session import SessionLimitExceeded

client = TestClient(app, raise_server_exceptions=False)

PLAYER_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve"]


class TestSessionLimitExceededHandler:
    """SessionLimitExceeded が exception_handler 経由で 429 を返すことを確認する。"""

    def test_post_games_returns_429_on_session_limit(self) -> None:
        with patch.object(game_store, "create", side_effect=SessionLimitExceeded("上限")):
            response = client.post("/games", json={"player_names": PLAYER_NAMES})
        assert response.status_code == 429
        assert "セッション数が上限に達しました" in response.json()["detail"]

    def test_post_play_returns_429_on_session_limit(self) -> None:
        with patch.object(interactive_store, "create", side_effect=SessionLimitExceeded("上限")):
            response = client.post("/play", data={"player_name": "テスト", "role": "random"}, follow_redirects=False)
        assert response.status_code == 429
        assert "セッション数が上限に達しました" in response.json()["detail"]


class TestExportGameLog:
    """GET /play/{game_id}/export のテスト。"""

    def test_export_returns_log_json(self) -> None:
        session = interactive_store.create("テスト", rng=random.Random(42))
        response = client.get(f"/play/{session.game_id}/export")
        assert response.status_code == 200
        data = response.json()
        assert "log" in data
        assert isinstance(data["log"], list)
        assert len(data["log"]) > 0
        assert "Content-Disposition" in response.headers
        assert f"game-log-{session.game_id}.json" in response.headers["Content-Disposition"]
        interactive_store.delete(session.game_id)

    def test_export_returns_404_for_missing_game(self) -> None:
        response = client.get("/play/nonexistent/export")
        assert response.status_code == 404
