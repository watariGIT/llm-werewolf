# CLAUDE.md — プロジェクト指示書

## 基本ルール

- 日本語で応答すること
- パッケージ管理には必ず **uv** を使用（pip禁止）

- テストは pytest（`tests/` ディレクトリ）

## プロジェクト構成

- **src layout** を採用: `src/llm_werewolf/` がパッケージルート
- Web FW: FastAPI + Jinja2（テンプレートは `src/llm_werewolf/templates/`）
- LLM連携: LangChain → OpenAI API
- Python 3.12

## リファレンス

- ゲームルール: [docs/game-rules.md](docs/game-rules.md)
- 用語集: [docs/glossary.md](docs/glossary.md)
- アーキテクチャ: [docs/architecture.md](docs/architecture.md)

## 現在の開発フェーズ

- **Step 1: Mock版** — AI はランダム行動。LLM は使わない
- 詳細は README.md のロードマップを参照
- 各 Step のタスクは着手時に GitHub Issues で管理する

## よく使うコマンド

```bash
uv sync                  # 依存関係インストール
uv run tox               # リント・型チェック・テスト一括実行
```

## 開発ワークフロー

### ブランチ運用

- `master` が本流ブランチ。直接コミットしない
- 機能追加: `feature/<issue番号>-<短い説明>` (例: `feature/3-add-voting-phase`)
- バグ修正: `fix/<issue番号>-<短い説明>` (例: `fix/7-fix-role-assignment`)
- PR のマージ先は常に `master`

### コミット前チェック（必須）

```bash
uv run ruff format .     # フォーマット適用
uv run tox               # リント・型チェック・テスト一括通過
```

### 標準作業フロー

1. GitHub Issue を確認し、要件を把握する
2. `feature/` または `fix/` ブランチを作成する
3. プランモードで設計 → ユーザー承認後に実装
4. リント・テストを通してからコミット・プッシュ
5. `gh pr create` で PR を作成する
6. `/review-pr` で PR レビュー（結果は PR コメントに投稿） → `/fix-review` で指摘修正
7. ユーザー確認後にマージ

### GitHub CLI リファレンス

```bash
gh issue view <番号>                                          # Issue 参照
gh pr create --title "..." --body "..."                       # PR 作成
gh pr diff                                                    # PR 差分
gh pr comment <番号> --body "..."                              # PR コメント投稿
gh api repos/{owner}/{repo}/pulls/{number}/comments           # PRコメント取得
```
