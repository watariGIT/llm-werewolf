from dataclasses import dataclass, replace

from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role


@dataclass(frozen=True)
class GameState:
    """ゲーム状態（集約ルート）"""

    players: tuple[Player, ...]
    phase: Phase = Phase.DAY
    day: int = 1
    log: tuple[str, ...] = ()
    divined_history: tuple[tuple[str, str], ...] = ()

    @property
    def alive_players(self) -> tuple[Player, ...]:
        return tuple(p for p in self.players if p.is_alive)

    @property
    def alive_werewolves(self) -> tuple[Player, ...]:
        return tuple(p for p in self.alive_players if p.role == Role.WEREWOLF)

    @property
    def alive_village_team(self) -> tuple[Player, ...]:
        """村人陣営（村人+占い師）の生存者"""
        return tuple(p for p in self.alive_players if p.role != Role.WEREWOLF)

    def find_player(self, name: str, *, alive_only: bool = False) -> "Player | None":
        """名前でプレイヤーを検索する。alive_only=True の場合は生存者のみ。"""
        players = self.alive_players if alive_only else self.players
        for p in players:
            if p.name == name:
                return p
        return None

    def replace_player(self, old: Player, new: Player) -> "GameState":
        """プレイヤーを差し替えた新しい GameState を返す"""
        players = tuple(new if p is old else p for p in self.players)
        return replace(self, players=players)

    def add_log(self, message: str) -> "GameState":
        return replace(self, log=self.log + (message,))

    def add_divine_history(self, seer_name: str, target_name: str) -> "GameState":
        """占い履歴を追加した新しい GameState を返す"""
        return replace(self, divined_history=self.divined_history + ((seer_name, target_name),))

    def get_divined_history(self, seer_name: str) -> tuple[str, ...]:
        """占い師の占い履歴を取得する"""
        return tuple(target for seer, target in self.divined_history if seer == seer_name)
