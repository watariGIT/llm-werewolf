"""main.py エンドポイントのテスト。"""

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
