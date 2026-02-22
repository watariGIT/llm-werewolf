---
name: fix-review
description: PR のレビュー指摘を読み込み、修正可能な問題を修正してプッシュする。対応困難な問題は GitHub Issue を作成する。「/fix-review」「レビュー指摘を修正して」「レビュー対応して」と言ったときに使う。直前の /review-pr の結果も参照する。
---

# Fix Review

PR レビューの指摘事項を修正するスキル。レビューコメントやチャット履歴から指摘を収集し、修正可能なものを直してプッシュする。

## 引数の解析

- `/fix-review` → 現在のブランチに紐づく PR の指摘を修正
- `/fix-review 5` or `/fix-review #5` → PR #5 の指摘を修正

## ワークフロー

### Step 0: 作業ディレクトリの確認

PR のブランチに対応する worktree が存在するか確認し、worktree 内で作業する。

```bash
BRANCH_NAME=$(gh pr view <番号> --json headRefName -q .headRefName)
if [ -d ".worktrees/$BRANCH_NAME" ]; then
  cd .worktrees/$BRANCH_NAME
else
  git worktree add .worktrees/$BRANCH_NAME $BRANCH_NAME
  cd .worktrees/$BRANCH_NAME
fi
```

以降の全 Step は worktree ディレクトリ内で実行する。

### Step 1: 指摘事項の収集

2つのソースから指摘を集める:

**GitHub の PR コメント・レビューコメント:**

```bash
gh pr view --json number,title,url,comments
gh api repos/{owner}/{repo}/pulls/<番号>/comments
gh api repos/{owner}/{repo}/pulls/<番号>/reviews
```

`/review-pr` が投稿したレビューコメント（「コードレビュー結果」セクション）も PR コメントとして取得できる。

**チャット履歴:**
直前の `/review-pr` の結果がチャット履歴にあれば、補足情報として参照する。

### Step 2: 指摘の分類とユーザー確認

各指摘を以下に分類する:

- **即時修正可能** — コード修正で今すぐ対応できるもの
- **Issue 作成** — 大規模な変更が必要でこの PR では対応しないもの

分類結果をユーザーに提示し、確認を取る。ユーザーが分類を変更したい場合は修正する。確認なしで修正に入らないこと。

### Step 3: 修正の実施

「即時修正可能」に分類された指摘を修正する。

- CLAUDE.md のコーディング規約に従う
- 修正箇所ごとに何を直したか把握しておく（Step 7 で報告する）

### Step 4: リント・テスト

```bash
uv run ruff format .
uv run tox
```

エラーがあれば修正して再実行。

### Step 5: コミット・プッシュ

```bash
git add <変更ファイル>
git commit -m "レビュー指摘を修正"
git push
```

### Step 6: Issue 作成（対応困難な問題がある場合）

「Issue 作成」に分類された指摘がある場合、`/create-issue` スキルを使って Issue を作成する。

指摘ごとに以下の情報を `/create-issue` に渡す:

- **ゴール**: 指摘された問題の解決
- **背景**: PR #<番号> のレビューで発見された問題であること、指摘内容の詳細
- **変更方針**: 推奨する対応方針
- **対応時期**: この PR では対応しない旨と、適切な対応時期

### Step 7: PR に修正結果をコメント投稿

修正内容を PR のコメントとして投稿する。記録として残すために、チャットでの報告だけでなく必ず PR にも投稿すること。

```bash
gh pr comment <番号> --body "$(cat <<'EOF'
## レビュー指摘修正完了

| 指摘 | 修正内容 |
|------|---------|
| <指摘内容> | <修正内容> |

<マージ可能かどうかの判断>
EOF
)"
```

### Step 8: 結果報告

以下をユーザーに報告する:

1. 修正した指摘事項の一覧
2. 作成した Issue の一覧（番号と URL）
3. PR がマージ可能な状態かどうかの判断

マージ可能であれば、ユーザーにマージ確認を促す。
