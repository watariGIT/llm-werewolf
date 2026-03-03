"""main.py エンドポイントのテスト。"""

import logging
import random
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.services import create_game
from llm_werewolf.engine.llm_config import LLMConfig, PromptConfig
from llm_werewolf.main import (
    _extract_current_execution_logs,
    _extract_discussions_by_day,
    _extract_events_by_day,
    _log_startup_config,
    app,
    game_store,
    interactive_store,
)
from llm_werewolf.session import SessionLimitExceeded

client = TestClient(app, raise_server_exceptions=False)

PLAYER_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Heidi", "Ivan"]


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


class TestExtractCurrentExecutionLogs:
    """_extract_current_execution_logs のユニットテスト。"""

    def test_empty_log(self) -> None:
        game = GameState(players=create_game(PLAYER_NAMES, rng=random.Random(42)).players)
        result = _extract_current_execution_logs(game)
        assert result == []

    def test_extracts_current_day_only(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=2,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[処刑] Alice が処刑された（得票数: 3）",
                "--- Night 1 （夜フェーズ） ---",
                "--- Day 2 （昼フェーズ） ---",
                "[処刑] Bob が処刑された（得票数: 2）",
            ),
        )
        result = _extract_current_execution_logs(game)
        assert result == ["Bob が処刑された（得票数: 2）"]

    def test_strips_prefix(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=1,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[処刑] Charlie が処刑された（得票数: 4）",
            ),
        )
        result = _extract_current_execution_logs(game)
        assert result == ["Charlie が処刑された（得票数: 4）"]

    def test_no_execution_logs(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=1,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[発言] Alice: こんにちは",
                "[投票] Alice → Bob",
            ),
        )
        result = _extract_current_execution_logs(game)
        assert result == []


class TestExtractEventsByDay:
    """_extract_events_by_day のユニットテスト。"""

    def test_empty_log(self) -> None:
        game = GameState(players=create_game(PLAYER_NAMES, rng=random.Random(42)).players)
        result = _extract_events_by_day(game)
        assert result == {}

    def test_extracts_vote_execution_attack(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[発言] Alice: こんにちは",
                "[投票] Alice → Bob",
                "[投票] Charlie → Bob",
                "[処刑] Bob が処刑された（得票数: 2）",
                "--- Night 1 （夜フェーズ） ---",
                "[襲撃] Diana が人狼に襲撃された",
            ),
        )
        result = _extract_events_by_day(game)
        assert result == {
            1: [
                ("vote", "Alice → Bob"),
                ("vote", "Charlie → Bob"),
                ("execution", "Bob が処刑された（得票数: 2）"),
                ("attack", "Diana が人狼に襲撃された"),
            ]
        }

    def test_multiple_days(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[投票] Alice → Bob",
                "[処刑] Bob が処刑された（得票数: 3）",
                "--- Night 1 （夜フェーズ） ---",
                "[襲撃] Charlie が人狼に襲撃された",
                "--- Day 2 （昼フェーズ） ---",
                "[投票] Diana → Eve",
                "[処刑] Eve が処刑された（得票数: 2）",
            ),
        )
        result = _extract_events_by_day(game)
        assert 1 in result
        assert 2 in result
        assert result[1] == [
            ("vote", "Alice → Bob"),
            ("execution", "Bob が処刑された（得票数: 3）"),
            ("attack", "Charlie が人狼に襲撃された"),
        ]
        assert result[2] == [
            ("vote", "Diana → Eve"),
            ("execution", "Eve が処刑された（得票数: 2）"),
        ]

    def test_night_events_belong_to_same_day(self) -> None:
        """夜フェーズのイベントは同じ Day に紐づく。"""
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[投票] Alice → Bob",
                "--- Night 1 （夜フェーズ） ---",
                "[襲撃] 今夜は誰も襲撃されなかった",
            ),
        )
        result = _extract_events_by_day(game)
        assert result == {
            1: [
                ("vote", "Alice → Bob"),
                ("attack", "今夜は誰も襲撃されなかった"),
            ]
        }

    def test_ignores_non_event_entries(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[発言] Alice: こんにちは",
                "[議論] ラウンド 1",
                "[占い結果] Alice: Bob は人狼ではない",
                "[投票] Alice → Bob",
            ),
        )
        result = _extract_events_by_day(game)
        assert result == {1: [("vote", "Alice → Bob")]}


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


class TestLogStartupConfig:
    """_log_startup_config のユニットテスト。"""

    def _make_configs(self) -> tuple[LLMConfig, LLMConfig, PromptConfig]:
        llm = LLMConfig(model_name="gpt-4o-mini", temperature=0.7, api_key="dummy")
        gm = LLMConfig(model_name="gpt-4o", temperature=0.3, api_key="dummy")
        prompt = PromptConfig(max_recent_statements=10, gm_max_recent_statements=20)
        return llm, gm, prompt

    def test_logs_player_ai_config(self, caplog: pytest.LogCaptureFixture) -> None:
        llm, gm, prompt = self._make_configs()
        with caplog.at_level(logging.INFO, logger="llm_werewolf.main"):
            _log_startup_config(llm, gm, prompt, llm_debug=False, log_level="INFO")
        assert any("gpt-4o-mini" in r.message and "0.7" in r.message for r in caplog.records)

    def test_logs_gm_config(self, caplog: pytest.LogCaptureFixture) -> None:
        llm, gm, prompt = self._make_configs()
        with caplog.at_level(logging.INFO, logger="llm_werewolf.main"):
            _log_startup_config(llm, gm, prompt, llm_debug=False, log_level="INFO")
        assert any("gpt-4o" in r.message and "0.3" in r.message for r in caplog.records)

    def test_logs_prompt_config(self, caplog: pytest.LogCaptureFixture) -> None:
        llm, gm, prompt = self._make_configs()
        with caplog.at_level(logging.INFO, logger="llm_werewolf.main"):
            _log_startup_config(llm, gm, prompt, llm_debug=False, log_level="INFO")
        assert any("10" in r.message and "20" in r.message for r in caplog.records)

    def test_logs_llm_debug_and_log_level(self, caplog: pytest.LogCaptureFixture) -> None:
        llm, gm, prompt = self._make_configs()
        with caplog.at_level(logging.INFO, logger="llm_werewolf.main"):
            _log_startup_config(llm, gm, prompt, llm_debug=True, log_level="DEBUG")
        assert any("True" in r.message and "DEBUG" in r.message for r in caplog.records)

    def test_does_not_log_api_key_value(self, caplog: pytest.LogCaptureFixture) -> None:
        llm, gm, prompt = self._make_configs()
        with caplog.at_level(logging.INFO, logger="llm_werewolf.main"):
            _log_startup_config(llm, gm, prompt, llm_debug=False, log_level="INFO")
        for record in caplog.records:
            assert "dummy" not in record.message
