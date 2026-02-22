---
globs: src/llm_werewolf/domain/**
---

# Domain Layer Rules

- Follow DDD (Domain-Driven Design)
  - Value Objects: defined with `str, Enum` (`value_objects.py`)
  - Entities: defined with `@dataclass(frozen=True)`, have unique identity (`player.py`)
    - Designed as immutable objects; return new instances on state changes
  - Aggregate Root: defined with `@dataclass(frozen=True)`, consistency boundary for related objects (`game.py`)
    - Use `tuple` for collections; create new instances via `dataclasses.replace` for state changes
  - Domain Services: business logic not belonging to entities, provided as functions (`services.py`)
- **No external library dependencies** (only Python standard library allowed)
- Naming must follow terminology in `docs/glossary.md`
- Game logic must comply with rules in `docs/game-rules.md`
- Constraint-checking functions in domain services must raise `ValueError` on violations
