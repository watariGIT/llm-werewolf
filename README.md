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
