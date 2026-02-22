"""LLM レスポンスのパースとバリデーション。

LLM が返すテキスト応答を解析し、ゲームアクションに変換する。
無効な応答時はフォールバックとしてランダム選択を行う。
"""

from __future__ import annotations

import logging
import random

logger = logging.getLogger(__name__)

DEFAULT_DISCUSS_MESSAGE = "..."


def parse_discuss_response(response: str) -> str:
    """議論レスポンスをパースする。

    空文字列の場合はデフォルトメッセージを返す。
    それ以外はそのまま返す。

    Args:
        response: LLM の応答テキスト

    Returns:
        議論用の発言テキスト
    """
    stripped = response.strip()
    if not stripped:
        return DEFAULT_DISCUSS_MESSAGE
    return stripped


def parse_candidate_response(
    response: str,
    candidates: tuple[str, ...],
    rng: random.Random,
    action_type: str = "vote",
) -> str:
    """候補者選択レスポンスをパースする。

    以下の優先順位でマッチングを行う:
    1. 完全一致: 応答テキストを strip した結果が候補者名と一致
    2. 部分一致: 候補者名が応答テキスト内に含まれる（候補者リスト順で最初のマッチ）
    3. フォールバック: ランダム選択 + WARNING ログ

    Args:
        response: LLM の応答テキスト
        candidates: 候補者名のタプル
        rng: 乱数生成器（フォールバック時のランダム選択用）
        action_type: アクション種別（ログ出力用。"vote", "divine", "attack"）

    Returns:
        選択された候補者名

    Raises:
        ValueError: candidates が空の場合
    """
    if not candidates:
        raise ValueError("candidates must not be empty")

    stripped = response.strip()

    # 1. 完全一致
    if stripped in candidates:
        return stripped

    # 2. 部分一致（候補者リスト順で最初のマッチ）
    for candidate in candidates:
        if candidate in stripped:
            return candidate

    # 3. フォールバック
    selected = rng.choice(candidates)
    logger.warning(
        "LLM の %s 応答をパースできませんでした (応答=%r, 候補=%s)。ランダムで %s を選択します。",
        action_type,
        stripped,
        candidates,
        selected,
    )
    return selected
