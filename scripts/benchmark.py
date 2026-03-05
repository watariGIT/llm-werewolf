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
from tqdm import tqdm

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_werewolf.domain.services import check_victory, create_game  # noqa: E402
from llm_werewolf.domain.value_objects import Phase, Team  # noqa: E402
from llm_werewolf.engine.action_provider import ActionProvider  # noqa: E402
from llm_werewolf.engine.game_engine import GameEngine  # noqa: E402
from llm_werewolf.engine.game_master import GameMasterProvider  # noqa: E402
from llm_werewolf.engine.metrics import (  # noqa: E402
    ActionMetrics,
    GameMetrics,
    MetricsCollectingProvider,
    estimate_cost,
)
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


def _collect_gm_tokens(gm_provider: GameMasterProvider, gm_metrics: GameMetrics) -> None:
    """GM-AI プロバイダーから直近のトークン使用量を読み取り、メトリクスに記録する。"""
    input_tokens: int = getattr(gm_provider, "last_input_tokens", 0)
    output_tokens: int = getattr(gm_provider, "last_output_tokens", 0)
    cache_read: int = getattr(gm_provider, "last_cache_read_input_tokens", 0)
    if input_tokens > 0 or output_tokens > 0:
        gm_metrics.actions.append(ActionMetrics("gm_summary", "GM-AI", 0.0, input_tokens, output_tokens, cache_read))


def _aggregate_token_stats(results: list[dict[str, Any]], prefix: str) -> dict[str, int]:
    """結果リストからトークン統計を集計する。"""
    input_t = sum(r[f"{prefix}_input_tokens"] for r in results)
    output_t = sum(r[f"{prefix}_output_tokens"] for r in results)
    cache_t = sum(r[f"{prefix}_cache_read_input_tokens"] for r in results)
    return {
        "input_tokens": input_t,
        "output_tokens": output_t,
        "cache_read_input_tokens": cache_t,
        "total_tokens": input_t + output_t,
    }


def run_single_game(
    provider_factory: ProviderFactory,
    rng: random.Random,
    model_name: str | None = None,
    on_phase_end: Callable[..., None] | None = None,
    gm_provider: GameMasterProvider | None = None,
    gm_model_name: str | None = None,
) -> dict[str, Any]:
    """1ゲームを実行し、結果を辞書で返す。"""
    game = create_game(PLAYER_NAMES, rng=rng)
    base_providers = provider_factory(rng)
    providers, metrics_list = _wrap_with_metrics(base_providers)

    # GM-AI メトリクス収集用
    gm_metrics = GameMetrics()

    def _on_phase_end_with_gm(game_state: Any) -> None:
        # 昼フェーズ完了時（Day 2以降）に GM-AI トークンを収集
        if gm_provider is not None and game_state.phase == Phase.DAY and game_state.day >= 2:
            _collect_gm_tokens(gm_provider, gm_metrics)
        if on_phase_end is not None:
            on_phase_end(game_state)

    engine = GameEngine(game, providers, rng=rng, on_phase_end=_on_phase_end_with_gm, gm_provider=gm_provider)
    final_state = engine.run()

    winner = check_victory(final_state)
    winner_str = winner.value if winner else "unknown"

    # Player AI メトリクス集計
    total_calls = sum(m.total_api_calls for m in metrics_list)
    all_latencies = [a.elapsed_seconds for m in metrics_list for a in m.actions]
    avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0

    player_input = sum(m.total_input_tokens for m in metrics_list)
    player_output = sum(m.total_output_tokens for m in metrics_list)
    player_cache = sum(m.total_cache_read_input_tokens for m in metrics_list)
    player_cost = estimate_cost(model_name or "", player_input, player_output, player_cache)

    # GM-AI メトリクス集計
    gm_input = gm_metrics.total_input_tokens
    gm_output = gm_metrics.total_output_tokens
    gm_cache = gm_metrics.total_cache_read_input_tokens
    gm_cost = estimate_cost(gm_model_name or "", gm_input, gm_output, gm_cache)

    # 合計
    total_input = player_input + gm_input
    total_output = player_output + gm_output
    total_cache = player_cache + gm_cache
    total_tokens = total_input + total_output

    # 合計コスト
    total_cost: float | None = None
    if player_cost is not None and gm_cost is not None:
        total_cost = player_cost + gm_cost
    elif player_cost is not None:
        total_cost = player_cost

    # 護衛成功回数をログから集計
    guard_success_count = sum(1 for entry in final_state.log if "[護衛成功]" in entry)

    result: dict[str, Any] = {
        "winner": winner_str,
        "turns": final_state.day - 1,
        "api_calls": total_calls,
        "average_latency": round(avg_latency, 4),
        "guard_success_count": guard_success_count,
        # 合計トークン（後方互換）
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cache_read_input_tokens": total_cache,
        "total_tokens": total_tokens,
        # Player AI 内訳
        "player_input_tokens": player_input,
        "player_output_tokens": player_output,
        "player_cache_read_input_tokens": player_cache,
        # GM-AI 内訳
        "gm_input_tokens": gm_input,
        "gm_output_tokens": gm_output,
        "gm_cache_read_input_tokens": gm_cache,
        "log": list(final_state.log),
    }
    if total_cost is not None:
        result["estimated_cost_usd"] = round(total_cost, 6)
    if player_cost is not None:
        result["player_estimated_cost_usd"] = round(player_cost, 6)
    if gm_cost is not None:
        result["gm_estimated_cost_usd"] = round(gm_cost, 6)
    return result


def _format_phase_status(game_state: Any) -> str:
    """GameState からフェーズ表示文字列を生成する。"""
    phase_label = "昼" if game_state.phase.value == "day" else "夜"
    alive_count = len(game_state.alive_players)
    return f"Day {game_state.day} {phase_label} (生存{alive_count}人)"


def run_benchmark(
    games_count: int,
    provider_factory: ProviderFactory,
    provider_type: str,
    model_name: str | None = None,
    gm_provider: GameMasterProvider | None = None,
    gm_model_name: str | None = None,
) -> dict[str, Any]:
    """指定回数のゲームを実行し、統計を集計する。"""
    results: list[dict[str, Any]] = []

    pbar = tqdm(range(games_count), desc=f"{provider_type} ベンチマーク", unit="game")
    for i in pbar:
        rng = random.Random(i)

        def on_phase_end(game_state: Any) -> None:
            pbar.set_postfix_str(_format_phase_status(game_state))

        result = run_single_game(
            provider_factory,
            rng,
            model_name=model_name,
            on_phase_end=on_phase_end,
            gm_provider=gm_provider,
            gm_model_name=gm_model_name,
        )
        result["game_index"] = i
        results.append(result)
        winner_label = "村人" if result["winner"] == "village" else "人狼"
        pbar.set_postfix_str(f"完了: {winner_label}勝利, {result['turns']}ターン")

    # 統計集計
    village_wins = sum(1 for r in results if r["winner"] == Team.VILLAGE.value)
    werewolf_wins = sum(1 for r in results if r["winner"] == Team.WEREWOLF.value)
    total_turns = sum(r["turns"] for r in results)
    total_calls = sum(r["api_calls"] for r in results)
    all_latencies = [r["average_latency"] for r in results if r["api_calls"] > 0]
    total_guard_successes = sum(r["guard_success_count"] for r in results)

    # 合計トークン統計
    total_input_tokens = sum(r["total_input_tokens"] for r in results)
    total_output_tokens = sum(r["total_output_tokens"] for r in results)
    total_cache_read = sum(r["total_cache_read_input_tokens"] for r in results)
    total_tokens = total_input_tokens + total_output_tokens

    # Player / GM 内訳
    player_stats = _aggregate_token_stats(results, "player")
    gm_stats = _aggregate_token_stats(results, "gm")

    # コスト計算
    player_cost = estimate_cost(
        model_name or "",
        player_stats["input_tokens"],
        player_stats["output_tokens"],
        player_stats["cache_read_input_tokens"],
    )
    gm_cost = estimate_cost(
        gm_model_name or "",
        gm_stats["input_tokens"],
        gm_stats["output_tokens"],
        gm_stats["cache_read_input_tokens"],
    )
    total_cost: float | None = None
    if player_cost is not None and gm_cost is not None:
        total_cost = player_cost + gm_cost
    elif player_cost is not None:
        total_cost = player_cost

    metadata: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "games_count": games_count,
        "provider_type": provider_type,
    }
    if model_name:
        metadata["model_name"] = model_name
    if gm_model_name:
        metadata["gm_model_name"] = gm_model_name

    summary: dict[str, Any] = {
        "village_win_rate": round(village_wins / games_count, 4) if games_count > 0 else 0,
        "werewolf_win_rate": round(werewolf_wins / games_count, 4) if games_count > 0 else 0,
        "average_turns": round(total_turns / games_count, 2) if games_count > 0 else 0,
        "total_api_calls": total_calls,
        "average_latency": round(sum(all_latencies) / len(all_latencies), 4) if all_latencies else 0,
        "total_guard_successes": total_guard_successes,
        "average_guard_successes": round(total_guard_successes / games_count, 2) if games_count > 0 else 0,
        # 合計トークン
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cache_read_input_tokens": total_cache_read,
        "cache_hit_rate": round(total_cache_read / total_input_tokens, 4) if total_input_tokens > 0 else 0,
        "total_tokens": total_tokens,
        "average_tokens_per_game": round(total_tokens / games_count) if games_count > 0 else 0,
        # Player AI 内訳
        "player_input_tokens": player_stats["input_tokens"],
        "player_output_tokens": player_stats["output_tokens"],
        "player_cache_read_input_tokens": player_stats["cache_read_input_tokens"],
        "player_total_tokens": player_stats["total_tokens"],
        # GM-AI 内訳
        "gm_input_tokens": gm_stats["input_tokens"],
        "gm_output_tokens": gm_stats["output_tokens"],
        "gm_cache_read_input_tokens": gm_stats["cache_read_input_tokens"],
        "gm_total_tokens": gm_stats["total_tokens"],
    }
    if total_cost is not None:
        summary["total_estimated_cost_usd"] = round(total_cost, 6)
        summary["average_cost_per_game_usd"] = round(total_cost / games_count, 6) if games_count > 0 else 0
    if player_cost is not None:
        summary["player_estimated_cost_usd"] = round(player_cost, 6)
    if gm_cost is not None:
        summary["gm_estimated_cost_usd"] = round(gm_cost, 6)

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
    if "gm_model_name" in meta:
        print(f"  GM-AI モデル: {meta['gm_model_name']}")
    print(f"  ゲーム数: {meta['games_count']}")
    print(f"  村人陣営勝率: {summary['village_win_rate']:.1%}")
    print(f"  人狼陣営勝率: {summary['werewolf_win_rate']:.1%}")
    print(f"  平均ターン数: {summary['average_turns']:.2f}")
    print(f"  API 呼び出し回数: {summary['total_api_calls']}")
    print(f"  平均レイテンシ: {summary['average_latency']:.4f}s")
    print(f"  護衛成功回数: {summary['total_guard_successes']} (平均: {summary['average_guard_successes']:.2f})")

    # 合計トークン
    input_t = summary["total_input_tokens"]
    output_t = summary["total_output_tokens"]
    cache_t = summary["total_cache_read_input_tokens"]
    print(f"  トークン合計: {summary['total_tokens']:,} (入力: {input_t:,}, 出力: {output_t:,})")
    print(f"  キャッシュ済み入力: {cache_t:,} (ヒット率: {summary['cache_hit_rate']:.1%})")
    print(f"  平均トークン/ゲーム: {summary['average_tokens_per_game']:,}")

    # Player / GM 内訳
    p_total = summary["player_total_tokens"]
    g_total = summary["gm_total_tokens"]
    if p_total > 0 or g_total > 0:
        p_in = summary["player_input_tokens"]
        p_out = summary["player_output_tokens"]
        g_in = summary["gm_input_tokens"]
        g_out = summary["gm_output_tokens"]
        print(f"  [Player AI] トークン: {p_total:,} (入力: {p_in:,}, 出力: {p_out:,})")
        print(f"  [GM-AI]     トークン: {g_total:,} (入力: {g_in:,}, 出力: {g_out:,})")

    # コスト
    if "total_estimated_cost_usd" in summary:
        print(f"  推定コスト合計: ${summary['total_estimated_cost_usd']:.4f}")
        print(f"  推定コスト/ゲーム: ${summary['average_cost_per_game_usd']:.4f}")
    if "player_estimated_cost_usd" in summary and "gm_estimated_cost_usd" in summary:
        print(f"  [Player AI] 推定コスト: ${summary['player_estimated_cost_usd']:.4f}")
        print(f"  [GM-AI]     推定コスト: ${summary['gm_estimated_cost_usd']:.4f}")
    print("=" * 50)


def save_result(result: dict[str, Any], output_path: Path) -> None:
    """結果を JSON ファイルに保存する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n結果を保存しました: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 人狼ベンチマーク")
    parser.add_argument("--games", type=int, default=10, help="実行するゲーム数 (デフォルト: 10)")
    parser.add_argument("--compare-random", action="store_true", help="RandomActionProvider との比較も実行")
    parser.add_argument("--random-only", action="store_true", help="Random のみ実行 (API KEY 不要)")
    parser.add_argument("--output", type=str, default=None, help="結果の JSON 出力先")
    parser.add_argument("--env-file", default=".env", help="読み込む .env ファイルのパス (default: .env)")
    args = parser.parse_args()

    load_dotenv(dotenv_path=args.env_file)

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
        from llm_werewolf.engine.llm_config import load_gm_config, load_llm_config, load_prompt_config
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

        # GM-AI プロバイダーの生成
        gm_prov: GameMasterProvider | None = None
        gm_model: str | None = None
        try:
            gm_config = load_gm_config()
            gm_prov = GameMasterProvider(gm_config)
            gm_model = gm_config.model_name
        except ValueError:
            pass

        prompt_config = load_prompt_config()

        print(f"\n--- LLM ベンチマーク (model: {config.model_name}) ---")
        if gm_prov:
            print(f"  GM-AI: 有効 (model: {gm_model})")

        def llm_factory(rng: random.Random) -> dict[str, ActionProvider]:
            personalities = assign_personalities(len(PLAYER_NAMES), rng)
            return {
                name: LLMActionProvider(config, personality=build_personality(traits), prompt_config=prompt_config)
                for name, traits in zip(PLAYER_NAMES, personalities)
            }

        llm_result = run_benchmark(
            args.games,
            llm_factory,
            "llm",
            model_name=config.model_name,
            gm_provider=gm_prov,
            gm_model_name=gm_model,
        )
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
