import random
import sys
from pathlib import Path

# scripts/ はパッケージではないため、sys.path に追加してインポートする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from benchmark import run_single_game  # noqa: E402

from llm_werewolf.engine.random_provider import RandomActionProvider  # noqa: E402


class TestRunSingleGame:
    """run_single_game() の戻り値を検証するテスト。"""

    def test_result_contains_log_field(self) -> None:
        """結果辞書に log フィールドが含まれること。"""
        result = run_single_game(RandomActionProvider, random.Random(0))

        assert "log" in result

    def test_log_is_list_of_strings(self) -> None:
        """log フィールドが文字列のリストであること。"""
        result = run_single_game(RandomActionProvider, random.Random(0))

        assert isinstance(result["log"], list)
        assert all(isinstance(entry, str) for entry in result["log"])

    def test_log_is_not_empty(self) -> None:
        """ゲーム実行後のログが空でないこと。"""
        result = run_single_game(RandomActionProvider, random.Random(0))

        assert len(result["log"]) > 0

    def test_result_contains_all_expected_keys(self) -> None:
        """結果辞書が全ての期待されるキーを持つこと。"""
        result = run_single_game(RandomActionProvider, random.Random(0))

        expected_keys = {"winner", "turns", "api_calls", "average_latency", "log"}
        assert set(result.keys()) == expected_keys
