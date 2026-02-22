"""メトリクス収集モジュール。

ActionProvider をラップするデコレータパターンで、
LLMActionProvider を変更せずにレイテンシ等のメトリクスを計測する。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.engine.action_provider import ActionProvider


@dataclass
class ActionMetrics:
    """1回のアクション呼び出しのメトリクス。"""

    action_type: str
    player_name: str
    elapsed_seconds: float


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


class MetricsCollectingProvider:
    """ActionProvider をラップし、各呼び出しのレイテンシを計測するデコレータ。"""

    def __init__(self, inner: ActionProvider, metrics: GameMetrics) -> None:
        self._inner = inner
        self._metrics = metrics

    @property
    def metrics(self) -> GameMetrics:
        return self._metrics

    def _record(self, action_type: str, player_name: str, start: float) -> None:
        elapsed = time.monotonic() - start
        self._metrics.actions.append(ActionMetrics(action_type, player_name, elapsed))

    def discuss(self, game: GameState, player: Player) -> str:
        start = time.monotonic()
        result = self._inner.discuss(game, player)
        self._record("discuss", player.name, start)
        return result

    def vote(self, game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
        start = time.monotonic()
        result = self._inner.vote(game, player, candidates)
        self._record("vote", player.name, start)
        return result

    def divine(self, game: GameState, seer: Player, candidates: tuple[Player, ...]) -> str:
        start = time.monotonic()
        result = self._inner.divine(game, seer, candidates)
        self._record("divine", seer.name, start)
        return result

    def attack(self, game: GameState, werewolf: Player, candidates: tuple[Player, ...]) -> str:
        start = time.monotonic()
        result = self._inner.attack(game, werewolf, candidates)
        self._record("attack", werewolf.name, start)
        return result
