---
globs: src/llm_werewolf/engine/**
---

# Engine Layer (Application Layer) Rules

- **No external library dependencies** (only Python standard library + domain layer allowed)
- Abstract actions via `ActionProvider` Protocol; implement in concrete classes
  - New AI implementations must satisfy the `ActionProvider` interface
- `GameEngine` must not mutate GameState directly; use `dataclasses.replace` or GameState methods to produce new instances
- Inject `random.Random` from outside to ensure test determinism
