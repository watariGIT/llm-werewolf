---
name: create-issue
description: GitHub Issue を統一テンプレートで作成するスキル。ラベル付与・関連Issue紐づけ・重複チェックを一元化する。「/create-issue」「Issue を作成して」「課題を登録して」と言ったときに使う。
---

# Create Issue

GitHub Issue を統一テンプレートで作成するスキル。ラベル付与・関連 Issue 紐づけ・重複チェックを行い、一貫した形式で Issue を登録する。

## 引数の解析

- `/create-issue` → 対話的に Issue 内容を決定
- `/create-issue <説明>` → 説明をもとに Issue を作成

呼び出し元スキル（`/review-pr`, `/fix-review` 等）からコンテキストが渡される場合は、その情報を活用する。

## ワークフロー

### Step 1: Issue 内容の決定

引数やチャット履歴から以下の情報を収集する:

- 何を達成すべきか（ゴール）
- なぜ必要か（背景・出処）
- どう対応するか（変更方針）
- いつ対応するか（対応時期）

情報が不足している場合は、ユーザーに質問して補完する。

### Step 2: 重複チェック

既存の Issue と重複がないか確認する:

```bash
gh issue list --state open --limit 50
```

既存 Issue のタイトル・内容と照合し、同等の課題が既に登録されている場合はユーザーに報告する:

- 重複と判断 → 新規作成せず、該当 Issue 番号を報告して終了
- 類似だが別問題 → ユーザーに確認し、作成するかどうか判断を仰ぐ
- 重複なし → Step 3 に進む

### Step 3: ラベルの選定

既存ラベル一覧を取得し、適切なラベルを選定する:

```bash
gh label list --limit 50
```

Issue の内容に応じてラベルを選ぶ:

| 判定基準 | ラベル |
|---------|--------|
| バグ修正 | `bug` |
| 新機能・改善 | `enhancement` |
| ドキュメント関連 | `documentation` |
| ゲームルール関連 | `game-rules` |
| Step 1 のスコープ | `step-1` |

複数ラベルを付与してよい。選定したラベルをユーザーに提示し、確認を取る。

### Step 4: 関連 Issue の紐づけ

チャット履歴や引数から関連する Issue・PR を特定する:

- **親 Issue**: この Issue が属する上位タスク（あれば `## 背景` に記載）
- **関連 Issue/PR**: 出処となった PR 番号や関連する Issue 番号

関連情報は Issue 本文内に記載する（GitHub の Markdown リンク形式）。

### Step 5: Issue の作成

統一テンプレートで Issue を作成する:

```bash
gh issue create --title "<簡潔なタイトル>" --label "<label1>,<label2>" --body "$(cat <<'EOF'
## ゴール

<この Issue で達成すること>

## 背景

<なぜこの Issue が必要か>
<出処: PR #番号、commit ID、議論の経緯など>
<関連: #親Issue番号, #関連Issue番号>

## 変更方針

<推奨する対応アプローチ>

## 対応時期

<いつ対応するか: Step番号、前提条件など>
EOF
)"
```

### Step 6: 結果報告

作成した Issue の番号と URL をユーザーに報告する。

呼び出し元スキルがある場合は、そのスキルが必要とする形式（番号・URL）で結果を返す。
