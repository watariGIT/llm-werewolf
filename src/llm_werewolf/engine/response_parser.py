"""LLM レスポンスのパースとバリデーション。

LLM が返すテキスト応答を解析し、ゲームアクションに変換する。
無効な応答時はフォールバックとしてランダム選択を行う。
"""

from __future__ import annotations

import logging
import random

logger = logging.getLogger(__name__)

DEFAULT_DISCUSS_MESSAGE = "..."


_SPEECH_MARKER = "【発言】"
_THINKING_MARKER = "【思考】"


def parse_discussion_text(full_text: str) -> tuple[str, str]:
    """【思考】/【発言】形式テキストをパースし (thinking, message) を返す。

    Args:
        full_text: LLM が返したテキスト全体

    Returns:
        (thinking, message) のタプル。【発言】が見つからない場合はテキスト全体を message とする。
    """
    speech_pos = full_text.find(_SPEECH_MARKER)
    if speech_pos < 0:
        # セパレータなし: テキスト全体を message として扱う
        stripped = full_text.strip()
        if not stripped:
            return ("", DEFAULT_DISCUSS_MESSAGE)
        return ("", stripped)

    thinking_part = full_text[:speech_pos]
    message_part = full_text[speech_pos + len(_SPEECH_MARKER) :]

    # 【思考】マーカーを除去
    thinking = thinking_part.replace(_THINKING_MARKER, "").strip()
    message = message_part.strip()
    if not message:
        message = DEFAULT_DISCUSS_MESSAGE
    return (thinking, message)


def extract_speech_delta(buffer: str, prev_buffer_len: int) -> str:
    """バッファ全体から【発言】セクション内のデルタ（新規追加分）のみを返す。

    【発言】がまだ見つからない場合は空文字を返す（チャンク境界分割対策）。

    Args:
        buffer: 現在までに蓄積されたテキスト全体
        prev_buffer_len: 前回のバッファ長

    Returns:
        【発言】セクション内の新規追加テキスト
    """
    speech_pos = buffer.find(_SPEECH_MARKER)
    if speech_pos < 0:
        return ""

    speech_content_start = speech_pos + len(_SPEECH_MARKER)
    # デルタの開始位置: 前回バッファ長と発言セクション開始位置の大きい方
    delta_start = max(speech_content_start, prev_buffer_len)
    if delta_start >= len(buffer):
        return ""
    return buffer[delta_start:]


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
    # LLM 構造化出力でエスケープされた改行リテラルを実際の改行に変換
    stripped = stripped.replace("\\n", "\n")
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
