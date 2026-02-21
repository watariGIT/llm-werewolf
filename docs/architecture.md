# アーキテクチャ設計

## 設計方針

本プロジェクトは **DDD（ドメイン駆動設計）** を採用し、ビジネスロジック（ドメイン層）をフレームワーク（FastAPI 等）から分離する。

## レイヤー構成

```
src/llm_werewolf/
  domain/              ← ドメイン層（Python 標準ライブラリのみ依存）
    value_objects.py       値オブジェクト
    player.py              エンティティ
    game.py                集約ルート
    services.py            ドメインサービス
    game_log.py            ゲームログのフィルタリング・整形
  engine/              ← アプリケーション層（ゲーム進行エンジン）
    action_provider.py     プレイヤー行動の抽象インターフェース
    game_engine.py         ゲームループ管理
    random_provider.py     ランダム行動プロバイダー（Mock版AI）
  session.py           ← インフラ層（セッション管理）
  main.py              ← インフラ層（FastAPI, Jinja2）
  templates/
```

### 依存の方向

```
インフラ層 (main.py, session.py) → アプリケーション層 (engine/) → ドメイン層 (domain/)
ドメイン層 → Python 標準ライブラリのみ
```

ドメイン層は FastAPI, Jinja2, LangChain 等の外部ライブラリに**一切依存しない**。
アプリケーション層はドメイン層に依存し、ゲーム進行のユースケースを実装する。

## DDD 構成要素

### 値オブジェクト (`value_objects.py`)

不変の型として `str, Enum` で定義する。同一性を持たず、値そのものが意味を持つ。

| クラス | 説明 |
|--------|------|
| `Team` | 陣営（`village`, `werewolf`） |
| `Role` | 役職（`villager`, `seer`, `werewolf`） |
| `Phase` | フェーズ（`day`, `night`） |
| `PlayerStatus` | 生存状態（`alive`, `dead`） |

### エンティティ (`player.py`)

一意な同一性（名前）を持ち、ライフサイクルの中で状態が変化するオブジェクト。

| クラス | 説明 |
|--------|------|
| `Player` | プレイヤー。名前・役職・生存状態を保持 |

### 集約ルート (`game.py`)

関連するエンティティと値オブジェクトをまとめ、整合性の境界を定義する。

| クラス | 説明 |
|--------|------|
| `GameState` | ゲーム全体の状態。プレイヤー一覧・フェーズ・日数・ログを保持 |

### ドメインサービス (`services.py`)

特定のエンティティに属さないビジネスロジックを関数として提供する。

| 関数 | 説明 |
|------|------|
| `assign_roles` | 配役ロジック（5人にランダムで役職を割り当て） |
| `create_game` | ゲーム初期化ファクトリ |
| `create_game_with_role` | 指定プレイヤーに指定役職を割り当ててゲーム初期化 |
| `check_victory` | 勝利判定（人狼全滅→村人勝利、村人陣営≦人狼→人狼勝利） |

### ゲームログサービス (`game_log.py`)

| 関数 | 説明 |
|------|------|
| `format_log_for_context` | プレイヤー視点でフィルタリングしたゲームログを生成（Step 2 の LLM コンテキスト用） |

## アプリケーション層 (`engine/`)

ゲーム進行のユースケースを管理する層。ドメイン層のモデルとサービスを組み合わせてゲームループを実現する。

| クラス/Protocol | 説明 |
|-----------------|------|
| `ActionProvider` | プレイヤー行動の抽象インターフェース（Protocol）。議論・投票・占い・襲撃の行動を定義 |
| `GameEngine` | ゲームループ管理。昼議論→投票→処刑→夜行動→勝利判定のサイクルを実行 |
| `RandomActionProvider` | 全行動をランダムで実行するダミーAI（Mock版） |

## インフラ層

### ゲームモード

本プロジェクトは2つのゲームモードをサポートする。

| モード | 用途 | ストア |
|--------|------|--------|
| 一括実行モード | AI のみでゲームを最初から最後まで自動実行し、結果を JSON API で返す | `GameSessionStore` |
| インタラクティブモード | ユーザーと AI が対戦し、ステップごとに進行する Web UI 版 | `InteractiveSessionStore` |

### セッション管理 (`session.py`)

リクエストをまたいでゲーム状態を保持するインメモリストア。

| クラス/Enum | 説明 |
|-------------|------|
| `GameSessionStore` | 一括実行ゲームの CRUD 管理。ゲームID → GameState のマッピングを保持 |
| `GameStep` | インタラクティブゲームの進行ステップ（`role_reveal`, `discussion`, `vote`, `execution_result`, `night_action`, `night_result`, `game_over`） |
| `InteractiveSession` | インタラクティブゲームの状態。GameState + 進行ステップ + AI providers を保持 |
| `InteractiveSessionStore` | InteractiveSession のインメモリ CRUD |

#### ステップ進行関数

インフラ層のモジュール関数として配置。GameState の変更は domain 層のメソッド（`add_log`, `replace_player` 等）と domain サービス（`check_victory`, `can_divine` 等）を呼び出して行う。

| 関数 | 説明 |
|------|------|
| `advance_to_discussion` | AI 議論を実行し DISCUSSION ステップへ遷移 |
| `handle_user_discuss` | ユーザー発言を記録し VOTE ステップへ遷移 |
| `handle_user_vote` | ユーザー投票 + AI 投票 → 集計 → 処刑 → 勝利判定 |
| `handle_auto_vote` | ユーザー死亡時の AI のみ投票 |
| `start_night_phase` | 夜フェーズ開始。ユーザーが占い師/人狼なら NIGHT_ACTION へ、それ以外は即解決 |
| `handle_night_action` | ユーザーの夜行動（占い/襲撃対象選択）を処理 |
| `resolve_night_phase` | AI の夜行動 + ユーザー選択を反映して夜を完了 |

### Web エンドポイント (`main.py`)

| パス | メソッド | 説明 |
|------|---------|------|
| `/` | GET | トップページ（名前入力フォーム） |
| `/play` | POST | インタラクティブゲーム作成（名前 + 役職選択） |
| `/play/{id}` | GET | ゲーム画面（現在ステップに応じた表示） |
| `/play/{id}/next` | POST | 次ステップへ進む |
| `/play/{id}/discuss` | POST | ユーザー発言送信 |
| `/play/{id}/vote` | POST | ユーザー投票送信 |
| `/play/{id}/night-action` | POST | ユーザー夜行動送信（占い/襲撃対象） |
| `/games` | POST | 一括実行ゲーム作成（API） |
| `/games` | GET | 一括実行ゲーム一覧（API） |
| `/games/{id}` | GET | 一括実行ゲーム状態取得（API） |

## 命名規則

コード上の命名は [用語集](glossary.md) に準拠する。
