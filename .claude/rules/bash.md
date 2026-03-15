# Bash Tool Rules

- Do not use compound commands with `&&` or `||` (execute commands one at a time)
- Do not prefix commands with `cd <dir> &&`. The working directory is already set correctly. `cd && git` triggers a security prompt that cannot be bypassed
- Use `E:/workspace/...` path format (do not use `/E:/...` or `/e/...`)
- Use dedicated tools (Read / Write / Edit) for file operations instead of Bash commands like `cat`
