---
globs: tests/**
---

# Test Rules

- Write tests with pytest
- Test classes use `Test` prefix; test functions use `test_` prefix
- Domain model unit tests go in `tests/domain/`
- Inject `random.Random(seed)` for test determinism
