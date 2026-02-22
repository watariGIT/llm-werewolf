"""LLM 設定の管理。

環境変数から OpenAI API の設定を読み込み、バリデーションを行う。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODEL_NAME = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.7


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
