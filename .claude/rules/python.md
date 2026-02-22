---
globs: "**/*.py"
---

# Python Coding Conventions

- Variables and functions: snake_case; classes: PascalCase
- Must comply with Ruff formatting and linting (line-length=120)
- Must pass mypy type checking
- Never hardcode `.env` or API keys (use environment variables)
- `.env` contains secrets and must not be committed to git
- Use uv for package management (pip is prohibited)
