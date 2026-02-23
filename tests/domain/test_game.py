import pytest

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role


@pytest.fixture
def players() -> tuple[Player, ...]:
    return (
        Player(name="Alice", role=Role.VILLAGER),
        Player(name="Bob", role=Role.SEER),
        Player(name="Charlie", role=Role.VILLAGER),
        Player(name="Dave", role=Role.VILLAGER),
        Player(name="Eve", role=Role.WEREWOLF),
    )


class TestGameState:
    def test_defaults(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        assert game.phase == Phase.DAY
        assert game.day == 1
        assert game.log == ()

    def test_alive_players(self, players: tuple[Player, ...]) -> None:
        dead_player = players[0].killed()
        new_players = (dead_player,) + players[1:]
        game = GameState(players=new_players)
        assert len(game.alive_players) == 4
        assert dead_player not in game.alive_players

    def test_alive_werewolves(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        assert len(game.alive_werewolves) == 1
        assert game.alive_werewolves[0].role == Role.WEREWOLF

    def test_alive_village_team(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        village_team = game.alive_village_team
        assert len(village_team) == 4
        assert all(p.role != Role.WEREWOLF for p in village_team)

    def test_alive_village_team_after_kill(self, players: tuple[Player, ...]) -> None:
        dead_seer = players[1].killed()
        new_players = players[:1] + (dead_seer,) + players[2:]
        game = GameState(players=new_players)
        assert len(game.alive_village_team) == 3

    def test_add_log(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        game = game.add_log("Day 1 started")
        game = game.add_log("Alice voted for Eve")
        assert len(game.log) == 2
        assert game.log[0] == "Day 1 started"

    def test_replace_player(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        old_player = players[0]
        dead_player = old_player.killed()
        new_game = game.replace_player(old_player, dead_player)
        assert len(new_game.alive_players) == 4
        assert dead_player in new_game.players
        assert old_player not in new_game.players
        # 元の GameState は変更されない
        assert len(game.alive_players) == 5

    def test_find_player_returns_player(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        result = game.find_player("Alice")
        assert result is not None
        assert result.name == "Alice"

    def test_find_player_returns_none_for_unknown(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        assert game.find_player("Unknown") is None

    def test_find_player_alive_only(self, players: tuple[Player, ...]) -> None:
        dead = players[0].killed()
        game = GameState(players=(dead,) + players[1:])
        assert game.find_player("Alice", alive_only=False) is not None
        assert game.find_player("Alice", alive_only=True) is None

    def test_frozen(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        with pytest.raises(AttributeError):
            game.phase = Phase.NIGHT  # type: ignore[misc]


class TestGuardHistory:
    def test_add_guard_history(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        game = game.add_guard_history("Knight", "Alice")
        game = game.add_guard_history("Knight", "Bob")
        assert game.guard_history == (("Knight", "Alice"), ("Knight", "Bob"))

    def test_get_last_guard_target(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        game = game.add_guard_history("Knight", "Alice")
        game = game.add_guard_history("Knight", "Bob")
        assert game.get_last_guard_target("Knight") == "Bob"

    def test_get_last_guard_target_no_history(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        assert game.get_last_guard_target("Knight") is None

    def test_immutability(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        new_game = game.add_guard_history("Knight", "Alice")
        assert game.guard_history == ()
        assert len(new_game.guard_history) == 1


class TestMediumResults:
    def test_add_medium_result(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        game = game.add_medium_result(1, "Eve", True)
        game = game.add_medium_result(2, "Alice", False)
        assert game.medium_results == ((1, "Eve", True), (2, "Alice", False))

    def test_immutability(self, players: tuple[Player, ...]) -> None:
        game = GameState(players=players)
        new_game = game.add_medium_result(1, "Eve", True)
        assert game.medium_results == ()
        assert len(new_game.medium_results) == 1


class TestAliveVillageTeamExcludesMadman:
    def test_madman_excluded_from_village_team(self) -> None:
        players = (
            Player(name="Alice", role=Role.VILLAGER),
            Player(name="Bob", role=Role.SEER),
            Player(name="Charlie", role=Role.MADMAN),
            Player(name="Dave", role=Role.VILLAGER),
            Player(name="Eve", role=Role.WEREWOLF),
        )
        game = GameState(players=players)
        village_team = game.alive_village_team
        assert len(village_team) == 3
        assert all(p.role.team.value == "village" for p in village_team)
        assert not any(p.role == Role.MADMAN for p in village_team)
