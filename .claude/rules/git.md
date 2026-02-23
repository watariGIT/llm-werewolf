# Git Rules

- Never commit directly to `master`. Always use feature/fix branches and PRs
- Branch naming: `feature/<issue-number>-<short-description>` or `fix/<issue-number>-<short-description>`
- Use worktrees for development: `git worktree add .worktrees/<branch-name> -b <branch-name> origin/master`
- Always use squash merge when merging PRs: `gh pr merge --squash`
