# LLM人狼 (LLM Werewolf)

AI人狼ゲーム — 1人のプレイヤーが4体のAIと人狼を遊ぶWebアプリケーション。

## ゲームルール

- **プレイヤー数**: 5人（人間1 + AI4）
- **役職**: 村人3、占い師1、人狼1（ランダム配役）
- 昼フェーズで議論・投票 → 最多得票者を処刑
- 夜フェーズで人狼が襲撃、占い師が占い
- 人狼を処刑すれば村人陣営の勝利、村人の数が人狼以下になれば人狼陣営の勝利

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
| 1 | Mock版: ローカル動作、AI はランダム行動 | 進行中 |
| 2 | ChatGPT 導入: ランダム→LLM に置換 | 未着手 |
| 3 | GCP 移行: Cloud Run デプロイ（開発者のみ） | 未着手 |
| 4 | 拡張: 役職追加・人数変更・UX改善 | 未着手 |

### Step 1: Mock版
ローカルで動作する人狼ゲームの基盤を作る。AI プレイヤーはランダムに投票・能力使用する。昼議論→投票→処刑→夜行動の一連のフローを実装。LLM は使用しない。

### Step 2: ChatGPT 導入
Mock版のランダム行動を LangChain + OpenAI API に置き換える。AI が議論に参加し、推理に基づいて投票するようにする。

### Step 3: GCP 移行
Cloud Run にデプロイし、Web 経由でプレイ可能にする。この段階では利用者は開発者のみ。

### Step 4: 拡張
役職追加（騎士・霊媒師等）、プレイヤー人数の変更、メモ機能などの UX 改善。

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

# 開発サーバー起動（実装後）
uv run uvicorn src.llm_werewolf.main:app --reload
```

### リント・型チェック

```bash
uv run ruff check .
uv run mypy src/
```
