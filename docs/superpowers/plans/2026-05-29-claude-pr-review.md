# Claude Automated PR Review — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four parallel, advisory Claude review jobs (code, architecture, security, docs-currency) that fire automatically on every PR to `dev` or `main`.

**Architecture:** A single new workflow file `.github/workflows/claude-review.yml` with four independent jobs, each using `anthropics/claude-code-action@v1` with a `direct_prompt`. The docs job additionally creates a GitHub issue when stale documentation is detected. All jobs are advisory (exit 0 always).

**Tech Stack:** GitHub Actions, `anthropics/claude-code-action@v1`, Anthropic API (Claude Sonnet), `gh` CLI (already available in GitHub-hosted runners)

---

## Prerequisites (manual, do once before pushing the workflow)

### P1 — Add the `ANTHROPIC_API_KEY` secret to GitHub

1. Go to: `https://github.com/ArthurG-data/AutoMana/settings/secrets/actions`
2. Click **New repository secret**
3. Name: `ANTHROPIC_API_KEY`
4. Value: your Anthropic API key (from console.anthropic.com)
5. Click **Add secret**

### P2 — Note: `documentation` label already exists

The repo already has a `documentation` label (`#0075ca`). The docs review job will use this label when opening issues. No action needed.

---

## Task 1: Create the workflow file

**Files:**
- Create: `.github/workflows/claude-review.yml`

This is the only file that needs to be created or modified.

- [ ] **Step 1: Create `.github/workflows/claude-review.yml`**

```yaml
name: Claude PR Review

on:
  pull_request:
    branches: [dev, main]
    types: [opened, synchronize, reopened]

jobs:
  review-code:
    name: "Claude: Code Review"
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: anthropics/claude-code-action@v1
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          prompt: |
            Review this pull request diff for code correctness issues. Check for:
            - Logic errors and silent failures
            - Missing edge cases or error handling
            - Test coverage gaps (new code paths with no corresponding test)
            - Performance issues (N+1 queries, unnecessary loops, blocking calls in async code)
            - Type errors or unsafe type casts

            Post a single PR comment summarising your findings with file:line references.
            If there are no significant issues, say so in one sentence.

  review-arch:
    name: "Claude: Architecture"
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: anthropics/claude-code-action@v1
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          prompt: |
            Review this pull request for architecture and CLAUDE.md rule compliance.
            First read CLAUDE.md in the repo root for the full ruleset. Key rules to enforce:

            1. Layer boundary: Router → ServiceManager → Service → Repository → Database.
               No DB access from routers. No business logic in repositories.
            2. CQS naming: read-only methods must start with get_/fetch_/list_/exists_
               Write methods must start with insert_/update_/delete_/upsert_/execute_
            3. Logging: use logger.info("msg", extra={"key": value}) only.
               Never use logging.basicConfig(), never interpolate values into the message
               string with f-strings or %s, never pass reserved LogRecord keys in extra=
               (filename, module, lineno, etc.).
            4. Pipeline tasks in worker/tasks/pipelines.py must not use autoretry_for.
            5. No hardcoded credentials or paths — all config must come from core/settings.py.
            6. Every schema change must have a migration file under database/SQL/migrations/.
            7. Repository separation: DB queries only in AbstractDBRepository subclasses;
               external HTTP calls only in AbstractAPIRepository subclasses — never mixed
               in the same class.

            Post a single PR comment listing any violations with file:line references.
            If the PR is fully compliant, say so in one sentence.

  review-security:
    name: "Claude: Security"
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: anthropics/claude-code-action@v1
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          prompt: |
            Review this pull request for security vulnerabilities. Check for:
            - SQL injection (raw query construction without parameterisation)
            - Command injection (unsanitised input passed to shell commands)
            - XSS in any templated or rendered output
            - Broken authentication or missing authorisation checks
            - IDOR vulnerabilities — any endpoint touching eBay resources must verify
              ownership by joining app_info → app_user using both user_id and app_code;
              never trust a bare resource ID from the request without this check
            - Exposed secrets or credentials committed to source code
            - Missing input validation at system boundaries (user-supplied input, external
              API responses)

            Post a single PR comment with your findings, referencing the relevant OWASP
            category (e.g. A03 Injection, A01 Broken Access Control) where applicable.
            If no issues are found, say so in one sentence.

  review-docs:
    name: "Claude: Docs Currency"
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      issues: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: anthropics/claude-code-action@v1
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          prompt: |
            Review this pull request for documentation currency.

            Step 1 — identify which docs are candidates for staleness using this mapping:
              src/automana/api/routers/              → docs/api/API.md
              src/automana/core/services/            → docs/architecture/ARCHITECTURE.md
                                                       docs/architecture/DESIGN_PATTERNS.md
              src/automana/core/repositories/        → docs/architecture/ARCHITECTURE.md
                                                       docs/architecture/DESIGN_PATTERNS.md
              src/automana/worker/tasks/pipelines.py → docs/pipelines/ (match by pipeline name)
              src/automana/database/SQL/             → docs/infrastructure/DATABASE_ROLES.md
              src/automana/core/settings.py          → docs/infrastructure/DEPLOYMENT.md
              frontend/src/                          → docs/frontend/FRONTEND.md

            Step 2 — for each candidate doc, read the doc file and compare it against the
            changed code. Only flag a doc as stale if you can confirm the doc content is
            now inaccurate or missing information introduced by this PR.

            Step 3 — post a PR comment:
            - If stale docs found: list each stale file with a one-line reason.
            - If all docs are current: post one sentence saying so.

            Step 4 — if any stale docs were confirmed in Step 2, open a GitHub issue:
              gh issue create \
                --title "docs: update documentation for PR #${{ github.event.pull_request.number }} — ${{ github.event.pull_request.title }}" \
                --label "documentation" \
                --body "<body listing each stale doc file path and a brief reason>"
            Replace <body ...> with the actual content from your Step 2 findings.
```

- [ ] **Step 2: Validate YAML syntax**

Install `yamllint` if not present, then lint the file:

```bash
pip install yamllint --quiet
yamllint .github/workflows/claude-review.yml
```

Expected output: no errors (warnings about line length are acceptable).

If `pip` is not available or you prefer not to install, validate by pushing to a feature branch — GitHub will report any YAML parse errors in the Actions tab immediately without running the workflow.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/claude-review.yml
git commit -m "ci: add Claude automated PR review workflow (code, arch, security, docs)"
```

---

## Task 2: Smoke test

- [ ] **Step 1: Complete the prerequisite — add `ANTHROPIC_API_KEY` secret**

Follow the steps in **P1** above before pushing. The workflow will silently do nothing without the secret.

- [ ] **Step 2: Push the branch and open a PR targeting `dev`**

```bash
git push origin HEAD
gh pr create --base dev --title "test: smoke test Claude PR review workflow" --body "Testing the four Claude review jobs." --draft
```

- [ ] **Step 3: Watch the Actions tab**

Go to: `https://github.com/ArthurG-data/AutoMana/actions`

You should see a workflow run named **Claude PR Review** with 4 parallel jobs:
- `Claude: Code Review`
- `Claude: Architecture`
- `Claude: Security`
- `Claude: Docs Currency`

All 4 should show green (they always exit 0). Each should have posted a comment on the PR.

- [ ] **Step 4: Verify PR comments**

Open the draft PR. Confirm:
1. Four separate comments posted by the GitHub Actions bot.
2. Each comment identifies itself as the relevant review type.
3. The docs comment either says docs are current OR lists stale files and an issue was opened.

- [ ] **Step 5: Close the draft PR after verification**

```bash
gh pr close <PR_NUMBER> --delete-branch
```

---

## Notes

- All 4 jobs always exit 0 — they cannot block a merge. This is intentional per the design spec.
- The `GH_TOKEN` env var on the `review-docs` job is required for `gh issue create` to work; `GITHUB_TOKEN` alone does not satisfy the `gh` CLI.
- If the Anthropic API is down or rate-limited, the job logs the error and exits 0 — it does not fail the PR check.
- To disable a specific review temporarily, comment out the corresponding job block in the workflow file.
