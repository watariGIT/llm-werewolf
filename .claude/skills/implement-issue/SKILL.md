---
name: implement-issue
description: GitHub Issue を読み込み、フィーチャーブランチで実装し、リント・テスト通過後に PR を作成するワークフロー。ユーザーが「/implement-issue #3」「Issue を実装して」「この Issue をやって」などと言ったときに使う。Issue 番号や URL を受け取って、ブランチ作成から PR 作成まで一気通貫で実行する。
---

# Implement Issue

GitHub Issue に基づいてコードを実装し、PR を作成するスキル。Issue の取得からブランチ作成、実装、リント・テスト、PR 作成までの全工程を扱う。

## 引数の解析

ユーザーの入力から Issue 番号を抽出する:

- `/implement-issue #3` → 3
- `/implement-issue 3` → 3
- `/implement-issue https://github.com/.../issues/3` → 3

## ワークフロー

### Step 1: Issue の取得

```bash
gh issue view <番号>
```

Issue のタイトル・本文・ラベルを読み取り、何を実装すべきか把握する。ラベルに `bug` があれば修正タスク（`fix/` ブランチ）、それ以外は機能追加（`feature/` ブランチ）と判断する。

### Step 2: worktree の作成

git worktree を使い、メインの作業ツリーを汚さずに独立した環境で作業する。

```bash
# master を最新にする
git fetch origin master

# worktree を作成（origin/master ベースのブランチ付き）
git worktree add .worktrees/<branch-name> -b <prefix>/<issue番号>-<短い説明> origin/master

# 以降の全作業は worktree 内で行う
cd .worktrees/<branch-name>
```

- **機能追加**: `feature/<issue番号>-<説明>` (例: `feature/3-add-voting-phase`)
- **バグ修正**: `fix/<issue番号>-<説明>` (例: `fix/7-fix-role-assignment`)
- 説明は Issue タイトルから英語ケバブケースで作る
- **以降の Step 3〜9 は全て worktree ディレクトリ内で実行する**

### Step 3: 設計と承認

EnterPlanMode を使って実装計画をユーザーに提示する。計画には以下を含める:

1. 変更対象ファイルの一覧
2. 新規作成するファイルの一覧
3. 主要な設計方針
4. テスト方針
5. **ドキュメント・設定の更新計画**（以下を必ず確認し、変更が必要なものを計画に含める）
   - `docs/architecture.md` — アーキテクチャ図・レイヤー構成の更新
   - `docs/glossary.md` — 新しい用語の追加
   - `docs/game-rules.md` — ルール変更がある場合
   - `.claude/rules/` 配下 — レイヤー依存・ドメイン・エンジン等のルール更新
   - `src/llm_werewolf/*/__init__.py` — 公開 API（エクスポート）の更新

ユーザーが計画を承認するまで実装に入らないこと。これはユーザーが期待と違う方向に進むのを防ぐために重要。

### Step 4: 実装

承認された計画に基づいてコードを書く。

- CLAUDE.md のコーディング規約に従う（Ruff line-length=120、スネークケース等）
- 型ヒントを付ける
- 必要に応じて `tests/` にテストを追加する
- **ドキュメント・設定ファイルも忘れずに更新する**（Step 3 で計画したもの）

### Step 5: リント・テスト

worktree 内で依存をインストールしてからチェックを実行する。エラーがあれば修正して再実行:

```bash
uv sync
uv run ruff format .
uv run tox
```

- pytest がテストファイル未検出で exit code 5 を返す場合、テストがまだないだけなので問題ない。
- tox が lint / typecheck / test を一括実行する。

### Step 6: コミット・プッシュ

```bash
git add <変更ファイル>
git commit -m "<日本語の簡潔なコミットメッセージ>"
git push -u origin <ブランチ名>
```

- `.env` や秘密情報を含むファイルは絶対にコミットしない
- `git add .` ではなく変更ファイルを個別に指定する

### Step 7: PR 作成

```bash
gh pr create --title "<簡潔なタイトル>" --body "$(cat <<'EOF'
## 概要
<変更内容の要約>

## 関連 Issue
Closes #<issue番号>

## 変更内容
- <箇条書きで変更点を列挙>

## テスト
- <テスト内容を記載>
EOF
)"
```

- `Closes #<番号>` でマージ時に Issue を自動クローズする
- PR の URL をユーザーに報告する

### Step 8: レビュー

PR 作成後、`/review-pr` スキルを実行してコードレビューを行う。

### Step 9: レビュー指摘対応

レビューで指摘があれば、ユーザーの確認を待たずに `/fix-review` スキルを実行して修正を対応する。

ただし `/fix-review` 内の Step 2「指摘の分類とユーザー確認」も省略し、自動で分類・修正を進めること。implement-issue ワークフロー全体でユーザー確認が必要なのは Step 3（設計と承認）のみ。

### Step 10: worktree のクリーンアップ

マージ完了後、worktree を削除する。

```bash
# メインのリポジトリルートに戻る
cd <元のリポジトリルート>
git worktree remove .worktrees/<branch-name>
```
