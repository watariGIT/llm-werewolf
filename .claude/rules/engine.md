---
globs: src/llm_werewolf/engine/**
---

# Engine Layer (Application Layer) Rules

- Dependencies allowed: Python standard library + domain layer + **LangChain / langchain-openai** only
  - LangChain dependency is limited to `ActionProvider` LLM implementations (Step 2 onwards)
  - Domain layer (`domain/`) remains restricted to Python standard library only
- Abstract actions via `ActionProvider` Protocol; implement in concrete classes
  - New AI implementations must satisfy the `ActionProvider` interface
- `GameEngine` and `InteractiveGameEngine` must not mutate GameState directly; use `dataclasses.replace` or GameState methods to produce new instances
- `InteractiveGameEngine` provides step-by-step game progression for interactive mode; session.py delegates business logic to this engine
- Shared game logic functions live in `game_logic.py` and are used by both engines
- Inject `random.Random` from outside to ensure test determinism
