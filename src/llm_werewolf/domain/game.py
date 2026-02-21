from dataclasses import dataclass, field

from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role


@dataclass
class GameState:
    """ゲーム状態（集約ルート）"""

    players: list[Player]
    phase: Phase = Phase.DAY
    day: int = 1
    log: list[str] = field(default_factory=list)

    @property
    def alive_players(self) -> list[Player]:
        return [p for p in self.players if p.is_alive]

    @property
    def alive_werewolves(self) -> list[Player]:
        return [p for p in self.alive_players if p.role == Role.WEREWOLF]

    @property
    def alive_village_team(self) -> list[Player]:
        """村人陣営（村人+占い師）の生存者"""
        return [p for p in self.alive_players if p.role != Role.WEREWOLF]

    def add_log(self, message: str) -> None:
        self.log.append(message)
