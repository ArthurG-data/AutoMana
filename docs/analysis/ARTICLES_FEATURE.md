# Articles (Analysis) Section

The **Articles** section (reachable from the sidebar, labelled "Articles", route
`/analysis`) is AutoMana's in-app publishing surface for MTG-finance analysis
write-ups. Articles are authored in Markdown by admins, stored in PostgreSQL, and
rendered to all visitors in a clean reading view.

> This document covers the **application feature** — the section, its routes, the
> API, and the step-by-step "how to add an article" flow.
> For the **editorial workflow** (how to research and write the article *content*
> itself — templates, figures, methodology), see
> [`articles/EDITORIAL_GUIDE.md`](articles/EDITORIAL_GUIDE.md).

---

## What the section is

- **Public hub** — a grid of published articles. Anyone (logged in or not) can
  browse and read.
- **Reading view** — a single published article rendered from Markdown, addressed
  by a URL-friendly `slug`.
- **Admin area** — admin-only pages to create, edit, publish/unpublish, and delete
  articles. Non-admins cannot reach these routes or the admin API.

Drafts are private; only **published** articles appear in the public hub and are
reachable by slug.

---

## Routes (frontend)

| Route | Access | Purpose |
|-------|--------|---------|
| `/analysis` | Public | Article hub — grid of published articles (`ArticleGrid`) |
| `/analysis/$slug` | Public | Reading view for one published article |
| `/analysis/admin` | Admin | Article list with **+ New article** and publish/unpublish |
| `/analysis/admin/$id` | Admin | Markdown editor for a single article |

The sidebar entry (`Sidebar.tsx`) routes to `/analysis` with the `article` icon and
the label **Articles**. Its nav `id` stays `analysis` to match the route, the
`TopBar` title, and `active="analysis"`.

Markdown is rendered by `MarkdownView.tsx` using `react-markdown` + `remark-gfm`
(GitHub-flavoured Markdown: tables, strikethrough, task lists) with
`rehype-sanitize` (sanitises HTML to prevent injection from article bodies).

---

## API (backend)

All routes live under the content router and are reached from the frontend via the
`/api` proxy prefix. Public routes need no auth; admin routes require an **admin**
user (`require_admin` dependency — a normal logged-in user is rejected).

| Method | Path | Access | Description |
|--------|------|--------|-------------|
| `GET` | `/api/content/articles/` | Public | List published articles (`limit`, `offset`, `tag`) |
| `GET` | `/api/content/articles/{slug}` | Public | Get a published article by slug |
| `GET` | `/api/content/articles/admin/` | Admin | List all articles (draft + published) |
| `GET` | `/api/content/articles/admin/{article_id}` | Admin | Get any article by id |
| `POST` | `/api/content/articles/admin/` | Admin | Create an article (returns the new article) |
| `PATCH` | `/api/content/articles/admin/{article_id}` | Admin | Update title / excerpt / body / tags / cover |
| `POST` | `/api/content/articles/admin/{article_id}/publish?published=true\|false` | Admin | Publish or unpublish |
| `DELETE` | `/api/content/articles/admin/{article_id}` | Admin | Delete an article |

Source: `src/automana/api/routers/content/articles.py` (router),
`src/automana/core/services/content/` (services),
`src/automana/core/repositories/content/article_repository.py` (DB access).

### Article fields

`ArticleCreate` accepts: `title` (required, 1–300 chars), `excerpt` (≤500),
`body_markdown`, `cover_image_url`, `tags`. `ArticleUpdate` makes all of these
optional (patch semantics). The server derives `slug`, `status`
(`draft`/`published`), `read_minutes`, `author_id`, and timestamps — you don't set
them by hand.

---

## How to add an article

You must be logged in as an **admin** user. Two ways:

### A. Via the UI (recommended)

1. Open the **Articles** section in the sidebar, then go to `/analysis/admin`
   (the admin list).
2. Click **+ New article**. This creates a draft titled "Untitled draft" and drops
   you into the editor at `/analysis/admin/$id`.
3. Edit the **title**, **excerpt**, **tags** (comma-separated), and **body
   (Markdown)**. The editor shows a live rendered preview next to the Markdown and a
   word-count / read-time estimate with a length hint. The slug and final read-time
   are computed server-side on save. (A `cover_image_url` is supported by the API
   but is not yet exposed in the editor — set it via the API if needed.)
4. Save your changes (persists via `PATCH .../admin/{id}`). The article stays a
   **draft** — not yet public.
5. When ready, click **Publish** (in the admin list or editor). It now appears in
   the public hub at `/analysis` and is readable at `/analysis/<slug>`. Use
   **Unpublish** to pull it back to draft.

### B. Via the API directly

```bash
# 1. Create a draft (must be an admin; send your auth cookie/token)
curl -X POST https://<host>/api/content/articles/admin/ \
  -H "Content-Type: application/json" \
  --cookie "<admin session>" \
  -d '{
        "title": "Foil Premiums by Treatment",
        "excerpt": "How much extra do collectors pay for foils?",
        "body_markdown": "# Intro\n\nMarkdown body with **GFM** tables...",
        "tags": ["foils", "research"]
      }'
# → returns the created article, including its article_id and slug

# 2. Publish it
curl -X POST "https://<host>/api/content/articles/admin/<article_id>/publish?published=true" \
  --cookie "<admin session>"
```

---

## Data & migrations

Articles are persisted in PostgreSQL (content schema). The table and any schema
changes are introduced via a migration under
`src/automana/database/SQL/migrations/` (see the
`feat(content): analysis articles backend` commit for the initial migration).

---

## Related docs

- [`articles/EDITORIAL_GUIDE.md`](articles/EDITORIAL_GUIDE.md) — writing the article
  content (research templates, figures, methodology).
- [`ARTICLES_PLAN.md`](ARTICLES_PLAN.md) — the analysis content roadmap.
- [`../frontend/FRONTEND.md`](../frontend/FRONTEND.md) — SPA design system, routing,
  and stores.
