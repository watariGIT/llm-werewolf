"""メトリクス収集モジュール。

ActionProvider をラップするデコレータパターンで、
LLMActionProvider を変更せずにレイテンシ・トークン使用量等のメトリクスを計測する。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.engine.action_provider import ActionProvider

# 料金テーブル（USD per 1M tokens）
# 料金は変動するため参考値。該当しないモデルの場合はコスト推定不可（None）。
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
}


def estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float | None:
    """モデル名とトークン数から推定コスト（USD）を計算する。

    料金テーブルに該当しないモデルの場合は None を返す。
    """
    pricing = MODEL_PRICING.get(model_name)
    if pricing is None:
        return None
    input_cost = input_tokens * pricing["input"] / 1_000_000
    output_cost = output_tokens * pricing["output"] / 1_000_000
    return input_cost + output_cost


@dataclass
class ActionMetrics:
    """1回のアクション呼び出しのメトリクス。"""

    action_type: str
    player_name: str
    elapsed_seconds: float
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class GameMetrics:
    """1ゲーム分のメトリクスを保持する。"""

    actions: list[ActionMetrics] = field(default_factory=list)

    @property
    def total_api_calls(self) -> int:
        return len(self.actions)

    @property
    def average_latency(self) -> float:
        if not self.actions:
            return 0.0
        return sum(a.elapsed_seconds for a in self.actions) / len(self.actions)

    @property
    def total_input_tokens(self) -> int:
        return sum(a.input_tokens for a in self.actions)

    @property
    def total_output_tokens(self) -> int:
        return sum(a.output_tokens for a in self.actions)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def estimated_cost_usd(self, model_name: str) -> float | None:
        """モデル名に基づく推定コスト（USD）を返す。該当しないモデルは None。"""
        return estimate_cost(model_name, self.total_input_tokens, self.total_output_tokens)


class MetricsCollectingProvider:
    """ActionProvider をラップし、各呼び出しのレイテンシとトークン使用量を計測するデコレータ。"""

    def __init__(self, inner: ActionProvider, metrics: GameMetrics) -> None:
        self._inner = inner
        self._metrics = metrics

    @property
    def metrics(self) -> GameMetrics:
        return self._metrics

    def _record(self, action_type: str, player_name: str, start: float) -> None:
        elapsed = time.monotonic() - start
        input_tokens: int = getattr(self._inner, "last_input_tokens", 0)
        output_tokens: int = getattr(self._inner, "last_output_tokens", 0)
        self._metrics.actions.append(ActionMetrics(action_type, player_name, elapsed, input_tokens, output_tokens))

    def discuss(self, game: GameState, player: Player) -> str:
        start = time.monotonic()
        try:
            return self._inner.discuss(game, player)
        finally:
            self._record("discuss", player.name, start)

    def vote(self, game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
        start = time.monotonic()
        try:
            return self._inner.vote(game, player, candidates)
        finally:
            self._record("vote", player.name, start)

    def divine(self, game: GameState, seer: Player, candidates: tuple[Player, ...]) -> str:
        start = time.monotonic()
        try:
            return self._inner.divine(game, seer, candidates)
        finally:
            self._record("divine", seer.name, start)

    def attack(self, game: GameState, werewolf: Player, candidates: tuple[Player, ...]) -> str:
        start = time.monotonic()
        try:
            return self._inner.attack(game, werewolf, candidates)
        finally:
            self._record("attack", werewolf.name, start)

    def guard(self, game: GameState, knight: Player, candidates: tuple[Player, ...]) -> str:
        start = time.monotonic()
        try:
            return self._inner.guard(game, knight, candidates)
        finally:
            self._record("guard", knight.name, start)
