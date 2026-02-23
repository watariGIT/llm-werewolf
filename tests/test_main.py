"""main.py エンドポイントのテスト。"""

import random
from unittest.mock import patch

from starlette.testclient import TestClient

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.services import create_game
from llm_werewolf.main import _extract_discussions_by_day, app, game_store, interactive_store
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


class TestExtractDiscussionsByDay:
    """_extract_discussions_by_day のユニットテスト。"""

    def test_empty_log(self) -> None:
        game = create_game(PLAYER_NAMES, rng=random.Random(42))
        # ログなしの初期状態
        game_no_log = GameState(players=game.players)
        result = _extract_discussions_by_day(game_no_log)
        assert result == {}

    def test_single_day(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            log=(
                "=== ゲーム開始 ===",
                "--- Day 1 （昼フェーズ） ---",
                "[議論] ラウンド 1",
                "[発言] Alice: こんにちは",
                "[発言] Bob: よろしく",
                "[投票] Alice → Bob",
            ),
        )
        result = _extract_discussions_by_day(game)
        assert result == {1: ["Alice: こんにちは", "Bob: よろしく"]}

    def test_multiple_days(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[発言] Alice: Day1の発言",
                "--- Night 1 （夜フェーズ） ---",
                "--- Day 2 （昼フェーズ） ---",
                "[発言] Bob: Day2の発言1",
                "[発言] Charlie: Day2の発言2",
            ),
        )
        result = _extract_discussions_by_day(game)
        assert result == {
            1: ["Alice: Day1の発言"],
            2: ["Bob: Day2の発言1", "Charlie: Day2の発言2"],
        }

    def test_no_speech_entries(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[投票] Alice → Bob",
                "[処刑] Bob が処刑された（得票数: 3）",
            ),
        )
        result = _extract_discussions_by_day(game)
        assert result == {}
