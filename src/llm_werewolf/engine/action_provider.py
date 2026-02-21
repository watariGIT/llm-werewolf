from typing import Protocol

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player


class ActionProvider(Protocol):
    """プレイヤーの行動を提供するプロトコル。

    将来的に LLM やユーザー入力に差し替え可能。
    """

    def discuss(self, game: GameState, player: Player) -> str:
        """議論フェーズでの発言を返す。"""
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
