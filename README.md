# LLM人狼 (LLM Werewolf)

AI人狼ゲーム — 1人のプレイヤーが4体のAIと人狼を遊ぶWebアプリケーション。

## ゲームルール

5人（人間1 + AI4）で遊ぶ人狼ゲーム。詳細は [docs/game-rules.md](docs/game-rules.md) を参照。

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
| 2 | ChatGPT 導入: ランダム→LLM に置換 | 進行中 |
| 3 | GCP 移行: Cloud Run デプロイ（開発者のみ） | 未着手 |
| 4 | 拡張: 役職追加・人数変更・UX改善 | 未着手 |

### Step 1: Mock版 ✅
ローカルで動作する人狼ゲームの基盤を作る。AI プレイヤーはランダムに投票・能力使用する。昼議論→投票→処刑→夜行動の一連のフローを実装。LLM は使用しない。

### Step 2: ChatGPT 導入 🚧
Mock版のランダム行動を LangChain + OpenAI API に置き換える。AI が議論に参加し、推理に基づいて投票するようにする。

**Future Scope（Step 2 以降で検討）:**
- プロンプトチューニング基盤（バージョン管理・A/Bテスト・外部ファイル化）
- モデル/Temperature 設定 UI（ゲーム作成時に Web UI から選択）
- LLM コスト管理（トークン使用量トラッキング・コスト上限）
- AI 人格設定（プレイヤーごとに異なる性格・口調をプロンプトで制御）
- ストリーミングレスポンス（議論発言のストリーミング表示）

### Step 3: GCP 移行
Cloud Run にデプロイし、Web 経由でプレイ可能にする。この段階では利用者は開発者のみ。

### Step 4: 拡張
役職追加（騎士・霊媒師等）、プレイヤー人数の変更、メモ機能などの UX 改善。

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
uv run uvicorn llm_werewolf.main:app --reload
```

サーバー起動後、ブラウザで http://127.0.0.1:8000 にアクセスしてゲームをプレイできます。

### リント・型チェック・テスト

```bash
uv run tox               # リント・型チェック・テスト一括実行
```

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
