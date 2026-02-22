"""MetricsCollectingProvider と GameMetrics のテスト。"""

import random

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Role
from llm_werewolf.engine.metrics import ActionMetrics, GameMetrics, MetricsCollectingProvider
from llm_werewolf.engine.random_provider import RandomActionProvider


def _create_game() -> GameState:
    return GameState(
        players=(
            Player(name="Alice", role=Role.VILLAGER),
            Player(name="Bob", role=Role.SEER),
            Player(name="Charlie", role=Role.VILLAGER),
            Player(name="Dave", role=Role.VILLAGER),
            Player(name="Eve", role=Role.WEREWOLF),
        )
    )


class TestActionMetrics:
    def test_fields(self) -> None:
        m = ActionMetrics(action_type="discuss", player_name="Alice", elapsed_seconds=1.5)
        assert m.action_type == "discuss"
        assert m.player_name == "Alice"
        assert m.elapsed_seconds == 1.5


class TestGameMetrics:
    def test_empty_metrics(self) -> None:
        gm = GameMetrics()
        assert gm.total_api_calls == 0
        assert gm.average_latency == 0.0

    def test_total_api_calls(self) -> None:
        gm = GameMetrics(
            actions=[
                ActionMetrics("discuss", "Alice", 1.0),
                ActionMetrics("vote", "Bob", 2.0),
            ]
        )
        assert gm.total_api_calls == 2

    def test_average_latency(self) -> None:
        gm = GameMetrics(
            actions=[
                ActionMetrics("discuss", "Alice", 1.0),
                ActionMetrics("vote", "Bob", 3.0),
            ]
        )
        assert gm.average_latency == 2.0


class TestMetricsCollectingProvider:
    def test_discuss_records_metrics(self) -> None:
        rng = random.Random(42)
        inner = RandomActionProvider(rng=rng)
        metrics = GameMetrics()
        provider = MetricsCollectingProvider(inner, metrics)

        game = _create_game()
        player = game.players[0]
        result = provider.discuss(game, player)

        assert isinstance(result, str)
        assert len(result) > 0
        assert metrics.total_api_calls == 1
        assert metrics.actions[0].action_type == "discuss"
        assert metrics.actions[0].player_name == "Alice"
        assert metrics.actions[0].elapsed_seconds >= 0

    def test_vote_records_metrics(self) -> None:
        rng = random.Random(42)
        inner = RandomActionProvider(rng=rng)
        metrics = GameMetrics()
        provider = MetricsCollectingProvider(inner, metrics)

        game = _create_game()
        player = game.players[0]
        candidates = tuple(p for p in game.players if p.name != player.name)
        result = provider.vote(game, player, candidates)

        assert result in [c.name for c in candidates]
        assert metrics.total_api_calls == 1
        assert metrics.actions[0].action_type == "vote"

    def test_divine_records_metrics(self) -> None:
        rng = random.Random(42)
        inner = RandomActionProvider(rng=rng)
        metrics = GameMetrics()
        provider = MetricsCollectingProvider(inner, metrics)

        game = _create_game()
        seer = game.players[1]  # Bob (seer)
        candidates = tuple(p for p in game.players if p.name != seer.name)
        result = provider.divine(game, seer, candidates)

        assert result in [c.name for c in candidates]
        assert metrics.actions[0].action_type == "divine"
        assert metrics.actions[0].player_name == "Bob"

    def test_attack_records_metrics(self) -> None:
        rng = random.Random(42)
        inner = RandomActionProvider(rng=rng)
        metrics = GameMetrics()
        provider = MetricsCollectingProvider(inner, metrics)

        game = _create_game()
        werewolf = game.players[4]  # Eve (werewolf)
        candidates = tuple(p for p in game.players if p.role != Role.WEREWOLF)
        result = provider.attack(game, werewolf, candidates)

        assert result in [c.name for c in candidates]
        assert metrics.actions[0].action_type == "attack"
        assert metrics.actions[0].player_name == "Eve"

    def test_multiple_actions_accumulate(self) -> None:
        rng = random.Random(42)
        inner = RandomActionProvider(rng=rng)
        metrics = GameMetrics()
        provider = MetricsCollectingProvider(inner, metrics)

        game = _create_game()
        for player in game.players:
            provider.discuss(game, player)

        assert metrics.total_api_calls == 5
        assert metrics.average_latency >= 0

    def test_metrics_property(self) -> None:
        inner = RandomActionProvider(rng=random.Random(42))
        metrics = GameMetrics()
        provider = MetricsCollectingProvider(inner, metrics)
        assert provider.metrics is metrics
