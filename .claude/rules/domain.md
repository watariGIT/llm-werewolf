---
globs: src/llm_werewolf/domain/**
---

# ドメイン層ルール

- DDD（ドメイン駆動設計）に従う
  - 値オブジェクト: `str, Enum` で定義（`value_objects.py`）
  - エンティティ: `@dataclass` で定義、一意な同一性を持つ（`player.py`）
  - 集約ルート: 関連オブジェクトの整合性境界（`game.py`）
  - ドメインサービス: エンティティに属さないビジネスロジックを関数で提供（`services.py`）
- **外部ライブラリに依存しない**（Python 標準ライブラリのみ使用可）
- 命名は `docs/glossary.md` の用語に準拠すること
- ゲームロジックは `docs/game-rules.md` のルールに準拠すること
