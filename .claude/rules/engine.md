---
globs: src/llm_werewolf/engine/**
---

# Engine 層（アプリケーション層）ルール

- **外部ライブラリに依存しない**（Python 標準ライブラリ + domain 層のみ使用可）
- `ActionProvider` Protocol で行動を抽象化し、具象クラスで実装する
  - 新しい AI 実装は `ActionProvider` を満たすクラスとして追加する
- `GameEngine` は GameState を直接変異させず、`dataclasses.replace` や GameState のメソッドで新インスタンスを生成する
- 乱数は `random.Random` を外部から注入し、テスト決定性を確保する
