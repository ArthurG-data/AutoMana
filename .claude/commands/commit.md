---
description: Smart commit with context
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git commit:*)
argument-hint: [message]
---

## Context
- Current git status: !`git status`
- Current git diff: !`git diff HEAD`
- Current branch: !`git branch --show-current`
- Recent commits: !`git log --oneline -5`

## Task

Create a git commit using the following rules:

1. Stage all modified and new tracked files (`git add -u`). Do not stage untracked files unless they are clearly part of the change.
2. Use `$ARGUMENTS` as the commit message if provided. Otherwise derive a message from the diff.
3. Follow the commit template format from `.commit-template.txt`:
   - First line: `<type>(<scope>): <short summary>` (max 72 chars)
   - Valid types: `feat`, `fix`, `refactor`, `chore`, `docs`
   - Scope: the module or area changed (e.g. `worker`, `scryfall`, `settings`)
   - Optional body: explain *why* the change was made
   - Optional footer: issue references (e.g. `Closes #123`)
4. Append the co-author line:
   ```
   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
   ```
5. Run `git status` after committing to confirm success.
