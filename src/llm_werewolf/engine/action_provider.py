from typing import NamedTuple, Protocol

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player


class DiscussResult(NamedTuple):
    """議論の結果。thinking は AI の内部思考（空文字列の場合もある）。"""

    message: str
    thinking: str = ""


class ActionProvider(Protocol):
    """プレイヤーの行動を提供するプロトコル。

    将来的に LLM やユーザー入力に差し替え可能。
    """

    last_thinking: str

    def discuss(self, game: GameState, player: Player) -> DiscussResult:
        """議論フェーズでの発言と思考を返す。"""
        ...

    def vote(self, game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
        """投票先プレイヤー名を返す。"""
        ...

    def divine(self, game: GameState, seer: Player, candidates: tuple[Player, ...]) -> str:
        """占い対象プレイヤー名を返す。"""
        ...

    def attack(self, game: GameState, werewolf: Player, candidates: tuple[Player, ...]) -> str:
        """襲撃対象プレイヤー名を返す。"""
        ...

    def guard(self, game: GameState, knight: Player, candidates: tuple[Player, ...]) -> str:
        """護衛対象プレイヤー名を返す。"""
        ...
