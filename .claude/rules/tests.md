---
globs: tests/**
---

# テストルール

- pytest で記述
- テストクラスは `Test` プレフィックス、テスト関数は `test_` プレフィックス
- ドメインモデルの単体テストは `tests/domain/` に配置
- テスト用の乱数は `random.Random(seed)` を注入して決定性を確保
