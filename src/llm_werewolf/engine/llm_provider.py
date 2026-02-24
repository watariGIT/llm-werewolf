"""LLM ベースの ActionProvider 実装。

LangChain + OpenAI API を使用して AI プレイヤーの行動を生成する。
API エラー時はリトライ（指数バックオフ）を行い、上限到達時はフォールバック動作で代替する。
各 API 呼び出しのプロンプト・レスポンス・レイテンシ・トークン使用量をログ出力する。
"""

from __future__ import annotations

import logging
import random
import time
from typing import NamedTuple

import openai
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.engine.llm_config import LLMConfig
from llm_werewolf.engine.prompts import (
    build_attack_prompt,
    build_discuss_prompt,
    build_divine_prompt,
    build_guard_prompt,
    build_system_prompt,
    build_vote_prompt,
)
from llm_werewolf.engine.response_parser import parse_candidate_response, parse_discuss_response

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
FALLBACK_DISCUSS_MESSAGE = "（通信エラーのため発言できませんでした）"


class CandidateDecision(BaseModel):
    """候補者選択の構造化レスポンス。"""

    target: str = Field(description="選択した候補者の名前（候補者リストから正確に1つ選択）")
    reason: str = Field(description="選択理由（1文）")


class _LLMResult(NamedTuple):
    """LLM 呼び出し結果を保持する内部データ型。"""

    content: str
    elapsed: float
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0


class _StructuredLLMResult(NamedTuple):
    """構造化 LLM 呼び出し結果を保持する内部データ型。"""

    decision: CandidateDecision
    elapsed: float
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0


class LLMActionProvider:
    """LLM ベースのプレイヤー行動プロバイダー。

    ActionProvider Protocol に準拠し、LangChain + OpenAI API で
    AI プレイヤーの議論・投票・占い・襲撃の行動を生成する。
    API エラー時は最大3回リトライし、失敗時はフォールバック動作で代替する。
    """

    def __init__(self, config: LLMConfig, rng: random.Random | None = None, personality: str = "") -> None:
        self._llm = ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            api_key=SecretStr(config.api_key),
        )
        self._rng = rng if rng is not None else random.Random()
        self._personality = personality
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0
        self.last_cache_read_input_tokens: int = 0
        self._discuss_day: int = 0
        self._discuss_messages: list[SystemMessage | HumanMessage | AIMessage] = []

    def _sleep(self, seconds: float) -> None:
        """スリープ処理。テスト時にモック可能。"""
        time.sleep(seconds)

    def _update_token_usage(self, result: _LLMResult | _StructuredLLMResult | None) -> None:
        """最新のトークン使用量を更新する。"""
        if result is not None:
            self.last_input_tokens = result.input_tokens
            self.last_output_tokens = result.output_tokens
            self.last_cache_read_input_tokens = result.cache_read_input_tokens
        else:
            self.last_input_tokens = 0
            self.last_output_tokens = 0
            self.last_cache_read_input_tokens = 0

    def _call_llm_structured(self, system_prompt: str, user_prompt: str) -> _StructuredLLMResult | None:
        """構造化出力で LLM を呼び出し、CandidateDecision を返す。

        API エラー時は指数バックオフで最大 MAX_RETRIES 回リトライする。
        リトライ上限到達時は None を返す。
        """
        structured_llm = self._llm.with_structured_output(CandidateDecision, include_raw=True)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        logger.debug("LLM 構造化出力プロンプト:\n  system: %s\n  user: %s", system_prompt, user_prompt)
        for attempt in range(MAX_RETRIES):
            try:
                start = time.monotonic()
                response = structured_llm.invoke(messages)
                elapsed = time.monotonic() - start
                parsed = response.get("parsed") if isinstance(response, dict) else response
                if not isinstance(parsed, CandidateDecision):
                    logger.warning("構造化出力のパースに失敗しました。フォールバックします。")
                    return None
                logger.debug("LLM 構造化レスポンス: target=%s, reason=%s", parsed.target, parsed.reason)
                input_tokens = 0
                output_tokens = 0
                cache_read = 0
                if isinstance(response, dict):
                    raw = response.get("raw")
                    usage = getattr(raw, "usage_metadata", None) if raw else None
                    if usage:
                        input_tokens = usage.get("input_tokens", 0)
                        output_tokens = usage.get("output_tokens", 0)
                        details = usage.get("input_token_details", {})
                        if details:
                            cache_read = details.get("cache_read", 0)
                        logger.debug(
                            "トークン使用量: input=%d, output=%d, total=%d, cache_read=%d",
                            input_tokens,
                            output_tokens,
                            input_tokens + output_tokens,
                            cache_read,
                        )
                return _StructuredLLMResult(
                    decision=parsed,
                    elapsed=elapsed,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_input_tokens=cache_read,
                )
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
            except Exception as e:
                logger.warning("構造化出力の処理中に予期しない例外が発生しました: %s。フォールバックします。", e)
                return None
        logger.warning("LLM API リトライ上限 (%d回) に到達しました。フォールバック動作に切り替えます。", MAX_RETRIES)
        return None

    def _call_llm_with_messages(self, messages: list[SystemMessage | HumanMessage | AIMessage]) -> _LLMResult | None:
        """メッセージリストを直接指定して LLM を呼び出す。

        API エラー時は指数バックオフで最大 MAX_RETRIES 回リトライする。
        リトライ上限到達時は None を返す。
        """
        logger.debug("LLM プロンプト (messages=%d):\n  %s", len(messages), messages)
        for attempt in range(MAX_RETRIES):
            try:
                start = time.monotonic()
                response = self._llm.invoke(messages)
                elapsed = time.monotonic() - start
                content = str(response.content)
                logger.debug("LLM レスポンス: %s", content)
                usage = getattr(response, "usage_metadata", None)
                input_tokens = 0
                output_tokens = 0
                cache_read = 0
                if usage:
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    details = usage.get("input_token_details", {})
                    if details:
                        cache_read = details.get("cache_read", 0)
                    logger.debug(
                        "トークン使用量: input=%d, output=%d, total=%d, cache_read=%d",
                        input_tokens,
                        output_tokens,
                        input_tokens + output_tokens,
                        cache_read,
                    )
                return _LLMResult(
                    content=content,
                    elapsed=elapsed,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_input_tokens=cache_read,
                )
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

    def _call_llm(self, system_prompt: str, user_prompt: str) -> _LLMResult | None:
        """LLM を呼び出してレスポンステキストとメタデータを返す。

        _call_llm_with_messages への委譲ラッパー。
        """
        messages: list[SystemMessage | HumanMessage | AIMessage] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        return self._call_llm_with_messages(messages)

    def _prepend_personality(self, user_prompt: str) -> str:
        """ユーザープロンプトの先頭に人格タグを付加する。"""
        if self._personality:
            return f"{self._personality}\n\n{user_prompt}"
        return user_prompt

    def discuss(self, game: GameState, player: Player) -> str:
        """議論フェーズでの発言を LLM で生成する。

        同一日内の複数ラウンドでは会話履歴を保持し、
        前回の発言コンテキストを LLM に渡すことで文脈連続性を向上させる。
        日が変わると履歴はリセットされる。
        """
        system_prompt = build_system_prompt(player.role)
        user_prompt = self._prepend_personality(build_discuss_prompt(game, player))

        # 日が変わったら履歴をリセット
        if game.day != self._discuss_day:
            self._discuss_day = game.day
            self._discuss_messages = []

        if not self._discuss_messages:
            # ラウンド1: 新規メッセージリスト
            messages: list[SystemMessage | HumanMessage | AIMessage] = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        else:
            # ラウンド2+: 既存履歴に新しいコンテキストを追加
            messages = list(self._discuss_messages)
            messages.append(HumanMessage(content=user_prompt))

        result = self._call_llm_with_messages(messages)
        self._update_token_usage(result)

        if result is None:
            logger.warning("discuss フォールバック: プレイヤー %s の発言を定型文で代替します。", player.name)
            return FALLBACK_DISCUSS_MESSAGE

        logger.info("LLM アクション完了: player=%s, action=discuss, elapsed=%.2fs", player.name, result.elapsed)
        response_text = parse_discuss_response(result.content)

        # 履歴を更新（成功時のみ）
        if not self._discuss_messages:
            self._discuss_messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
                AIMessage(content=response_text),
            ]
        else:
            self._discuss_messages.append(HumanMessage(content=user_prompt))
            self._discuss_messages.append(AIMessage(content=response_text))

        return response_text

    def _select_candidate(
        self,
        system_prompt: str,
        user_prompt: str,
        candidate_names: tuple[str, ...],
        player_name: str,
        action_type: str,
    ) -> str:
        """構造化出力で候補者を選択する共通メソッド。

        1. 構造化出力で CandidateDecision を取得
        2. target が候補者リストに含まれればそのまま返却
        3. target が候補者リストに含まれなければ parse_candidate_response でフォールバック
        4. API エラー時はランダムフォールバック
        """
        result = self._call_llm_structured(system_prompt, user_prompt)
        self._update_token_usage(result)
        if result is None:
            selected = self._rng.choice(candidate_names)
            logger.warning(
                "%s フォールバック: プレイヤー %s の選択をランダムで %s に決定しました。",
                action_type,
                player_name,
                selected,
            )
            return selected
        decision = result.decision
        logger.info(
            "LLM アクション完了: player=%s, action=%s, elapsed=%.2fs, reason=%s",
            player_name,
            action_type,
            result.elapsed,
            decision.reason,
        )
        if decision.target in candidate_names:
            return decision.target
        return parse_candidate_response(decision.target, candidate_names, self._rng, action_type=action_type)

    def vote(self, game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
        """投票先を LLM で選択する。"""
        system_prompt = build_system_prompt(player.role)
        user_prompt = self._prepend_personality(build_vote_prompt(game, player, candidates))
        candidate_names = tuple(c.name for c in candidates)
        return self._select_candidate(system_prompt, user_prompt, candidate_names, player.name, "vote")

    def divine(self, game: GameState, seer: Player, candidates: tuple[Player, ...]) -> str:
        """占い対象を LLM で選択する。"""
        system_prompt = build_system_prompt(seer.role)
        user_prompt = self._prepend_personality(build_divine_prompt(game, seer, candidates))
        candidate_names = tuple(c.name for c in candidates)
        return self._select_candidate(system_prompt, user_prompt, candidate_names, seer.name, "divine")

    def attack(self, game: GameState, werewolf: Player, candidates: tuple[Player, ...]) -> str:
        """襲撃対象を LLM で選択する。"""
        system_prompt = build_system_prompt(werewolf.role)
        user_prompt = self._prepend_personality(build_attack_prompt(game, werewolf, candidates))
        candidate_names = tuple(c.name for c in candidates)
        return self._select_candidate(system_prompt, user_prompt, candidate_names, werewolf.name, "attack")

    def guard(self, game: GameState, knight: Player, candidates: tuple[Player, ...]) -> str:
        """護衛対象を LLM で選択する。"""
        system_prompt = build_system_prompt(knight.role)
        user_prompt = self._prepend_personality(build_guard_prompt(game, knight, candidates))
        candidate_names = tuple(c.name for c in candidates)
        return self._select_candidate(system_prompt, user_prompt, candidate_names, knight.name, "guard")
