import random

import pytest

from llm_werewolf.domain.services import REQUIRED_PLAYER_COUNT
from llm_werewolf.session import GameSessionStore, SessionLimitExceeded

PLAYER_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve"]


class TestGameSessionStore:
    def _make_store(self) -> GameSessionStore:
        return GameSessionStore()

    def test_create_returns_game_id_and_state(self) -> None:
        store = self._make_store()
        game_id, game = store.create(PLAYER_NAMES, rng=random.Random(42))
        assert isinstance(game_id, str)
        assert len(game_id) == 8
        assert len(game.players) == REQUIRED_PLAYER_COUNT
        assert len(game.log) > 0

    def test_create_without_rng(self) -> None:
        store = self._make_store()
        game_id, game = store.create(PLAYER_NAMES)
        assert isinstance(game_id, str)
        assert len(game_id) == 8
        assert len(game.players) == REQUIRED_PLAYER_COUNT
        assert len(game.log) > 0

    def test_get_returns_saved_state(self) -> None:
        store = self._make_store()
        game_id, game = store.create(PLAYER_NAMES, rng=random.Random(42))
        retrieved = store.get(game_id)
        assert retrieved is game

    def test_get_returns_none_for_unknown_id(self) -> None:
        store = self._make_store()
        assert store.get("unknown") is None

    def test_save_overwrites_state(self) -> None:
        store = self._make_store()
        game_id, original = store.create(PLAYER_NAMES, rng=random.Random(42))
        updated = original.add_log("テスト追加ログ")
        store.save(game_id, updated)
        retrieved = store.get(game_id)
        assert retrieved is updated
        assert retrieved is not original

    def test_delete_removes_session(self) -> None:
        store = self._make_store()
        game_id, _ = store.create(PLAYER_NAMES, rng=random.Random(42))
        store.delete(game_id)
        assert store.get(game_id) is None

    def test_delete_nonexistent_does_not_raise(self) -> None:
        store = self._make_store()
        store.delete("nonexistent")  # should not raise

    def test_list_sessions_returns_all(self) -> None:
        store = self._make_store()
        id1, _ = store.create(PLAYER_NAMES, rng=random.Random(42))
        id2, _ = store.create(PLAYER_NAMES, rng=random.Random(99))
        sessions = store.list_sessions()
        assert id1 in sessions
        assert id2 in sessions
        assert len(sessions) == 2

    def test_list_sessions_returns_copy(self) -> None:
        store = self._make_store()
        store.create(PLAYER_NAMES, rng=random.Random(42))
        sessions = store.list_sessions()
        sessions.clear()
        assert len(store.list_sessions()) == 1

    def test_create_raises_when_max_sessions_reached(self) -> None:
        store = GameSessionStore(max_sessions=3)
        for i in range(3):
            store.create(PLAYER_NAMES, rng=random.Random(i))
        with pytest.raises(SessionLimitExceeded):
            store.create(PLAYER_NAMES, rng=random.Random(999))

    def test_create_after_delete_allows_new_session(self) -> None:
        store = GameSessionStore(max_sessions=2)
        id1, _ = store.create(PLAYER_NAMES, rng=random.Random(0))
        store.create(PLAYER_NAMES, rng=random.Random(1))
        store.delete(id1)
        game_id, _ = store.create(PLAYER_NAMES, rng=random.Random(2))
        assert game_id is not None
