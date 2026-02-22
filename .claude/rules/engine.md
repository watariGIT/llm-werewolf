---
globs: src/llm_werewolf/engine/**
---

# Engine Layer (Application Layer) Rules

- 依存は Python 標準ライブラリ + ドメイン層 + **LangChain / langchain-openai** のみ許可
  - LangChain 依存は `ActionProvider` の LLM 実装（Step 2 以降）に限定して使用する
  - ドメイン層（`domain/`）は引き続き Python 標準ライブラリのみ
- Abstract actions via `ActionProvider` Protocol; implement in concrete classes
  - New AI implementations must satisfy the `ActionProvider` interface
- `GameEngine` and `InteractiveGameEngine` must not mutate GameState directly; use `dataclasses.replace` or GameState methods to produce new instances
- `InteractiveGameEngine` provides step-by-step game progression for interactive mode; session.py delegates business logic to this engine
- Shared game logic functions live in `game_logic.py` and are used by both engines
- Inject `random.Random` from outside to ensure test determinism
