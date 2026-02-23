"""LLM 人狼ベンチマークスクリプト。

指定回数のゲームを一括実行し、陣営別勝率・平均ターン数・
API 呼び出し回数・平均レイテンシ・トークン使用量・推定コスト等の統計を集計する。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_werewolf.domain.services import check_victory, create_game  # noqa: E402
from llm_werewolf.domain.value_objects import Team  # noqa: E402
from llm_werewolf.engine.action_provider import ActionProvider  # noqa: E402
from llm_werewolf.engine.game_engine import GameEngine  # noqa: E402
from llm_werewolf.engine.metrics import GameMetrics, MetricsCollectingProvider, estimate_cost  # noqa: E402
from llm_werewolf.engine.random_provider import RandomActionProvider  # noqa: E402

PLAYER_NAMES = ["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan"]


ProviderFactory = Callable[[random.Random], dict[str, ActionProvider]]


def _wrap_with_metrics(
    base_providers: dict[str, ActionProvider],
) -> tuple[dict[str, ActionProvider], list[GameMetrics]]:
    """全プレイヤー分の MetricsCollectingProvider でラップする。"""
    metrics_list: list[GameMetrics] = []
    providers: dict[str, ActionProvider] = {}
    for name in PLAYER_NAMES:
        gm = GameMetrics()
        metrics_list.append(gm)
        providers[name] = MetricsCollectingProvider(base_providers[name], gm)
    return providers, metrics_list


def run_single_game(
    provider_factory: ProviderFactory,
    rng: random.Random,
    model_name: str | None = None,
) -> dict[str, Any]:
    """1ゲームを実行し、結果を辞書で返す。"""
    game = create_game(PLAYER_NAMES, rng=rng)
    base_providers = provider_factory(rng)
    providers, metrics_list = _wrap_with_metrics(base_providers)

    engine = GameEngine(game, providers, rng=rng)
    final_state = engine.run()

    winner = check_victory(final_state)
    winner_str = winner.value if winner else "unknown"

    # メトリクス集計
    total_calls = sum(m.total_api_calls for m in metrics_list)
    all_latencies = [a.elapsed_seconds for m in metrics_list for a in m.actions]
    avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0

    # トークン集計
    total_input_tokens = sum(m.total_input_tokens for m in metrics_list)
    total_output_tokens = sum(m.total_output_tokens for m in metrics_list)
    total_tokens = total_input_tokens + total_output_tokens
    cost = estimate_cost(model_name or "", total_input_tokens, total_output_tokens)

    # 護衛成功回数をログから集計
    guard_success_count = sum(1 for entry in final_state.log if "[護衛成功]" in entry)

    result: dict[str, Any] = {
        "winner": winner_str,
        "turns": final_state.day - 1,
        "api_calls": total_calls,
        "average_latency": round(avg_latency, 4),
        "guard_success_count": guard_success_count,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "log": list(final_state.log),
    }
    if cost is not None:
        result["estimated_cost_usd"] = round(cost, 6)
    return result


def run_benchmark(
    games_count: int,
    provider_factory: ProviderFactory,
    provider_type: str,
    model_name: str | None = None,
) -> dict[str, Any]:
    """指定回数のゲームを実行し、統計を集計する。"""
    results: list[dict[str, Any]] = []

    for i in range(games_count):
        rng = random.Random(i)
        print(f"  ゲーム {i + 1}/{games_count} 実行中...", end="", flush=True)
        result = run_single_game(provider_factory, rng, model_name=model_name)
        result["game_index"] = i
        results.append(result)
        print(f" 完了 (勝者: {result['winner']}, ターン数: {result['turns']})")

    # 統計集計
    village_wins = sum(1 for r in results if r["winner"] == Team.VILLAGE.value)
    werewolf_wins = sum(1 for r in results if r["winner"] == Team.WEREWOLF.value)
    total_turns = sum(r["turns"] for r in results)
    total_calls = sum(r["api_calls"] for r in results)
    all_latencies = [r["average_latency"] for r in results if r["api_calls"] > 0]
    total_guard_successes = sum(r["guard_success_count"] for r in results)

    # トークン統計
    total_input_tokens = sum(r["total_input_tokens"] for r in results)
    total_output_tokens = sum(r["total_output_tokens"] for r in results)
    total_tokens = total_input_tokens + total_output_tokens
    total_cost = estimate_cost(model_name or "", total_input_tokens, total_output_tokens)

    metadata: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "games_count": games_count,
        "provider_type": provider_type,
    }
    if model_name:
        metadata["model_name"] = model_name

    summary: dict[str, Any] = {
        "village_win_rate": round(village_wins / games_count, 4) if games_count > 0 else 0,
        "werewolf_win_rate": round(werewolf_wins / games_count, 4) if games_count > 0 else 0,
        "average_turns": round(total_turns / games_count, 2) if games_count > 0 else 0,
        "total_api_calls": total_calls,
        "average_latency": round(sum(all_latencies) / len(all_latencies), 4) if all_latencies else 0,
        "total_guard_successes": total_guard_successes,
        "average_guard_successes": round(total_guard_successes / games_count, 2) if games_count > 0 else 0,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "average_tokens_per_game": round(total_tokens / games_count) if games_count > 0 else 0,
    }
    if total_cost is not None:
        summary["total_estimated_cost_usd"] = round(total_cost, 6)
        summary["average_cost_per_game_usd"] = round(total_cost / games_count, 6) if games_count > 0 else 0

    return {
        "metadata": metadata,
        "summary": summary,
        "games": results,
    }


def print_summary(result: dict[str, Any]) -> None:
    """ベンチマーク結果のサマリーを表示する。"""
    meta = result["metadata"]
    summary = result["summary"]

    print()
    print("=" * 50)
    print(f"ベンチマーク結果 ({meta['provider_type']})")
    print("=" * 50)
    if "model_name" in meta:
        print(f"  モデル: {meta['model_name']}")
    print(f"  ゲーム数: {meta['games_count']}")
    print(f"  村人陣営勝率: {summary['village_win_rate']:.1%}")
    print(f"  人狼陣営勝率: {summary['werewolf_win_rate']:.1%}")
    print(f"  平均ターン数: {summary['average_turns']:.2f}")
    print(f"  API 呼び出し回数: {summary['total_api_calls']}")
    print(f"  平均レイテンシ: {summary['average_latency']:.4f}s")
    print(f"  護衛成功回数: {summary['total_guard_successes']} (平均: {summary['average_guard_successes']:.2f})")
    input_t = summary["total_input_tokens"]
    output_t = summary["total_output_tokens"]
    print(f"  トークン合計: {summary['total_tokens']:,} (入力: {input_t:,}, 出力: {output_t:,})")
    print(f"  平均トークン/ゲーム: {summary['average_tokens_per_game']:,}")
    if "total_estimated_cost_usd" in summary:
        print(f"  推定コスト合計: ${summary['total_estimated_cost_usd']:.4f}")
        print(f"  推定コスト/ゲーム: ${summary['average_cost_per_game_usd']:.4f}")
    print("=" * 50)


def save_result(result: dict[str, Any], output_path: Path) -> None:
    """結果を JSON ファイルに保存する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n結果を保存しました: {output_path}")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="LLM 人狼ベンチマーク")
    parser.add_argument("--games", type=int, default=10, help="実行するゲーム数 (デフォルト: 10)")
    parser.add_argument("--compare-random", action="store_true", help="RandomActionProvider との比較も実行")
    parser.add_argument("--random-only", action="store_true", help="Random のみ実行 (API KEY 不要)")
    parser.add_argument("--output", type=str, default=None, help="結果の JSON 出力先")
    args = parser.parse_args()

    # 出力先の決定（デフォルトはプロジェクトルート内の benchmark_results/）
    project_root = Path(__file__).resolve().parent.parent
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        output_path = project_root / "benchmark_results" / f"result_{timestamp}.json"

    all_results: dict[str, Any] = {}

    # Random ベンチマーク
    if args.random_only or args.compare_random:
        print("\n--- Random ベンチマーク ---")

        def random_factory(rng: random.Random) -> dict[str, ActionProvider]:
            return {name: RandomActionProvider() for name in PLAYER_NAMES}

        random_result = run_benchmark(args.games, random_factory, "random")
        print_summary(random_result)
        all_results["random"] = random_result

    # LLM ベンチマーク
    if not args.random_only:
        from llm_werewolf.engine.llm_config import load_llm_config
        from llm_werewolf.engine.llm_provider import LLMActionProvider
        from llm_werewolf.engine.prompts import assign_personalities, build_personality

        try:
            config = load_llm_config()
        except ValueError as e:
            print(f"\nエラー: {e}", file=sys.stderr)
            print(
                "OPENAI_API_KEY を設定してください。Random のみで実行するには --random-only を使用してください。",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"\n--- LLM ベンチマーク (model: {config.model_name}) ---")

        def llm_factory(rng: random.Random) -> dict[str, ActionProvider]:
            personalities = assign_personalities(len(PLAYER_NAMES), rng)
            return {
                name: LLMActionProvider(config, personality=build_personality(traits))
                for name, traits in zip(PLAYER_NAMES, personalities)
            }

        llm_result = run_benchmark(args.games, llm_factory, "llm", model_name=config.model_name)
        print_summary(llm_result)
        all_results["llm"] = llm_result

    # 結果保存
    if len(all_results) == 1:
        save_result(next(iter(all_results.values())), output_path)
    else:
        combined: dict[str, Any] = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "games_count": args.games,
                "mode": "comparison",
            },
            "results": all_results,
        }
        save_result(combined, output_path)


if __name__ == "__main__":
    main()
