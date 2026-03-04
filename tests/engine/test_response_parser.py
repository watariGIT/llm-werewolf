import logging
import random

import pytest

from llm_werewolf.engine.response_parser import (
    DEFAULT_DISCUSS_MESSAGE,
    extract_speech_delta,
    parse_candidate_response,
    parse_discuss_response,
    parse_discussion_text,
)


class TestParseDiscussResponse:
    """議論レスポンスパースのテスト。"""

    def test_normal_text_returned_as_is(self) -> None:
        assert parse_discuss_response("人狼は Bob だと思います") == "人狼は Bob だと思います"

    def test_empty_string_returns_default(self) -> None:
        assert parse_discuss_response("") == DEFAULT_DISCUSS_MESSAGE

    def test_whitespace_only_returns_default(self) -> None:
        assert parse_discuss_response("   ") == DEFAULT_DISCUSS_MESSAGE

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert parse_discuss_response("  hello  ") == "hello"

    def test_escaped_newline_converted_to_actual_newline(self) -> None:
        assert parse_discuss_response("こんにちは\\nよろしく") == "こんにちは\nよろしく"

    def test_multiple_escaped_newlines(self) -> None:
        assert parse_discuss_response("行1\\n行2\\n行3") == "行1\n行2\n行3"

    def test_actual_newline_preserved(self) -> None:
        assert parse_discuss_response("行1\n行2") == "行1\n行2"


class TestParseDiscussionText:
    """【思考】/【発言】形式パーサーのテスト。"""

    def test_normal_format(self) -> None:
        thinking, message = parse_discussion_text("【思考】戦略を考える【発言】Bobが怪しい")
        assert thinking == "戦略を考える"
        assert message == "Bobが怪しい"

    def test_thinking_only(self) -> None:
        thinking, message = parse_discussion_text("【思考】考え中")
        assert thinking == ""
        assert message == "【思考】考え中"

    def test_speech_only(self) -> None:
        thinking, message = parse_discussion_text("【発言】直接発言")
        assert thinking == ""
        assert message == "直接発言"

    def test_no_markers(self) -> None:
        thinking, message = parse_discussion_text("普通のテキスト")
        assert thinking == ""
        assert message == "普通のテキスト"

    def test_empty_string(self) -> None:
        thinking, message = parse_discussion_text("")
        assert thinking == ""
        assert message == DEFAULT_DISCUSS_MESSAGE

    def test_whitespace_in_sections(self) -> None:
        thinking, message = parse_discussion_text("【思考】 思考内容 【発言】 発言内容 ")
        assert thinking == "思考内容"
        assert message == "発言内容"

    def test_empty_message_returns_default(self) -> None:
        thinking, message = parse_discussion_text("【思考】考えた【発言】")
        assert thinking == "考えた"
        assert message == DEFAULT_DISCUSS_MESSAGE

    def test_multiline_content(self) -> None:
        text = "【思考】まず占い結果を確認\n次に投票先を決める【発言】Aliceに賛成です\n投票はBobにします"
        thinking, message = parse_discussion_text(text)
        assert "占い結果を確認" in thinking
        assert "Aliceに賛成です" in message


class TestExtractSpeechDelta:
    """ストリーミングデルタ抽出のテスト。"""

    def test_before_speech_marker(self) -> None:
        assert extract_speech_delta("【思考】考え中...", 0) == ""

    def test_speech_marker_just_appeared(self) -> None:
        buffer = "【思考】考えた【発言】こんにちは"
        delta = extract_speech_delta(buffer, 0)
        assert delta == "こんにちは"

    def test_incremental_delta(self) -> None:
        buffer1 = "【思考】考えた【発言】こん"
        buffer2 = "【思考】考えた【発言】こんにちは"
        prev_len = len(buffer1)
        delta = extract_speech_delta(buffer2, prev_len)
        assert delta == "にちは"

    def test_no_new_content(self) -> None:
        buffer = "【思考】考えた【発言】こんにちは"
        delta = extract_speech_delta(buffer, len(buffer))
        assert delta == ""

    def test_partial_marker(self) -> None:
        """チャンク境界で【発が途中の場合"""
        assert extract_speech_delta("【思考】考え【発", 0) == ""

    def test_speech_only_buffer(self) -> None:
        buffer = "【発言】テスト"
        delta = extract_speech_delta(buffer, 0)
        assert delta == "テスト"

    def test_delta_after_prev_in_speech(self) -> None:
        """prev_buffer_len が発言セクション内の場合"""
        buffer = "【発言】ABCDE"
        # 前回は "【発言】AB" まで (len=7)
        marker_end = len("【発言】")  # 4 (in chars: 【=1,発=1,言=1,】=1 -> 4 chars)
        prev_len = marker_end + 2  # "AB" の後
        delta = extract_speech_delta(buffer, prev_len)
        assert delta == "CDE"


class TestParseCandidateResponse:
    """候補者選択レスポンスパースのテスト。"""

    CANDIDATES = ("Alice", "Bob", "Charlie")

    # --- 正常系: 完全一致 ---
    def test_exact_match(self) -> None:
        rng = random.Random(42)
        result = parse_candidate_response("Bob", self.CANDIDATES, rng)
        assert result == "Bob"

    def test_exact_match_with_whitespace(self) -> None:
        rng = random.Random(42)
        result = parse_candidate_response("  Bob  ", self.CANDIDATES, rng)
        assert result == "Bob"

    # --- 正常系: 部分一致 ---
    def test_partial_match_candidate_in_sentence(self) -> None:
        rng = random.Random(42)
        result = parse_candidate_response("私は Alice に投票します", self.CANDIDATES, rng)
        assert result == "Alice"

    def test_partial_match_first_candidate_wins(self) -> None:
        """複数候補が含まれる場合、候補者リスト順で最初のマッチを返す。"""
        rng = random.Random(42)
        result = parse_candidate_response(
            "Alice と Bob のどちらかだけど Bob にする",
            self.CANDIDATES,
            rng,
        )
        assert result == "Alice"

    # --- 異常系: フォールバック ---
    def test_no_match_falls_back_to_random(self) -> None:
        rng = random.Random(42)
        result = parse_candidate_response("わからない", self.CANDIDATES, rng)
        assert result in self.CANDIDATES

    def test_fallback_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        rng = random.Random(42)
        with caplog.at_level(logging.WARNING):
            parse_candidate_response("わからない", self.CANDIDATES, rng, action_type="vote")
        assert "vote" in caplog.text
        assert "わからない" in caplog.text

    def test_fallback_is_deterministic_with_same_seed(self) -> None:
        r1 = parse_candidate_response("xxx", self.CANDIDATES, random.Random(99))
        r2 = parse_candidate_response("xxx", self.CANDIDATES, random.Random(99))
        assert r1 == r2

    # --- エッジケース ---
    def test_empty_response_falls_back(self) -> None:
        rng = random.Random(42)
        result = parse_candidate_response("", self.CANDIDATES, rng)
        assert result in self.CANDIDATES

    def test_empty_candidates_raises(self) -> None:
        rng = random.Random(42)
        with pytest.raises(ValueError, match="candidates must not be empty"):
            parse_candidate_response("Bob", (), rng)

    def test_single_candidate_fallback(self) -> None:
        rng = random.Random(42)
        result = parse_candidate_response("unknown", ("Alice",), rng)
        assert result == "Alice"

    def test_action_type_in_log(self, caplog: pytest.LogCaptureFixture) -> None:
        rng = random.Random(42)
        with caplog.at_level(logging.WARNING):
            parse_candidate_response("???", self.CANDIDATES, rng, action_type="divine")
        assert "divine" in caplog.text
