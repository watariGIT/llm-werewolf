import random
from collections import Counter

import pytest

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import assign_roles, check_victory, create_game
from llm_werewolf.domain.value_objects import PlayerStatus, Role, Team

PLAYER_NAMES = ["Alice", "Bob", "Charlie", "Dave", "Eve"]


class TestAssignRoles:
    def test_returns_five_players(self) -> None:
        players = assign_roles(PLAYER_NAMES)
        assert len(players) == 5

    def test_role_composition(self) -> None:
        players = assign_roles(PLAYER_NAMES)
        role_counts = Counter(p.role for p in players)
        assert role_counts[Role.VILLAGER] == 3
        assert role_counts[Role.SEER] == 1
        assert role_counts[Role.WEREWOLF] == 1

    def test_names_preserved(self) -> None:
        players = assign_roles(PLAYER_NAMES)
        assert [p.name for p in players] == PLAYER_NAMES

    def test_deterministic_with_seed(self) -> None:
        players1 = assign_roles(PLAYER_NAMES, rng=random.Random(42))
        players2 = assign_roles(PLAYER_NAMES, rng=random.Random(42))
        assert [p.role for p in players1] == [p.role for p in players2]

    def test_invalid_player_count(self) -> None:
        with pytest.raises(ValueError, match="Player count must be 5"):
            assign_roles(["Alice", "Bob"])


class TestCreateGame:
    def test_returns_game_state(self) -> None:
        game = create_game(PLAYER_NAMES)
        assert isinstance(game, GameState)
        assert len(game.players) == 5


class TestCheckVictory:
    def test_village_wins_when_werewolf_dead(self) -> None:
        players = [
            Player(name="Alice", role=Role.VILLAGER),
            Player(name="Bob", role=Role.SEER),
            Player(name="Charlie", role=Role.VILLAGER),
            Player(name="Dave", role=Role.VILLAGER),
            Player(name="Eve", role=Role.WEREWOLF, status=PlayerStatus.DEAD),
        ]
        game = GameState(players=players)
        assert check_victory(game) == Team.VILLAGE

    def test_werewolf_wins_when_villagers_lte_werewolves(self) -> None:
        players = [
            Player(name="Alice", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Bob", role=Role.SEER, status=PlayerStatus.DEAD),
            Player(name="Charlie", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Dave", role=Role.VILLAGER),
            Player(name="Eve", role=Role.WEREWOLF),
        ]
        game = GameState(players=players)
        assert check_victory(game) == Team.WEREWOLF

    def test_ongoing_game(self) -> None:
        players = [
            Player(name="Alice", role=Role.VILLAGER),
            Player(name="Bob", role=Role.SEER),
            Player(name="Charlie", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Dave", role=Role.VILLAGER),
            Player(name="Eve", role=Role.WEREWOLF),
        ]
        game = GameState(players=players)
        assert check_victory(game) is None

    def test_initial_state(self) -> None:
        game = create_game(PLAYER_NAMES)
        assert check_victory(game) is None
