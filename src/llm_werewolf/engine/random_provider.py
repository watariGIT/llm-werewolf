import random

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.engine.action_provider import DiscussResult

DUMMY_MESSAGES: tuple[str, ...] = (
    "うーん、誰が人狼だろう…",
    "昨日の夜、怪しい動きをした人がいた気がする。",
    "みんなの意見を聞きたいな。",
    "自分は村人だよ。信じてほしい。",
    "ちょっと気になる人がいるんだけど…",
    "まだ情報が少ないから慎重に行こう。",
    "誰かが嘘をついている気がする。",
    "投票先を決めないといけないね。",
)


class RandomActionProvider:
    """全行動をランダムで実行するダミーAI。"""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng if rng is not None else random.Random()
        self.last_thinking: str = ""

    def discuss(self, game: GameState, player: Player) -> DiscussResult:
        return DiscussResult(message=self._rng.choice(DUMMY_MESSAGES))

    def vote(self, game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
        return self._rng.choice(candidates).name

    def divine(self, game: GameState, seer: Player, candidates: tuple[Player, ...]) -> str:
        return self._rng.choice(candidates).name

    def attack(self, game: GameState, werewolf: Player, candidates: tuple[Player, ...]) -> str:
        return self._rng.choice(candidates).name

    def guard(self, game: GameState, knight: Player, candidates: tuple[Player, ...]) -> str:
        return self._rng.choice(candidates).name
