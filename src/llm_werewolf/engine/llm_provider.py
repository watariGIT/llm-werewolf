"""LLM ベースの ActionProvider 実装。

LangChain + OpenAI API を使用して AI プレイヤーの行動を生成する。
API エラー時はリトライ（指数バックオフ）を行い、上限到達時はフォールバック動作で代替する。
"""

from __future__ import annotations

import logging
import random
import time

import openai
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

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
FALLBACK_DISCUSS_MESSAGE = "（通信エラーのため発言できませんでした）"


class LLMActionProvider:
    """LLM ベースのプレイヤー行動プロバイダー。

    ActionProvider Protocol に準拠し、LangChain + OpenAI API で
    AI プレイヤーの議論・投票・占い・襲撃の行動を生成する。
    API エラー時は最大3回リトライし、失敗時はフォールバック動作で代替する。
    """

    def __init__(self, config: LLMConfig, rng: random.Random | None = None) -> None:
        self._llm = ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            api_key=SecretStr(config.api_key),
        )
        self._rng = rng if rng is not None else random.Random()

    def _sleep(self, seconds: float) -> None:
        """スリープ処理。テスト時にモック可能。"""
        time.sleep(seconds)

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str | None:
        """LLM を呼び出してレスポンステキストを返す。

        API エラー時は指数バックオフで最大 MAX_RETRIES 回リトライする。
        リトライ上限到達時は None を返す。
        """
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        for attempt in range(MAX_RETRIES):
            try:
                response = self._llm.invoke(messages)
                return str(response.content)
            except (openai.APITimeoutError, openai.RateLimitError) as e:
                wait = 2**attempt
                logger.warning(
                    "LLM API エラー (試行 %d/%d): %s。%d秒後にリトライします。", attempt + 1, MAX_RETRIES, e, wait
                )
                self._sleep(wait)
            except openai.APIStatusError as e:
                if e.status_code >= 500:
                    wait = 2**attempt
                    logger.warning(
                        "LLM API サーバーエラー %d (試行 %d/%d): %s。%d秒後にリトライします。",
                        e.status_code,
                        attempt + 1,
                        MAX_RETRIES,
                        e,
                        wait,
                    )
                    self._sleep(wait)
                else:
                    logger.warning("LLM API クライアントエラー %d: %s。リトライしません。", e.status_code, e)
                    return None
        logger.warning("LLM API リトライ上限 (%d回) に到達しました。フォールバック動作に切り替えます。", MAX_RETRIES)
        return None

    def discuss(self, game: GameState, player: Player) -> str:
        """議論フェーズでの発言を LLM で生成する。"""
        system_prompt = build_system_prompt(player.role)
        user_prompt = build_discuss_prompt(game, player)
        response = self._call_llm(system_prompt, user_prompt)
        if response is None:
            logger.warning("discuss フォールバック: プレイヤー %s の発言を定型文で代替します。", player.name)
            return FALLBACK_DISCUSS_MESSAGE
        return parse_discuss_response(response)

    def vote(self, game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
        """投票先を LLM で選択する。"""
        system_prompt = build_system_prompt(player.role)
        user_prompt = build_vote_prompt(game, player, candidates)
        response = self._call_llm(system_prompt, user_prompt)
        candidate_names = tuple(c.name for c in candidates)
        if response is None:
            selected = self._rng.choice(candidate_names)
            logger.warning(
                "vote フォールバック: プレイヤー %s の投票先をランダムで %s に決定しました。", player.name, selected
            )
            return selected
        return parse_candidate_response(response, candidate_names, self._rng, action_type="vote")

    def divine(self, game: GameState, seer: Player, candidates: tuple[Player, ...]) -> str:
        """占い対象を LLM で選択する。"""
        system_prompt = build_system_prompt(seer.role)
        user_prompt = build_divine_prompt(game, seer, candidates)
        response = self._call_llm(system_prompt, user_prompt)
        candidate_names = tuple(c.name for c in candidates)
        if response is None:
            selected = self._rng.choice(candidate_names)
            logger.warning(
                "divine フォールバック: 占い師 %s の占い対象をランダムで %s に決定しました。", seer.name, selected
            )
            return selected
        return parse_candidate_response(response, candidate_names, self._rng, action_type="divine")

    def attack(self, game: GameState, werewolf: Player, candidates: tuple[Player, ...]) -> str:
        """襲撃対象を LLM で選択する。"""
        system_prompt = build_system_prompt(werewolf.role)
        user_prompt = build_attack_prompt(game, werewolf, candidates)
        response = self._call_llm(system_prompt, user_prompt)
        candidate_names = tuple(c.name for c in candidates)
        if response is None:
            selected = self._rng.choice(candidate_names)
            logger.warning(
                "attack フォールバック: 人狼 %s の襲撃対象をランダムで %s に決定しました。", werewolf.name, selected
            )
            return selected
        return parse_candidate_response(response, candidate_names, self._rng, action_type="attack")
