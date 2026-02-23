import random
import sys
from pathlib import Path

# scripts/ はパッケージではないため、sys.path に追加してインポートする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from benchmark import PLAYER_NAMES, run_benchmark, run_single_game  # noqa: E402

from llm_werewolf.engine.action_provider import ActionProvider  # noqa: E402
from llm_werewolf.engine.random_provider import RandomActionProvider  # noqa: E402


def _random_factory(rng: random.Random) -> dict[str, ActionProvider]:
    return {name: RandomActionProvider() for name in PLAYER_NAMES}


class TestRunSingleGame:
    """run_single_game() の戻り値を検証するテスト。"""

    def test_result_contains_log_field(self) -> None:
        """結果辞書に log フィールドが含まれること。"""
        result = run_single_game(_random_factory, random.Random(0))

        assert "log" in result

    def test_log_is_list_of_strings(self) -> None:
        """log フィールドが文字列のリストであること。"""
        result = run_single_game(_random_factory, random.Random(0))

        assert isinstance(result["log"], list)
        assert all(isinstance(entry, str) for entry in result["log"])

    def test_log_is_not_empty(self) -> None:
        """ゲーム実行後のログが空でないこと。"""
        result = run_single_game(_random_factory, random.Random(0))

        assert len(result["log"]) > 0

    def test_result_contains_all_expected_keys(self) -> None:
        """結果辞書が全ての期待されるキーを持つこと。"""
        result = run_single_game(_random_factory, random.Random(0))

        expected_keys = {"winner", "turns", "api_calls", "average_latency", "guard_success_count", "log"}
        assert set(result.keys()) == expected_keys

    def test_guard_success_count_is_non_negative(self) -> None:
        """護衛成功回数が 0 以上であること。"""
        result = run_single_game(_random_factory, random.Random(0))

        assert result["guard_success_count"] >= 0


class TestRunBenchmark:
    """run_benchmark() の統計集計を検証するテスト。"""

    def test_summary_contains_guard_stats(self) -> None:
        """summary に護衛成功の統計が含まれること。"""
        result = run_benchmark(2, _random_factory, "random")
        summary = result["summary"]

        assert "total_guard_successes" in summary
        assert "average_guard_successes" in summary
        assert summary["total_guard_successes"] >= 0
        assert summary["average_guard_successes"] >= 0
