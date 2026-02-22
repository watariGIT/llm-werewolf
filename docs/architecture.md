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
  engine/              ← アプリケーション層（ゲーム進行エンジン、LangChain 依存可）
    action_provider.py     プレイヤー行動の抽象インターフェース
    game_logic.py          共通ゲームロジック関数
    game_engine.py         一括実行用ゲームループ管理
    interactive_engine.py  インタラクティブ用ステップ実行エンジン
    random_provider.py     ランダム行動プロバイダー（Mock版AI）
    llm_config.py          LLM設定の管理（環境変数バリデーション）
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
アプリケーション層はドメイン層に依存し、ゲーム進行のユースケースを実装する。LangChain / langchain-openai への依存は許可されており、LLM ベースの `ActionProvider` 実装に使用する。

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

| クラス/Protocol/モジュール | 説明 |
|---------------------------|------|
| `ActionProvider` | プレイヤー行動の抽象インターフェース（Protocol）。議論・投票・占い・襲撃の行動を定義 |
| `game_logic` | 両エンジン共通のゲームロジック関数群。占い結果通知・占い/襲撃実行・投票集計・発言順管理・議論ラウンド数判定を提供 |
| `GameEngine` | 一括実行用ゲームループ管理。昼議論→投票→処刑→夜行動→勝利判定のサイクルを自動実行。`game_logic` の共通関数を利用 |
| `InteractiveGameEngine` | インタラクティブ用ステップ実行エンジン。ユーザー入力を受け付けながら1ステップずつゲームを進行。議論・投票・夜行動の各メソッドを提供し、`game_logic` の共通関数を利用 |
| `RandomActionProvider` | 全行動をランダムで実行するダミーAI（Mock版） |
| `LLMConfig` | LLM 設定を保持する値オブジェクト。model_name・temperature・api_key を管理 |
| `load_llm_config` | 環境変数から `LLMConfig` を生成するファクトリ関数。`OPENAI_API_KEY` 未設定時は `ValueError` を送出 |
| `response_parser` | LLM レスポンスのパースとバリデーション。議論テキストの正規化、候補者名マッチング（完全一致→部分一致→ランダムフォールバック）を提供 |

## インフラ層

### ゲームモード

本プロジェクトは2つのゲームモードをサポートする。

| モード | 用途 | ストア |
|--------|------|--------|
| インタラクティブモード | メインのゲーム体験。ユーザーと AI が対戦し、ステップごとに進行する Web UI 版 | `InteractiveSessionStore` |
| 一括実行モード | 開発用内部ツール。AI のみで自動対戦し結果を JSON API で返す。Step 2 以降の LLM 品質評価・ベンチマークに活用 | `GameSessionStore` |

### セッション管理 (`session.py`)

リクエストをまたいでゲーム状態を保持するインメモリストア。

| クラス/Enum | 説明 |
|-------------|------|
| `MAX_SESSIONS` | セッション数の上限定数（デフォルト100）。DoS 対策として両ストアで共有 |
| `SessionLimitExceeded` | セッション数が上限に達した場合に発生する例外 |
| `GameSessionStore` | 一括実行ゲームの CRUD 管理。ゲームID → GameState のマッピングを保持 |
| `GameStep` | インタラクティブゲームの進行ステップ。遷移順: `role_reveal` → `discussion` → `vote` → `execution_result` → `night_action` → `night_result` → `discussion`（次の日）。勝利時は `game_over` へ遷移 |
| `InteractiveSession` | インタラクティブゲームの状態。GameState + 進行ステップ + AI providers + `discussion_round`（議論ラウンド番号）+ `speaking_order`（発言順）+ `display_order`（UI表示用の固定プレイヤー順）を保持 |
| `InteractiveSessionStore` | InteractiveSession のインメモリ CRUD |

#### ステップ進行関数

インフラ層のモジュール関数として配置。ビジネスロジックはエンジン層の `InteractiveGameEngine` に委譲し、セッション状態の更新とステップ遷移のみを担当する薄いラッパーとして機能する。

| 関数 | 説明 |
|------|------|
| `advance_to_discussion` | `InteractiveGameEngine.advance_discussion()` を呼び出し DISCUSSION ステップへ遷移 |
| `handle_user_discuss` | `InteractiveGameEngine.handle_user_discuss()` を呼び出し、結果に応じて VOTE または次ラウンドへ遷移 |
| `skip_to_vote` | ユーザー死亡時に `discussion_round` をリセットし VOTE へスキップ |
| `handle_user_vote` | `InteractiveGameEngine.handle_user_vote()` を呼び出し、結果に応じて EXECUTION_RESULT または GAME_OVER へ遷移 |
| `handle_auto_vote` | `InteractiveGameEngine.handle_auto_vote()` を呼び出し、ユーザー死亡時の AI のみ投票を処理 |
| `start_night_phase` | `InteractiveGameEngine.start_night()` を呼び出し、NIGHT_ACTION または即解決へ遷移 |
| `handle_night_action` | ユーザーの夜行動を検証し `resolve_night_phase()` へ委譲 |
| `resolve_night_phase` | `InteractiveGameEngine.resolve_night()` を呼び出し夜を完了 |

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
