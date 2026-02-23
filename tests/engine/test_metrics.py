"""MetricsCollectingProvider と GameMetrics のテスト。"""

import random

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Role
from llm_werewolf.engine.metrics import (
    MODEL_PRICING,
    ActionMetrics,
    GameMetrics,
    MetricsCollectingProvider,
    estimate_cost,
)
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
        assert m.input_tokens == 0
        assert m.output_tokens == 0

    def test_token_fields(self) -> None:
        m = ActionMetrics("discuss", "Alice", 1.0, input_tokens=100, output_tokens=50)
        assert m.input_tokens == 100
        assert m.output_tokens == 50


class TestGameMetrics:
    def test_empty_metrics(self) -> None:
        gm = GameMetrics()
        assert gm.total_api_calls == 0
        assert gm.average_latency == 0.0
        assert gm.total_input_tokens == 0
        assert gm.total_output_tokens == 0
        assert gm.total_tokens == 0

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

    def test_total_tokens(self) -> None:
        gm = GameMetrics(
            actions=[
                ActionMetrics("discuss", "Alice", 1.0, input_tokens=100, output_tokens=50),
                ActionMetrics("vote", "Bob", 2.0, input_tokens=200, output_tokens=30),
            ]
        )
        assert gm.total_input_tokens == 300
        assert gm.total_output_tokens == 80
        assert gm.total_tokens == 380

    def test_estimated_cost_usd_known_model(self) -> None:
        gm = GameMetrics(
            actions=[
                ActionMetrics("discuss", "Alice", 1.0, input_tokens=1_000_000, output_tokens=100_000),
            ]
        )
        # gpt-4o: input $2.50/1M, output $10.00/1M
        cost = gm.estimated_cost_usd("gpt-4o")
        assert cost is not None
        assert abs(cost - (2.50 + 1.00)) < 0.001

    def test_estimated_cost_usd_unknown_model(self) -> None:
        gm = GameMetrics(
            actions=[
                ActionMetrics("discuss", "Alice", 1.0, input_tokens=1000, output_tokens=500),
            ]
        )
        assert gm.estimated_cost_usd("unknown-model") is None


class TestEstimateCost:
    def test_known_model(self) -> None:
        # gpt-4o-mini: input $0.15/1M, output $0.60/1M
        cost = estimate_cost("gpt-4o-mini", 2_000_000, 500_000)
        assert cost is not None
        assert abs(cost - (0.30 + 0.30)) < 0.001

    def test_unknown_model(self) -> None:
        assert estimate_cost("nonexistent", 1000, 500) is None

    def test_zero_tokens(self) -> None:
        cost = estimate_cost("gpt-4o", 0, 0)
        assert cost is not None
        assert cost == 0.0

    def test_gpt_5_mini(self) -> None:
        # gpt-5-mini: input $0.25/1M, output $2.00/1M
        cost = estimate_cost("gpt-5-mini", 1_000_000, 1_000_000)
        assert cost is not None
        assert abs(cost - (0.25 + 2.00)) < 0.001


class TestModelPricing:
    def test_all_models_have_input_and_output(self) -> None:
        for model, pricing in MODEL_PRICING.items():
            assert "input" in pricing, f"{model} missing 'input' price"
            assert "output" in pricing, f"{model} missing 'output' price"
            assert pricing["input"] >= 0, f"{model} has negative input price"
            assert pricing["output"] >= 0, f"{model} has negative output price"


class _TokenTrackingProvider:
    """トークン使用量を返すテスト用プロバイダー。"""

    def __init__(self) -> None:
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0

    def discuss(self, game: GameState, player: Player) -> str:
        self.last_input_tokens = 150
        self.last_output_tokens = 50
        return "テスト発言"

    def vote(self, game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
        self.last_input_tokens = 200
        self.last_output_tokens = 10
        return candidates[0].name

    def divine(self, game: GameState, seer: Player, candidates: tuple[Player, ...]) -> str:
        self.last_input_tokens = 180
        self.last_output_tokens = 10
        return candidates[0].name

    def attack(self, game: GameState, werewolf: Player, candidates: tuple[Player, ...]) -> str:
        self.last_input_tokens = 170
        self.last_output_tokens = 10
        return candidates[0].name

    def guard(self, game: GameState, knight: Player, candidates: tuple[Player, ...]) -> str:
        self.last_input_tokens = 160
        self.last_output_tokens = 10
        return candidates[0].name


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

    def test_discuss_records_token_usage(self) -> None:
        inner = _TokenTrackingProvider()
        metrics = GameMetrics()
        provider = MetricsCollectingProvider(inner, metrics)

        game = _create_game()
        provider.discuss(game, game.players[0])

        assert metrics.actions[0].input_tokens == 150
        assert metrics.actions[0].output_tokens == 50
        assert metrics.total_input_tokens == 150
        assert metrics.total_output_tokens == 50

    def test_vote_records_token_usage(self) -> None:
        inner = _TokenTrackingProvider()
        metrics = GameMetrics()
        provider = MetricsCollectingProvider(inner, metrics)

        game = _create_game()
        candidates = tuple(p for p in game.players if p.name != "Alice")
        provider.vote(game, game.players[0], candidates)

        assert metrics.actions[0].input_tokens == 200
        assert metrics.actions[0].output_tokens == 10

    def test_token_usage_zero_for_non_token_provider(self) -> None:
        """last_input_tokens 属性がない provider ではトークンは 0 になる。"""
        rng = random.Random(42)
        inner = RandomActionProvider(rng=rng)
        metrics = GameMetrics()
        provider = MetricsCollectingProvider(inner, metrics)

        game = _create_game()
        provider.discuss(game, game.players[0])

        assert metrics.actions[0].input_tokens == 0
        assert metrics.actions[0].output_tokens == 0

    def test_multiple_actions_accumulate_tokens(self) -> None:
        inner = _TokenTrackingProvider()
        metrics = GameMetrics()
        provider = MetricsCollectingProvider(inner, metrics)

        game = _create_game()
        provider.discuss(game, game.players[0])  # input=150, output=50
        candidates = tuple(p for p in game.players if p.name != "Alice")
        provider.vote(game, game.players[0], candidates)  # input=200, output=10

        assert metrics.total_input_tokens == 350
        assert metrics.total_output_tokens == 60
        assert metrics.total_tokens == 410
