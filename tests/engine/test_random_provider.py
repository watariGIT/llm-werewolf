import random

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Role
from llm_werewolf.engine.random_provider import DUMMY_MESSAGES, RandomActionProvider


class TestRandomActionProvider:
    def _create_game(self) -> GameState:
        return GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.VILLAGER),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
            )
        )

    def test_discuss_returns_dummy_message(self) -> None:
        rng = random.Random(42)
        provider = RandomActionProvider(rng=rng)
        game = self._create_game()
        message = provider.discuss(game, game.players[0])
        assert message in DUMMY_MESSAGES

    def test_vote_returns_candidate_name(self) -> None:
        rng = random.Random(42)
        provider = RandomActionProvider(rng=rng)
        game = self._create_game()
        candidates = (game.players[1], game.players[2])
        name = provider.vote(game, game.players[0], candidates)
        assert name in {p.name for p in candidates}

    def test_divine_returns_candidate_name(self) -> None:
        rng = random.Random(42)
        provider = RandomActionProvider(rng=rng)
        game = self._create_game()
        candidates = (game.players[1], game.players[2])
        name = provider.divine(game, game.players[0], candidates)
        assert name in {p.name for p in candidates}

    def test_attack_returns_candidate_name(self) -> None:
        rng = random.Random(42)
        provider = RandomActionProvider(rng=rng)
        game = self._create_game()
        candidates = (game.players[0], game.players[2])
        name = provider.attack(game, game.players[1], candidates)
        assert name in {p.name for p in candidates}

    def test_guard_returns_candidate_name(self) -> None:
        rng = random.Random(42)
        provider = RandomActionProvider(rng=rng)
        game = self._create_game()
        candidates = (game.players[0], game.players[2])
        name = provider.guard(game, game.players[3], candidates)
        assert name in {p.name for p in candidates}

    def test_deterministic_with_same_seed(self) -> None:
        game = self._create_game()
        candidates = game.alive_players

        results1 = []
        provider1 = RandomActionProvider(rng=random.Random(123))
        for _ in range(5):
            results1.append(provider1.vote(game, game.players[0], candidates))

        results2 = []
        provider2 = RandomActionProvider(rng=random.Random(123))
        for _ in range(5):
            results2.append(provider2.vote(game, game.players[0], candidates))

        assert results1 == results2
