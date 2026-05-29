# Claude Automated PR Review — Design Spec

**Date:** 2026-05-29  
**Status:** Approved

---

## Overview

Add automated Claude code review to every pull request targeting `dev` or `main`. Four parallel review jobs run on each PR: code correctness, architecture/CLAUDE.md compliance, security, and documentation currency. All reviews are advisory (non-blocking). The docs job additionally opens a GitHub issue when stale documentation is detected.

---

## Workflow Structure

**File:** `.github/workflows/claude-review.yml`

**Trigger:**
```yaml
on:
  pull_request:
    branches: [dev, main]
    types: [opened, synchronize, reopened]
```

**Jobs (all run in parallel):**

| Job ID | Check Name | Focus |
|--------|-----------|-------|
| `review-code` | Claude: Code Review | Logic errors, edge cases, test coverage gaps, performance, silent failures |
| `review-arch` | Claude: Architecture | Layer violations, CQS naming, logging rules, pipeline patterns, CLAUDE.md compliance |
| `review-security` | Claude: Security | OWASP top 10, auth/authz, SQL injection, command injection, secret exposure, IDOR |
| `review-docs` | Claude: Docs Currency | Stale doc detection based on changed files; opens a `docs` GitHub issue if stale files found |

All jobs use `anthropics/claude-code-action@beta` with `direct_prompt` (fires automatically, no `@claude` trigger needed).

---

## Permissions

| Job | Permissions Required |
|-----|---------------------|
| `review-code` | `pull-requests: write` |
| `review-arch` | `pull-requests: write` |
| `review-security` | `pull-requests: write` |
| `review-docs` | `pull-requests: write`, `issues: write` |

---

## Secrets

| Secret | Purpose |
|--------|---------|
| `ANTHROPIC_API_KEY` | Authenticates all Claude API calls. Added under repo Settings → Secrets → Actions. |

No other secrets are needed. `GITHUB_TOKEN` is available automatically in all jobs.

---

## Prompt Design

### `review-code`
Focus: the PR diff only. Report logic errors, incorrect error handling, missing edge cases, test coverage gaps, N+1 queries, type errors. Output as a structured PR comment with file + line references. Skip style and formatting.

### `review-arch`
Focus: CLAUDE.md rules explicitly injected into the prompt context. Check:
- Router → ServiceManager → Service → Repository boundary (no direct DB access from routers)
- CQS method naming (`get_*`/`fetch_*`/`list_*`/`exists_*` for queries; `insert_*`/`update_*`/`delete_*`/`upsert_*`/`execute_*` for commands)
- Logging anti-patterns: no `logging.basicConfig()`, no message interpolation, no reserved `extra` keys, use `logger.info("msg", extra={"key": value})`
- No `autoretry_for` in pipeline tasks
- No hardcoded credentials or paths
- New schema changes must have a migration file under `database/SQL/migrations/`
- Repository separation: DB queries in `AbstractDBRepository` subclass; external API calls in `AbstractAPIRepository` subclass; never mixed

### `review-security`
Focus: OWASP top 10 applied to the diff. Check:
- SQL injection (raw query construction)
- Command injection
- XSS in any templated output
- Broken auth / missing ownership checks (eBay IDOR pattern: all eBay endpoints must pass `user_id + app_code`)
- Exposed secrets or credentials in code
- Missing input validation at system boundaries (user input, external API responses)

### `review-docs`
Focus: map changed files to the CLAUDE.md docs table and identify stale documentation.

File → doc mapping (from CLAUDE.md):

| Changed path pattern | Likely stale doc |
|---------------------|-----------------|
| `src/automana/api/routers/` | `docs/api/API.md` |
| `src/automana/core/services/` or `src/automana/core/repositories/` | `docs/architecture/ARCHITECTURE.md`, `docs/architecture/DESIGN_PATTERNS.md` |
| `src/automana/worker/tasks/pipelines.py` | relevant pipeline doc in `docs/pipelines/` |
| `src/automana/database/SQL/` | `docs/infrastructure/DATABASE_ROLES.md` |
| `src/automana/core/settings.py` | `docs/infrastructure/DEPLOYMENT.md` |
| `src/automana/api/routers/` (new endpoints) | `docs/testing/TESTING_API_FLOW.md` |
| Any pipeline service | `docs/MASTER_TECHNICAL_DEBT.md` or `docs/BACKLOG.md` if debt introduced |
| Frontend (`frontend/src/`) | `docs/frontend/FRONTEND.md` |

**Output:**
1. PR comment listing stale docs with a short reason for each.
2. If any stale docs found → open a GitHub issue:
   - Title: `docs: update documentation for PR #<N> — <PR title>`
   - Label: `docs`
   - Body: lists the stale files with links to the PR

---

## Error Handling

- If the Claude API call fails, the job exits with code 0 (not a failing check) so a transient API error never blocks a merge.
- Each job is independent — a failure in one does not cancel the others.

---

## Cost

~4 API calls per PR event (open + each push). At typical diff sizes (200–500 lines) with Claude Sonnet: ~$0.01–0.05 per call. No throttle needed; always-on is acceptable.

---

## Out of Scope

- Auto-fixing code (reviews are read-only comments)
- Blocking merges on findings (all advisory)
- Reviewing pushes directly to `dev` (only PRs)
- Scheduled / periodic doc audits (separate feature)
