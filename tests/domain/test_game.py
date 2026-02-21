from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role


def _make_players() -> list[Player]:
    return [
        Player(name="Alice", role=Role.VILLAGER),
        Player(name="Bob", role=Role.SEER),
        Player(name="Charlie", role=Role.VILLAGER),
        Player(name="Dave", role=Role.VILLAGER),
        Player(name="Eve", role=Role.WEREWOLF),
    ]


class TestGameState:
    def test_defaults(self) -> None:
        game = GameState(players=_make_players())
        assert game.phase == Phase.DAY
        assert game.day == 1
        assert game.log == []

    def test_alive_players(self) -> None:
        players = _make_players()
        players[0].kill()
        game = GameState(players=players)
        assert len(game.alive_players) == 4
        assert players[0] not in game.alive_players

    def test_alive_werewolves(self) -> None:
        game = GameState(players=_make_players())
        assert len(game.alive_werewolves) == 1
        assert game.alive_werewolves[0].role == Role.WEREWOLF

    def test_alive_villagers_team(self) -> None:
        game = GameState(players=_make_players())
        villagers_team = game.alive_villagers_team
        assert len(villagers_team) == 4
        assert all(p.role != Role.WEREWOLF for p in villagers_team)

    def test_alive_villagers_team_after_kill(self) -> None:
        players = _make_players()
        players[1].kill()  # seer killed
        game = GameState(players=players)
        assert len(game.alive_villagers_team) == 3

    def test_add_log(self) -> None:
        game = GameState(players=_make_players())
        game.add_log("Day 1 started")
        game.add_log("Alice voted for Eve")
        assert len(game.log) == 2
        assert game.log[0] == "Day 1 started"
