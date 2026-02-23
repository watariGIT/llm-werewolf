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
| `Role` | 役職（`villager`, `seer`, `werewolf`, `knight`, `medium`, `madman`）。`night_action_type` / `has_night_action` プロパティで夜行動メタデータを提供 |
| `NightActionType` | 夜行動種別（`divine`, `attack`, `guard`）。`Role` のメタデータとして使用 |
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
| `assign_roles` | 配役ロジック（9人にランダムで役職を割り当て） |
| `create_game` | ゲーム初期化ファクトリ |
| `create_game_with_role` | 指定プレイヤーに指定役職を割り当ててゲーム初期化 |
| `check_victory` | 勝利判定（人狼全滅→村人勝利、村人陣営≦人狼→人狼勝利） |
| `can_guard` | 護衛制約チェック（狩人であること・自己護衛不可） |

### ゲームログサービス (`game_log.py`)

| 関数 | 説明 |
|------|------|
| `format_log_for_context` | プレイヤー視点でフィルタリングしたゲームログを生成（Step 2 の LLM コンテキスト用） |

## アプリケーション層 (`engine/`)

ゲーム進行のユースケースを管理する層。ドメイン層のモデルとサービスを組み合わせてゲームループを実現する。

| クラス/Protocol/モジュール | 説明 |
|---------------------------|------|
| `ActionProvider` | プレイヤー行動の抽象インターフェース（Protocol）。議論・投票・占い・襲撃・護衛の行動を定義 |
| `game_logic` | 両エンジン共通のゲームロジック関数群。占い結果通知・占い/襲撃/護衛実行・霊媒結果通知・投票集計・発言順管理・議論ラウンド数判定を提供。`find_night_actor` / `get_night_action_candidates` で役職メタデータに基づく汎用的な夜行動解決を提供 |
| `GameEngine` | 一括実行用ゲームループ管理。昼議論→投票→処刑（霊媒結果記録）→夜行動（占い→護衛→襲撃、護衛成功判定）→勝利判定のサイクルを自動実行。`game_logic` の共通関数を利用 |
| `InteractiveGameEngine` | インタラクティブ用ステップ実行エンジン。ユーザー入力を受け付けながら1ステップずつゲームを進行。議論・投票・夜行動（占い・襲撃・護衛）の各メソッドを提供し、護衛成功判定・霊媒結果通知を含む。`game_logic` の共通関数を利用 |
| `RandomActionProvider` | 全行動をランダムで実行するダミーAI（Mock版） |
| `CandidateDecision` | 候補者選択の構造化レスポンスモデル（Pydantic BaseModel）。`target`（選択した候補者名）と `reason`（選択理由）を保持する。`with_structured_output()` で LLM に型安全なレスポンスを強制し、パースエラーを削減する |
| `LLMActionProvider` | LLM ベースの ActionProvider 実装。LangChain + OpenAI API で議論・投票・占い・襲撃・護衛の行動を生成。議論は従来のテキスト応答、候補者選択（投票・占い・襲撃・護衛）は `with_structured_output()` + `CandidateDecision` による構造化出力を使用。API エラー時は指数バックオフで最大3回リトライし、上限到達時は RandomActionProvider 相当のフォールバック動作で代替する。各呼び出しのプロンプト・レスポンス・レイテンシ・トークン使用量をログ出力する（INFO: アクション完了+理由、DEBUG: 詳細、WARNING: エラー/フォールバック） |
| `LLMConfig` | LLM 設定を保持する値オブジェクト。model_name・temperature・api_key を管理 |
| `load_llm_config` | 環境変数から `LLMConfig` を生成するファクトリ関数。`OPENAI_API_KEY` 未設定時は `ValueError` を送出 |
| `response_parser` | LLM レスポンスのパースとバリデーション。議論テキストの正規化、候補者名マッチング（完全一致→部分一致→ランダムフォールバック）を提供。構造化出力の `target` が候補者リストに含まれない場合のフォールバックとしても使用される |
| `prompts` | LLM 用プロンプトテンプレート生成。役職別システムプロンプトとアクション別ユーザープロンプト（discuss, vote, divine, attack, guard）を提供。`format_log_for_context` を活用したゲームコンテキスト埋め込みを行う。人格特性システム（`PersonalityTrait` / `TRAIT_CATEGORIES`）により、口調・議論態度・思考スタイルの独立した特性軸を組み合わせて多様なAI人格を生成する。襲撃プロンプトには仲間の人狼情報を含める |
| `PersonalityTrait` | 人格特性の1要素を表すデータクラス。カテゴリ（軸名）とプロンプト用テキストを保持する |
| `assign_personalities` | AI人数分の特性組み合わせを生成する関数。各特性軸からランダムに1つ選択し、人格のバリエーションを作る |
| `build_personality` | 特性リストからプロンプトに埋め込む人格テキストを組み立てる関数 |
| `ActionMetrics` | 1回のアクション呼び出しのメトリクス（アクション種別・プレイヤー名・レイテンシ）を保持するデータクラス |
| `GameMetrics` | 1ゲーム分のメトリクスを集約するデータクラス。`total_api_calls` / `average_latency` プロパティで統計を提供 |
| `MetricsCollectingProvider` | ActionProvider のデコレータ。内部の Provider をラップし、各呼び出しのレイテンシを計測して `GameMetrics` に記録する。LLMActionProvider を変更せずにメトリクスを収集可能 |

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
| `GameSessionStore` | 一括実行ゲームの CRUD 管理。ゲームID → GameState のマッピングを保持。`create()` に `LLMConfig` を渡すと `LLMActionProvider` を使用し、省略時は `RandomActionProvider` にフォールバック |
| `GameStep` | インタラクティブゲームの進行ステップ。遷移順: `role_reveal` → `discussion` → `vote` → `execution_result` → `night_action` → `night_result` → `discussion`（次の日）。勝利時は `game_over` へ遷移 |
| `InteractiveSession` | インタラクティブゲームの状態。GameState + 進行ステップ + AI providers + `discussion_round`（議論ラウンド番号）+ `speaking_order`（発言順）+ `display_order`（UI表示用の固定プレイヤー順）を保持 |
| `InteractiveSessionStore` | InteractiveSession のインメモリ CRUD。`create()` に `LLMConfig` を渡すと AI プレイヤーに `LLMActionProvider` を使用し、省略時は `RandomActionProvider` にフォールバック |

#### ステップ進行関数

インフラ層のモジュール関数として配置。ビジネスロジックはエンジン層の `InteractiveGameEngine` に委譲し、セッション状態の更新とステップ遷移のみを担当する薄いラッパーとして機能する。

| 関数 | 説明 |
|------|------|
| `advance_to_discussion` | `InteractiveGameEngine.advance_discussion()` を呼び出し DISCUSSION ステップへ遷移 |
| `handle_user_discuss` | `InteractiveGameEngine.handle_user_discuss()` を呼び出し、結果に応じて VOTE または次ラウンドへ遷移 |
| `skip_to_vote` | ユーザー死亡時に `discussion_round` をリセットし VOTE へスキップ |
| `handle_user_vote` | `InteractiveGameEngine.handle_user_vote()` を呼び出し、常に EXECUTION_RESULT へ遷移。勝者が確定した場合は `session.winner` に保持 |
| `handle_auto_vote` | `InteractiveGameEngine.handle_auto_vote()` を呼び出し、ユーザー死亡時の AI のみ投票を処理。常に EXECUTION_RESULT へ遷移 |
| `advance_from_execution_result` | `session.winner` が設定済みなら `_set_game_over()` で GAME_OVER へ、未設定なら `start_night_phase()` で夜フェーズへ遷移 |
| `start_night_phase` | `InteractiveGameEngine.start_night()` を呼び出し、NIGHT_ACTION または即解決へ遷移 |
| `handle_night_action` | ユーザーの夜行動（占い・襲撃・護衛対象選択）を検証し `resolve_night_phase()` へ委譲 |
| `resolve_night_phase` | `InteractiveGameEngine.resolve_night()` を呼び出し夜を完了（占い・護衛・襲撃を解決） |

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
| `/play/{id}/export` | GET | ゲームログを JSON 形式でエクスポート |
| `/games` | POST | 一括実行ゲーム作成（API） |
| `/games` | GET | 一括実行ゲーム一覧（API） |
| `/games/{id}` | GET | 一括実行ゲーム状態取得（API） |

## ベンチマーク (`scripts/`)

| ファイル | 説明 |
|---------|------|
| `scripts/benchmark.py` | CLI ベンチマークスクリプト。指定回数のゲームを一括実行し、陣営別勝率・平均ターン数・API 呼び出し回数・平均レイテンシ・護衛成功回数を集計して JSON 出力する。各ゲームの完全なログ（発言・投票・夜行動等）も結果に含まれる。`--compare-random` で RandomActionProvider との比較、`--random-only` で API KEY 不要の実行が可能 |

## 命名規則

コード上の命名は [用語集](glossary.md) に準拠する。
