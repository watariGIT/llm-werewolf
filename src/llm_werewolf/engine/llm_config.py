"""LLM 設定の管理。

環境変数から OpenAI API の設定およびプロンプト設定を読み込み、バリデーションを行う。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODEL_NAME = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.7

GM_DEFAULT_MODEL = "gpt-4o-mini"
GM_DEFAULT_TEMPERATURE = 0.3

DEFAULT_MAX_RECENT_STATEMENTS = 20


@dataclass(frozen=True)
class LLMConfig:
    """LLM の設定を保持する値オブジェクト。"""

    model_name: str
    temperature: float
    api_key: str


def load_llm_config() -> LLMConfig:
    """環境変数から LLMConfig を生成する。

    Raises:
        ValueError: OPENAI_API_KEY が未設定または空文字の場合
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("環境変数 OPENAI_API_KEY が設定されていません")

    model_name = os.environ.get("OPENAI_MODEL_NAME", DEFAULT_MODEL_NAME).strip()

    temperature_str = os.environ.get("OPENAI_TEMPERATURE", "").strip()
    if temperature_str:
        try:
            temperature = float(temperature_str)
        except ValueError:
            raise ValueError(f"OPENAI_TEMPERATURE の値が不正です: {temperature_str!r}")
        if not (0.0 <= temperature <= 2.0):
            raise ValueError(f"OPENAI_TEMPERATURE は 0.0〜2.0 の範囲で指定してください: {temperature}")
    else:
        temperature = DEFAULT_TEMPERATURE

    return LLMConfig(model_name=model_name, temperature=temperature, api_key=api_key)


@dataclass(frozen=True)
class PromptConfig:
    """プロンプト生成に関する設定を保持する値オブジェクト。"""

    max_recent_statements: int = DEFAULT_MAX_RECENT_STATEMENTS


def load_prompt_config() -> PromptConfig:
    """環境変数から PromptConfig を生成する。

    環境変数:
        MAX_RECENT_STATEMENTS: 保持する直近の発言ログ件数（デフォルト: 20）
    """
    max_recent_str = os.environ.get("MAX_RECENT_STATEMENTS", "").strip()
    if max_recent_str:
        try:
            max_recent = int(max_recent_str)
        except ValueError:
            raise ValueError(f"MAX_RECENT_STATEMENTS の値が不正です: {max_recent_str!r}")
        if max_recent < 0:
            raise ValueError(f"MAX_RECENT_STATEMENTS は 0 以上で指定してください: {max_recent}")
        return PromptConfig(max_recent_statements=max_recent)

    return PromptConfig()


def load_gm_config() -> LLMConfig:
    """GM-AI 用の LLMConfig を環境変数から生成する。

    GM_MODEL_NAME, GM_TEMPERATURE でプレイヤー AI とは独立に指定可能。
    API キーは OPENAI_API_KEY を共有する。

    Raises:
        ValueError: OPENAI_API_KEY が未設定または空文字の場合
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("環境変数 OPENAI_API_KEY が設定されていません")

    model_name = os.environ.get("GM_MODEL_NAME", GM_DEFAULT_MODEL).strip()

    temperature_str = os.environ.get("GM_TEMPERATURE", "").strip()
    if temperature_str:
        try:
            temperature = float(temperature_str)
        except ValueError:
            raise ValueError(f"GM_TEMPERATURE の値が不正です: {temperature_str!r}")
        if not (0.0 <= temperature <= 2.0):
            raise ValueError(f"GM_TEMPERATURE は 0.0〜2.0 の範囲で指定してください: {temperature}")
    else:
        temperature = GM_DEFAULT_TEMPERATURE

    return LLMConfig(model_name=model_name, temperature=temperature, api_key=api_key)
