# CLAUDE.md — プロジェクト指示書

## 基本ルール

- 日本語で応答すること
- パッケージ管理には必ず **uv** を使用（pip禁止）
- コマンド実行例: `uv sync`, `uv run pytest`, `uv run ruff check .`

## プロジェクト構成

- **src layout** を採用: `src/llm_werewolf/` がパッケージルート
- Web FW: FastAPI + Jinja2（テンプレートは `src/llm_werewolf/templates/`）
- LLM連携: LangChain → OpenAI API
- Python 3.12

## コーディング規約

- Ruff でフォーマット・リント（line-length=120）
- mypy で型チェック
- テストは pytest（`tests/` ディレクトリ）
- 変数名・関数名はスネークケース、クラス名はパスカルケース

## 重要な制約

- `.env` には秘密情報を含むため git にコミットしない
- LLMのAPIキーはすべて環境変数経由で取得する（ハードコード禁止）
- ゲーム構成: 5人（村人3, 占い師1, 人狼1）

## よく使うコマンド

```bash
uv sync                  # 依存関係インストール
uv run ruff check .      # リント
uv run ruff format .     # フォーマット
uv run mypy src/         # 型チェック
uv run pytest            # テスト実行
```
