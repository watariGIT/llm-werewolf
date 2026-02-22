import logging
import random

import pytest

from llm_werewolf.engine.response_parser import (
    DEFAULT_DISCUSS_MESSAGE,
    parse_candidate_response,
    parse_discuss_response,
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
