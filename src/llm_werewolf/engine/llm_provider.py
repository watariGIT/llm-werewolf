"""LLM ベースの ActionProvider 実装。

LangChain + OpenAI API を使用して AI プレイヤーの行動を生成する。
"""

from __future__ import annotations

import random

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.engine.llm_config import LLMConfig
from llm_werewolf.engine.prompts import (
    build_attack_prompt,
    build_discuss_prompt,
    build_divine_prompt,
    build_system_prompt,
    build_vote_prompt,
)
from llm_werewolf.engine.response_parser import parse_candidate_response, parse_discuss_response


class LLMActionProvider:
    """LLM ベースのプレイヤー行動プロバイダー。

    ActionProvider Protocol に準拠し、LangChain + OpenAI API で
    AI プレイヤーの議論・投票・占い・襲撃の行動を生成する。
    """

    def __init__(self, config: LLMConfig, rng: random.Random | None = None) -> None:
        self._llm = ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            api_key=SecretStr(config.api_key),
        )
        self._rng = rng if rng is not None else random.Random()

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """LLM を呼び出してレスポンステキストを返す。"""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self._llm.invoke(messages)
        return str(response.content)

    def discuss(self, game: GameState, player: Player) -> str:
        """議論フェーズでの発言を LLM で生成する。"""
        system_prompt = build_system_prompt(player.role)
        user_prompt = build_discuss_prompt(game, player)
        response = self._call_llm(system_prompt, user_prompt)
        return parse_discuss_response(response)

    def vote(self, game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
        """投票先を LLM で選択する。"""
        system_prompt = build_system_prompt(player.role)
        user_prompt = build_vote_prompt(game, player, candidates)
        response = self._call_llm(system_prompt, user_prompt)
        candidate_names = tuple(c.name for c in candidates)
        return parse_candidate_response(response, candidate_names, self._rng, action_type="vote")

    def divine(self, game: GameState, seer: Player, candidates: tuple[Player, ...]) -> str:
        """占い対象を LLM で選択する。"""
        system_prompt = build_system_prompt(seer.role)
        user_prompt = build_divine_prompt(game, seer, candidates)
        response = self._call_llm(system_prompt, user_prompt)
        candidate_names = tuple(c.name for c in candidates)
        return parse_candidate_response(response, candidate_names, self._rng, action_type="divine")

    def attack(self, game: GameState, werewolf: Player, candidates: tuple[Player, ...]) -> str:
        """襲撃対象を LLM で選択する。"""
        system_prompt = build_system_prompt(werewolf.role)
        user_prompt = build_attack_prompt(game, werewolf, candidates)
        response = self._call_llm(system_prompt, user_prompt)
        candidate_names = tuple(c.name for c in candidates)
        return parse_candidate_response(response, candidate_names, self._rng, action_type="attack")
