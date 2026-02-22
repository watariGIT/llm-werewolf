---
name: update-review-pr-skill
description: PRスコープ外の既存実装に起因するバグ・問題が見つかった際に、過去のレビューでなぜ漏れたかを分析し、review-pr スキルのレビュアー定義を改善する。「/update-review-pr-skill」「レビュースキルを改善して」と言ったときに使う。
---

# Update Review PR Skill

PRスコープ外の既存実装に起因するバグや問題が発見された場合に、過去のレビューでの検出漏れを分析し、`review-pr` スキルのレビュアー定義ファイル（`reviewers/*.md`）を改善するスキル。

## 引数の解析

ユーザーの入力から Issue 番号または PR 番号を抽出する:

- `/update-review-pr-skill #10` → Issue or PR #10
- `/update-review-pr-skill 10` → Issue or PR #10

## 前提条件

- 指定された Issue/PR が **PRスコープ外の既存実装に起因する** バグ・問題であること
- レビュアー定義ファイルが `.claude/skills/review-pr/reviewers/` に存在すること

## ワークフロー

### Step 1: 問題の把握

指定された Issue/PR からバグ・問題の内容を読み取る:

```bash
gh issue view <番号>
# または
gh pr view <番号>
```

問題の概要・影響範囲・再現条件を把握する。

### Step 2: 原因コードの特定

バグの原因となった既存コードを特定する:

1. バグ修正の差分やIssue本文から、原因箇所のファイルと行を特定する
2. `git log` や `git blame` でそのコードがどの PR/コミットで導入されたかを調査する:

```bash
git log --oneline --follow <原因ファイル>
git blame <原因ファイル> -L <開始行>,<終了行>
```

3. 原因コミットから PR 番号を特定する（コミットメッセージの `(#XX)` パターンや `gh pr list --search` を活用）

### Step 3: 過去レビューの確認

原因 PR のレビューコメントを取得し、該当箇所が指摘されていたか確認する:

```bash
gh pr view <原因PR番号>
gh api repos/{owner}/{repo}/pulls/<原因PR番号>/comments
gh api repos/{owner}/{repo}/issues/<原因PR番号>/comments
```

確認ポイント:
- レビュー自体が実施されていたか
- 該当箇所に対する指摘があったか
- 指摘があったが見逃されたのか、そもそも指摘されなかったのか

### Step 4: レビュアー定義の読み込み

現在のレビュアー定義を全件読み込む:

- `.claude/skills/review-pr/reviewers/code-quality.md`
- `.claude/skills/review-pr/reviewers/design-docs.md`
- `.claude/skills/review-pr/reviewers/rule-consistency.md`
- `.claude/skills/review-pr/reviewers/designer.md`
- `.claude/skills/review-pr/reviewers/llm-integration.md`

また、SKILL.md 本体のレビュアー判定ルール（Step 3）も確認する。

### Step 5: 漏れの原因分析

以下の観点で、なぜレビューで検出できなかったかを分析する:

#### 5a. レビュアーの選定

- 原因 PR の変更ファイルに対して、どのレビュアーが起動されるべきだったか
- 判定基準（対象ファイルパターン）は適切だったか
- 起動されるべきレビュアーが起動されなかった場合 → **判定基準の改善が必要**

#### 5b. チェック観点の網羅性

- 担当レビュアーのチェック観点に、今回の問題を検出できる項目があったか
- チェック観点にあったのに見逃した場合 → **観点の具体化・明確化が必要**
- そもそもチェック観点に含まれていなかった場合 → **新しいチェック項目の追加が必要**

#### 5c. レビュアーの責務範囲

- 今回の問題がどのレビュアーの責務にも属さない場合 → **既存レビュアーの責務拡張** または **新規レビュアーの追加を検討**

### Step 6: 改善案の提示

分析結果をユーザーに以下の形式で提示する:

```
## レビュー漏れ分析結果

### 問題の概要
<バグ・問題の内容>

### 原因 PR
PR #XX: <タイトル>（<マージ日>）

### 過去レビューの状況
<レビューの有無と指摘状況>

### 漏れの原因
<なぜ検出できなかったか>

### 改善案
- 対象レビュアー: `reviewers/<ファイル名>.md`
- 変更内容: <追加・修正するチェック観点>
```

**ユーザーの承認を得てから Step 7 に進むこと。**

### Step 7: レビュアー定義の更新

ユーザー承認後、該当する `reviewers/*.md` ファイルを更新する:

- 新しいチェック観点を適切なセクションに追加
- 必要に応じて判定基準を修正
- 既存のチェック観点の表現を具体化

更新時の注意:
- 既存のチェック観点を削除しない（追加・修正のみ）
- 他のレビュアーとの責務の重複を避ける
- 具体的かつ検証可能なチェック項目にする

### Step 8: コミット

変更をコミットする:

```bash
git add .claude/skills/review-pr/reviewers/<変更ファイル>
git commit -m "review-prレビュアー定義を改善: <問題の要約>"
```
