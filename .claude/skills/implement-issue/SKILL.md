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

Issue のタイトル・本文・ラベルを読み取り、何を実装すべきか把握する。ラベルに `bug` があれば修正タスク、なければ機能追加と判断する。

### Step 2: ブランチの作成

master を最新にしてからブランチを切る。

```bash
git checkout master
git pull origin master
git checkout -b <prefix>/<issue番号>-<短い説明>
```

- **機能追加**: `feature/<issue番号>-<説明>` (例: `feature/3-add-voting-phase`)
- **バグ修正**: `fix/<issue番号>-<説明>` (例: `fix/7-fix-role-assignment`)
- 説明は Issue タイトルから英語ケバブケースで作る

### Step 3: 設計と承認

EnterPlanMode を使って実装計画をユーザーに提示する。計画には以下を含める:

1. 変更対象ファイルの一覧
2. 新規作成するファイルの一覧
3. 主要な設計方針
4. テスト方針

ユーザーが計画を承認するまで実装に入らないこと。これはユーザーが期待と違う方向に進むのを防ぐために重要。

### Step 4: 実装

承認された計画に基づいてコードを書く。

- CLAUDE.md のコーディング規約に従う（Ruff line-length=120、スネークケース等）
- 型ヒントを付ける
- 必要に応じて `tests/` にテストを追加する

### Step 5: リント・テスト

コミット前に全て通すこと。エラーがあれば修正して再実行:

```bash
uv run ruff format .
uv run tox
```

pytest がテストファイル未検出で exit code 5 を返す場合、テストがまだないだけなので問題ない。

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

レビューで指摘があれば `/fix-review` スキルを実行して修正を対応する。
