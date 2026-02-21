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
    divined_history: dict[str, list[str]] = field(default_factory=dict)

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

    def add_divine_history(self, seer_name: str, target_name: str) -> None:
        """占い履歴を追加する"""
        if seer_name not in self.divined_history:
            self.divined_history[seer_name] = []
        self.divined_history[seer_name].append(target_name)

    def get_divined_history(self, seer_name: str) -> list[str]:
        """占い師の占い履歴を取得する"""
        return self.divined_history.get(seer_name, [])
