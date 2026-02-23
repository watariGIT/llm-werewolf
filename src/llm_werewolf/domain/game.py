from dataclasses import dataclass, replace

from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role, Team


@dataclass(frozen=True)
class GameState:
    """ゲーム状態（集約ルート）"""

    players: tuple[Player, ...]
    phase: Phase = Phase.DAY
    day: int = 1
    log: tuple[str, ...] = ()
    divined_history: tuple[tuple[str, str], ...] = ()
    guard_history: tuple[tuple[str, str], ...] = ()
    medium_results: tuple[tuple[int, str, bool], ...] = ()
    gm_summary: str | None = None
    gm_summary_log_offset: int = 0

    @property
    def alive_players(self) -> tuple[Player, ...]:
        return tuple(p for p in self.players if p.is_alive)

    @property
    def alive_werewolves(self) -> tuple[Player, ...]:
        return tuple(p for p in self.alive_players if p.role == Role.WEREWOLF)

    @property
    def alive_village_team(self) -> tuple[Player, ...]:
        """村人陣営の生存者"""
        return tuple(p for p in self.alive_players if p.role.team != Team.WEREWOLF)

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

    def add_guard_history(self, knight_name: str, target_name: str) -> "GameState":
        """護衛履歴を追加した新しい GameState を返す"""
        return replace(self, guard_history=self.guard_history + ((knight_name, target_name),))

    def get_last_guard_target(self, knight_name: str) -> str | None:
        """狩人の最後の護衛対象を取得する。履歴がなければ None。"""
        for knight, target in reversed(self.guard_history):
            if knight == knight_name:
                return target
        return None

    def add_medium_result(self, day: int, name: str, is_werewolf: bool) -> "GameState":
        """霊媒結果を追加した新しい GameState を返す"""
        return replace(self, medium_results=self.medium_results + ((day, name, is_werewolf),))
