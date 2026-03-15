# Bash Tool Rules

- Do not use compound commands with `&&` or `||` (execute commands one at a time)
- Do not prefix commands with `cd <dir> &&`. The working directory is already set correctly. `cd && git/gh` triggers a security prompt that cannot be bypassed. Use `-C <dir>` flag for git or `--repo` flag for gh if a different directory is needed
- Use `E:/workspace/...` path format (do not use `/E:/...` or `/e/...`)
- Use dedicated tools (Read / Write / Edit) for file operations instead of Bash commands like `cat`
