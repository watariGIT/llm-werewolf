---
globs: src/llm_werewolf/domain/**
---

# ドメイン層ルール

- DDD（ドメイン駆動設計）に従う
  - 値オブジェクト: `str, Enum` で定義（`value_objects.py`）
  - エンティティ: `@dataclass(frozen=True)` で定義、一意な同一性を持つ（`player.py`）
    - 不変オブジェクトとして設計し、状態変更時は新インスタンスを返す
  - 集約ルート: `@dataclass(frozen=True)` で定義、関連オブジェクトの整合性境界（`game.py`）
    - コレクションは `tuple` を使用し、状態変更は `dataclasses.replace` で新インスタンスを返す
  - ドメインサービス: エンティティに属さないビジネスロジックを関数で提供（`services.py`）
- **外部ライブラリに依存しない**（Python 標準ライブラリのみ使用可）
- 命名は `docs/glossary.md` の用語に準拠すること
- ゲームロジックは `docs/game-rules.md` のルールに準拠すること
- ドメインサービスの制約チェック関数は、違反時に `ValueError` を送出する
