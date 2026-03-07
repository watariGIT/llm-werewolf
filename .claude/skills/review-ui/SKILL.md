# Review UI

Web UI の全画面スクリーンショットを撮影し、デザイン・UX をレビューするスキル。

## トリガー

- `/review-ui`
- 「UI をレビューして」「画面を確認して」

## 引数

- `--role <role>`: キャプチャする役職（デフォルト: villager）
  - 指定可能: villager, seer, werewolf, knight, medium, madman
- `--all`: 全役職でキャプチャ（並列実行）

## ワークフロー

### Step 1: キャプチャ実行

```bash
uv run python scripts/capture_ui.py --role <role>
```

`--all` が指定された場合は主要役職（villager, seer, werewolf, knight）を `--port` を変えて並列実行する:

```bash
uv run python scripts/capture_ui.py --role villager --port 8765 &
uv run python scripts/capture_ui.py --role seer --port 8766 &
uv run python scripts/capture_ui.py --role werewolf --port 8767 &
uv run python scripts/capture_ui.py --role knight --port 8768 &
wait
```

Bash ツールで並列実行する場合は各コマンドをバックグラウンドで起動し、`wait` で全完了を待つ。

### Step 2: スクリーンショット読み取り

Read ツールで `screenshots/<role>/` 内の全 PNG ファイルを読み取る。

### Step 3: デザイン・UX レビュー

以下の観点でレビューし、結果を報告する:

#### 3.1 デザイン一貫性
- テーマカラーの統一: 背景 `#1a1a2e`、テキスト `#e0e0e0`、ボタン `#e94560`
- フォントサイズ・余白の一貫性
- コンポーネントスタイルの統一感

#### 3.2 UX（ユーザビリティ）
- 操作の分かりやすさ（ボタン配置、ラベル）
- 情報の視認性（コントラスト、文字サイズ）
- 状態遷移の自然さ（各ステップ間の流れ）

#### 3.3 レイアウト
- 要素の配置バランス
- レスポンシブ対応の状況
- 余白・間隔の適切さ

#### 3.4 ゲーム体験
- ゲーム情報の十分な表示（役職、生存者、ログ）
- ゲーム進行の分かりやすさ
- フィードバックの適切さ（処刑結果、夜結果の表示）

### Step 4: 結果報告

問題点を重要度（高・中・低）で分類し、改善提案と共に報告する。
