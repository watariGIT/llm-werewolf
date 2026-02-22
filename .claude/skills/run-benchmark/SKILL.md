# Run Benchmark

LLM AI の品質を定量的に評価するためのベンチマークをワンコマンドで実行する。

## 引数の解析

ユーザーの入力からオプションを抽出する:

- `/run-benchmark` → デフォルト（10ゲーム、LLM のみ）
- `/run-benchmark 20` → 20ゲーム実行
- `/run-benchmark 20 --compare` → 20ゲーム、Random との比較あり
- `/run-benchmark --random-only` → Random のみ（API KEY 不要）

## ワークフロー

### Step 1: 環境チェック

`--random-only` でなければ、OPENAI_API_KEY が設定されているか確認する。

```bash
# 環境変数の確認（値は表示しない）
echo $OPENAI_API_KEY | head -c 3
```

設定されていなければユーザーに通知して中断する。

### Step 2: ベンチマーク実行

```bash
cd <プロジェクトルート>
uv run python scripts/benchmark.py --games <N> [--compare-random] [--random-only]
```

### Step 3: 結果表示

実行結果のサマリーをユーザーに報告する:

- 村人陣営 / 人狼陣営の勝率
- 平均ターン数
- API 呼び出し回数と平均レイテンシ
- 結果 JSON ファイルのパス

比較モードの場合は、LLM と Random の差分も報告する。
