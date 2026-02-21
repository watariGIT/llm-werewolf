import pytest

from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import PlayerStatus, Role


class TestPlayer:
    def test_creation_defaults(self) -> None:
        player = Player(name="Alice", role=Role.VILLAGER)
        assert player.name == "Alice"
        assert player.role == Role.VILLAGER
        assert player.status == PlayerStatus.ALIVE
        assert player.is_alive is True

    def test_killed(self) -> None:
        player = Player(name="Bob", role=Role.WEREWOLF)
        dead_player = player.killed()
        assert dead_player.status == PlayerStatus.DEAD
        assert dead_player.is_alive is False
        # 元のインスタンスは変更されない
        assert player.status == PlayerStatus.ALIVE

    def test_killed_already_dead_raises(self) -> None:
        player = Player(name="Charlie", role=Role.SEER, status=PlayerStatus.DEAD)
        with pytest.raises(ValueError, match="already dead"):
            player.killed()

    def test_frozen(self) -> None:
        player = Player(name="Alice", role=Role.VILLAGER)
        with pytest.raises(AttributeError):
            player.status = PlayerStatus.DEAD  # type: ignore[misc]
