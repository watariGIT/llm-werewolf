"""Web デバッグモードのテスト。"""

import random

from starlette.testclient import TestClient

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.services import create_game
from llm_werewolf.main import (
    _collect_debug_info,
    _extract_night_thinking,
    _extract_thinking_by_day,
    _extract_thinking_map,
    _extract_vote_thinking,
    app,
    interactive_store,
)
from llm_werewolf.session import InteractiveSession

client = TestClient(app, raise_server_exceptions=False)

PLAYER_NAMES = ["Alice", "AI-1", "AI-2", "AI-3", "AI-4", "AI-5", "AI-6", "AI-7", "AI-8"]


def _create_test_session(rng: random.Random | None = None) -> InteractiveSession:
    """テスト用のセッションを作成する。"""
    r = rng if rng is not None else random.Random(42)
    return interactive_store.create("Alice", rng=r)


class TestCollectDebugInfo:
    """_collect_debug_info のユニットテスト。"""

    def test_returns_ai_player_info(self) -> None:
        session = _create_test_session()
        try:
            info = _collect_debug_info(session)
            assert "players" in info
            # 人間プレイヤーは含まれない
            assert "Alice" not in info["players"]
            # AI プレイヤーは含まれる
            assert "AI-1" in info["players"]
            ai1 = info["players"]["AI-1"]
            assert "role" in ai1
            assert "personality" in ai1
            assert "last_thinking" in ai1
            assert "last_input_tokens" in ai1
            assert "last_output_tokens" in ai1
            assert "last_cache_read_input_tokens" in ai1
            assert "last_cost" in ai1
        finally:
            interactive_store.delete(session.game_id)

    def test_all_ai_players_included(self) -> None:
        session = _create_test_session()
        try:
            info = _collect_debug_info(session)
            ai_names = {f"AI-{i}" for i in range(1, 9)}
            assert set(info["players"].keys()) == ai_names
        finally:
            interactive_store.delete(session.game_id)

    def test_gm_info_when_provider_exists(self) -> None:
        """gm_provider がある場合、GM-AI情報が含まれる。"""
        session = _create_test_session()
        try:
            # gm_provider が None の場合は gm キーなし
            session.gm_provider = None
            info = _collect_debug_info(session)
            assert "gm" not in info
        finally:
            interactive_store.delete(session.game_id)

    def test_totals_included(self) -> None:
        """合計値が含まれる。"""
        session = _create_test_session()
        try:
            info = _collect_debug_info(session)
            assert "totals" in info
            totals = info["totals"]
            assert "input_tokens" in totals
            assert "output_tokens" in totals
            assert "cache_read_input_tokens" in totals
            assert "cost" in totals
            assert isinstance(totals["input_tokens"], int)
            assert isinstance(totals["output_tokens"], int)
            assert isinstance(totals["cache_read_input_tokens"], int)
            assert isinstance(totals["cost"], str)
        finally:
            interactive_store.delete(session.game_id)


class TestExtractThinkingMap:
    """_extract_thinking_map のユニットテスト。"""

    def test_empty_log(self) -> None:
        game = GameState(players=create_game(PLAYER_NAMES, rng=random.Random(42)).players)
        result = _extract_thinking_map(game)
        assert result == {}

    def test_extracts_current_day_thinking(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=1,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[思考] AI-1: 占い師COすべきか悩む",
                "[発言] AI-1: おはようございます",
                "[思考] AI-2: 静観しよう",
                "[発言] AI-2: よろしく",
            ),
        )
        result = _extract_thinking_map(game)
        assert "AI-1" in result
        assert result["AI-1"] == ["占い師COすべきか悩む"]
        assert "AI-2" in result
        assert result["AI-2"] == ["静観しよう"]

    def test_ignores_past_day_thinking(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=2,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[思考] AI-1: Day1の思考",
                "[発言] AI-1: Day1の発言",
                "--- Night 1 （夜フェーズ） ---",
                "--- Day 2 （昼フェーズ） ---",
                "[思考] AI-1: Day2の思考",
                "[発言] AI-1: Day2の発言",
            ),
        )
        result = _extract_thinking_map(game)
        assert result == {"AI-1": ["Day2の思考"]}

    def test_multiple_thinking_per_player(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=1,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[思考] AI-1: 1巡目の思考",
                "[発言] AI-1: 1巡目の発言",
                "[思考] AI-1: 2巡目の思考",
                "[発言] AI-1: 2巡目の発言",
            ),
        )
        result = _extract_thinking_map(game)
        assert result == {"AI-1": ["1巡目の思考", "2巡目の思考"]}


class TestExtractVoteThinking:
    """_extract_vote_thinking のユニットテスト。"""

    def test_empty_log(self) -> None:
        game = GameState(players=create_game(PLAYER_NAMES, rng=random.Random(42)).players)
        result = _extract_vote_thinking(game)
        assert result == {}

    def test_extracts_vote_thinking(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=1,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[思考] AI-1: 占い師COすべきか",
                "[発言] AI-1: おはようございます",
                "[思考] AI-2: 静観しよう",
                "[発言] AI-2: よろしく",
                "[思考] AI-1: AI-3が怪しい",
                "[思考] AI-2: AI-4が怪しい",
                "[投票] AI-1 → AI-3",
                "[投票] AI-2 → AI-4",
            ),
        )
        result = _extract_vote_thinking(game)
        assert result == {"AI-1": "AI-3が怪しい", "AI-2": "AI-4が怪しい"}

    def test_ignores_discussion_thinking(self) -> None:
        """議論中の思考は投票思考に含まれない（発言後にクリアされる）。"""
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=1,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[思考] AI-1: 議論の思考",
                "[発言] AI-1: 発言内容",
                "[投票] AI-1 → AI-2",
            ),
        )
        result = _extract_vote_thinking(game)
        # 発言後に思考がクリアされるので、投票思考は空
        assert result == {}

    def test_ignores_past_day(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=2,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[思考] AI-1: Day1の投票理由",
                "[投票] AI-1 → AI-2",
                "--- Night 1 （夜フェーズ） ---",
                "--- Day 2 （昼フェーズ） ---",
                "[思考] AI-1: Day2の投票理由",
                "[投票] AI-1 → AI-3",
            ),
        )
        result = _extract_vote_thinking(game)
        assert result == {"AI-1": "Day2の投票理由"}


class TestExtractNightThinking:
    """_extract_night_thinking のユニットテスト。"""

    def test_empty_log(self) -> None:
        game = GameState(players=create_game(PLAYER_NAMES, rng=random.Random(42)).players)
        result = _extract_night_thinking(game, 1)
        assert result == {}

    def test_extracts_night_thinking(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=2,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "--- Night 1 （夜フェーズ） ---",
                "[思考] AI-1: AI-3を占いたい",
                "[思考] AI-2: AI-4を護衛する",
                "[思考] AI-5: AI-6を襲撃する",
                "--- Day 2 （昼フェーズ） ---",
            ),
        )
        result = _extract_night_thinking(game, 1)
        assert result == {
            "AI-1": "AI-3を占いたい",
            "AI-2": "AI-4を護衛する",
            "AI-5": "AI-6を襲撃する",
        }

    def test_ignores_other_night(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=3,
            log=(
                "--- Night 1 （夜フェーズ） ---",
                "[思考] AI-1: Night1の思考",
                "--- Day 2 （昼フェーズ） ---",
                "--- Night 2 （夜フェーズ） ---",
                "[思考] AI-1: Night2の思考",
                "--- Day 3 （昼フェーズ） ---",
            ),
        )
        result = _extract_night_thinking(game, 2)
        assert result == {"AI-1": "Night2の思考"}


class TestDebugModeEndpoint:
    """デバッグモード有効時のエンドポイントテスト。"""

    def test_debug_mode_shows_all_roles(self) -> None:
        """debug=1 パラメータで全プレイヤーの役職が表示される。"""
        session = _create_test_session()
        try:
            response = client.get(f"/play/{session.game_id}?debug=1")
            assert response.status_code == 200
            html = response.text
            assert "DEBUG" in html
            # デバッグ情報テーブルが含まれる
            assert "デバッグ情報" in html
        finally:
            interactive_store.delete(session.game_id)

    def test_normal_mode_hides_debug(self) -> None:
        """debug パラメータなしではデバッグ情報が表示されない。"""
        session = _create_test_session()
        try:
            response = client.get(f"/play/{session.game_id}")
            assert response.status_code == 200
            html = response.text
            # デバッグ情報テーブル（h2タグ）が含まれない
            assert "<h2>デバッグ情報</h2>" not in html
        finally:
            interactive_store.delete(session.game_id)

    def test_debug_mode_false_when_not_1(self) -> None:
        """debug パラメータが '1' 以外ではデバッグ情報が表示されない。"""
        session = _create_test_session()
        try:
            response = client.get(f"/play/{session.game_id}?debug=0")
            assert response.status_code == 200
            html = response.text
            assert "<h2>デバッグ情報</h2>" not in html
        finally:
            interactive_store.delete(session.game_id)


class TestExtractThinkingByDay:
    """_extract_thinking_by_day のユニットテスト。"""

    def test_empty_log(self) -> None:
        game = GameState(players=create_game(PLAYER_NAMES, rng=random.Random(42)).players)
        result = _extract_thinking_by_day(game)
        assert result == {}

    def test_extracts_discussion_thinking(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=1,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[思考] AI-1: 占い師COすべきか",
                "[発言] AI-1: おはようございます",
                "[思考] AI-2: 静観しよう",
                "[発言] AI-2: よろしく",
            ),
        )
        result = _extract_thinking_by_day(game)
        assert 1 in result
        assert result[1]["discussion"] == {"AI-1": ["占い師COすべきか"], "AI-2": ["静観しよう"]}

    def test_extracts_vote_thinking(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=1,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[思考] AI-1: 議論の思考",
                "[発言] AI-1: 発言内容",
                "[思考] AI-1: AI-3が怪しい",
                "[投票] AI-1 → AI-3",
            ),
        )
        result = _extract_thinking_by_day(game)
        assert result[1]["vote"] == {"AI-1": "AI-3が怪しい"}

    def test_extracts_night_thinking(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=2,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "--- Night 1 （夜フェーズ） ---",
                "[思考] AI-1: AI-3を占いたい",
                "--- Day 2 （昼フェーズ） ---",
            ),
        )
        result = _extract_thinking_by_day(game)
        assert result[1]["night"] == {"AI-1": "AI-3を占いたい"}

    def test_multiple_days(self) -> None:
        game = GameState(
            players=create_game(PLAYER_NAMES, rng=random.Random(42)).players,
            day=2,
            log=(
                "--- Day 1 （昼フェーズ） ---",
                "[思考] AI-1: Day1の思考",
                "[発言] AI-1: Day1の発言",
                "[思考] AI-1: Day1投票理由",
                "[投票] AI-1 → AI-2",
                "--- Night 1 （夜フェーズ） ---",
                "[思考] AI-1: Night1の思考",
                "--- Day 2 （昼フェーズ） ---",
                "[思考] AI-2: Day2の思考",
                "[発言] AI-2: Day2の発言",
            ),
        )
        result = _extract_thinking_by_day(game)
        assert result[1]["discussion"] == {"AI-1": ["Day1の思考"]}
        assert result[1]["vote"] == {"AI-1": "Day1投票理由"}
        assert result[1]["night"] == {"AI-1": "Night1の思考"}
        assert result[2]["discussion"] == {"AI-2": ["Day2の思考"]}
