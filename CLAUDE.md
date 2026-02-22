# CLAUDE.md — Project Instructions

## Basic Rules

- Respond in Japanese
- Always use **uv** for package management (pip is prohibited)
- Tests use pytest (`tests/` directory)

## Project Structure

- **src layout**: `src/llm_werewolf/` is the package root
- Web FW: FastAPI + Jinja2 (templates in `src/llm_werewolf/templates/`)
- LLM integration: LangChain → OpenAI API
- Python 3.12

## References

@docs/game-rules.md
@docs/glossary.md
@docs/architecture.md

## Current Development Phase

- **Step 2: ChatGPT integration** — Replace random actions with LangChain + OpenAI API
- See README.md roadmap for details
- Tasks for each Step are tracked via GitHub Issues

## Common Commands

```bash
uv sync                  # Install dependencies
uv run tox               # Run lint, type check, and tests
uv run tox -e integration # Run integration tests (OPENAI_API_KEY required)
```

## Development Workflow

### Branch Strategy

- `master` is the main branch. No direct commits
- Features: `feature/<issue-number>-<short-description>` (e.g., `feature/3-add-voting-phase`)
- Bug fixes: `fix/<issue-number>-<short-description>` (e.g., `fix/7-fix-role-assignment`)
- PRs always merge into `master`

### Pre-commit Checks (Required)

```bash
uv run ruff format .     # Apply formatting
uv run tox               # Must pass lint, type check, and tests
```

### Standard Workflow

1. Review the GitHub Issue and understand requirements
2. Create a worktree with `feature/` or `fix/` branch
   ```bash
   git fetch origin master
   git worktree add .worktrees/<branch-name> -b <branch-name> origin/master
   cd .worktrees/<branch-name>
   ```
   All subsequent work (implementation, lint, test, commit, push) is done inside the worktree directory.
3. Design in plan mode → implement after user approval
4. Pass lint and tests before committing and pushing (`uv sync` first in worktree)
5. Create PR with `gh pr create`
6. `/review-pr` for code review (results posted as PR comment) → `/fix-review` to address feedback
7. Merge after user confirmation
8. Clean up the worktree
   ```bash
   cd <original-repo-root>
   git worktree remove .worktrees/<branch-name>
   ```
9. `/create-issue` for creating Issues with a unified template (labels, related Issues, dedup check)

### GitHub CLI Reference

```bash
gh issue view <number>                                        # View issue
gh pr create --title "..." --body "..."                       # Create PR
gh pr diff                                                    # PR diff
gh pr comment <number> --body "..."                           # Post PR comment
gh api repos/{owner}/{repo}/pulls/{number}/comments           # Get PR comments
```
