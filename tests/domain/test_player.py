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

    def test_kill(self) -> None:
        player = Player(name="Bob", role=Role.WEREWOLF)
        player.kill()
        assert player.status == PlayerStatus.DEAD
        assert player.is_alive is False

    def test_kill_already_dead_raises(self) -> None:
        player = Player(name="Charlie", role=Role.SEER, status=PlayerStatus.DEAD)
        with pytest.raises(ValueError, match="already dead"):
            player.kill()
