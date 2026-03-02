# LLM人狼 (LLM Werewolf)

AI人狼ゲーム — 1人のプレイヤーが8体のAIと人狼を遊ぶWebアプリケーション。

## ゲームルール

9人（人間1 + AI8）で遊ぶ人狼ゲーム。詳細は [docs/game-rules.md](docs/game-rules.md) を参照。

## 技術スタック

| 項目 | 技術 |
|------|------|
| Web FW | FastAPI + Jinja2 |
| LLM連携 | LangChain + OpenAI API |
| Python | 3.12 |
| パッケージ管理 | uv |
| Linter/Formatter | Ruff + mypy |
| デプロイ先 | Cloud Run（将来） |

## ロードマップ

| Step | 内容 | 状態 |
|------|------|------|
| 1 | Mock版: ローカル動作、AI はランダム行動 | 完了 |
| 2 | ChatGPT 導入: ランダム→LLM に置換 | 完了 |
| 3 | 9人村移行: 役職追加・人数拡張 | 進行中 |
| 4 | GCP 移行: Cloud Run デプロイ（開発者のみ） | 未着手 |

### Step 1: Mock版 ✅
ローカルで動作する人狼ゲームの基盤を作る。AI プレイヤーはランダムに投票・能力使用する。昼議論→投票→処刑→夜行動の一連のフローを実装。LLM は使用しない。

### Step 2: ChatGPT 導入 ✅
Mock版のランダム行動を LangChain + OpenAI API に置き換える。AI が議論に参加し、推理に基づいて投票するようにする。

**Future Scope（Step 2 以降で検討）:**
- プロンプトチューニング基盤（バージョン管理・A/Bテスト・外部ファイル化）
- モデル/Temperature 設定 UI（ゲーム作成時に Web UI から選択）
- LLM コスト管理（トークン使用量トラッキング・コスト上限）
- AI 人格設定（プレイヤーごとに異なる性格・口調をプロンプトで制御）
- ストリーミングレスポンス（議論発言のストリーミング表示）

### Step 3: 9人村移行
5人村（村人3, 占い師1, 人狼1）から9人村（人狼2, 狩人1, 占い師1, 霊媒師1, 狂人1, 村人3）に拡張する。新役職の夜行動（護衛・霊媒）、人狼の相互認識、代表襲撃などのゲームメカニクスを追加。

### Step 4: GCP 移行
Cloud Run にデプロイし、Web 経由でプレイ可能にする。この段階では利用者は開発者のみ。

## ゲームモード

本プロジェクトには2つのゲームモードがあります。

| モード | 用途 | インターフェース |
|--------|------|-----------------|
| インタラクティブモード | ユーザーがAIと対戦する本来のゲーム体験 | Web UI (`/play`) |
| 一括実行モード | AI同士の自動対戦。開発・デバッグ・AI品質評価用 | JSON API (`/games`) |

- **インタラクティブモード** がメインのゲームモードです。ブラウザからアクセスして遊びます。
- **一括実行モード** はユーザー向けの機能ではなく、開発用の内部ツールです。Step 2 以降で LLM を導入した際に、自動対戦によるAIの品質評価・ベンチマークに活用します。

## セットアップ

### 前提条件

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

### 手順

```bash
# 依存関係のインストール
uv sync

# 環境変数の設定
cp .env.example .env
# .env を編集して OPENAI_API_KEY を設定

# 開発サーバー起動
uv run python -m llm_werewolf --reload

# LLM デバッグモード（プロンプト・レスポンス・トークン数を表示）
uv run python -m llm_werewolf --llm-debug --reload
```

サーバー起動後、ブラウザで http://127.0.0.1:8000 にアクセスしてゲームをプレイできます。

### OpenAI API キーの設定

AI プレイヤーの動作に OpenAI API を使用するため、API キーの設定が必要です。

1. [OpenAI Platform](https://platform.openai.com/api-keys) でAPIキーを取得
2. プロジェクトルートに `.env` ファイルを作成（`.env.example` をコピー）

```bash
cp .env.example .env
```

3. `.env` ファイルを編集し、取得したAPIキーを設定

```
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

以下の設定もオプションで変更可能です:

| 環境変数 | 説明 | デフォルト値 |
|----------|------|-------------|
| `OPENAI_API_KEY` | OpenAI API キー（必須） | — |
| `OPENAI_MODEL_NAME` | プレイヤー AI のモデル名 | `gpt-4o-mini` |
| `OPENAI_TEMPERATURE` | プレイヤー AI の応答のランダム性（0.0〜2.0） | `0.7` |
| `GM_MODEL_NAME` | GM-AI（盤面整理AI）のモデル名 | `gpt-4o-mini` |
| `GM_TEMPERATURE` | GM-AI の応答のランダム性（0.0〜2.0） | `0.3` |
| `MAX_RECENT_STATEMENTS` | LLM に渡す直近の発言ログ件数上限 | `20` |

`OPENAI_API_KEY` が未設定の場合、起動時にエラーメッセージが表示されサーバーは起動しません。

### リント・型チェック・テスト

```bash
uv run tox               # リント・型チェック・テスト一括実行
uv run tox -e integration # 結合テスト（OPENAI_API_KEY 必須）
```

### ベンチマーク

LLM AI の品質を定量的に評価するためのベンチマークスクリプト。

```bash
# Random のみ（API KEY 不要）
uv run python scripts/benchmark.py --games 10 --random-only

# LLM ベンチマーク（OPENAI_API_KEY 必須）
uv run python scripts/benchmark.py --games 10

# LLM と Random の比較
uv run python scripts/benchmark.py --games 10 --compare-random

# 出力先を指定
uv run python scripts/benchmark.py --games 10 --output results.json
```

結果は `benchmark_results/` に JSON 形式で出力されます。集計される統計:

- 陣営別勝率（村人陣営 / 人狼陣営）
- 平均ゲームターン数
- LLM API 呼び出し回数・平均レイテンシ
- 護衛成功回数（合計・平均）

## ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [docs/game-rules.md](docs/game-rules.md) | ゲームルール詳細 |
| [docs/glossary.md](docs/glossary.md) | 用語集 |
| [docs/architecture.md](docs/architecture.md) | アーキテクチャ設計 |
| [CLAUDE.md](CLAUDE.md) | プロジェクト指示書 |

## Claude Code スキル

| スキル | 説明 |
|--------|------|
| `/implement-issue` | GitHub Issue の実装からPR作成まで一気通貫で実行 |
| `/review-pr` | PR の差分を6種のレビュアー観点で並列レビュー |
| `/fix-review` | レビュー指摘の修正・プッシュ、対応困難な問題はIssue作成 |
| `/run-benchmark` | ベンチマーク実行（環境チェック→実行→結果表示） |
| `/analyze-benchmark` | ベンチマーク結果の分析・改善提案 |
