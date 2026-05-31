# Analysis / Articles Feature — Design Spec

**Date:** 2026-05-31
**Status:** Approved design — ready for implementation planning
**Branch:** `feat/2026-05-31-analysis-articles` (off `dev`)

## Purpose

Let the author publish written market-analysis articles on the AutoMana site to
explain their MTG-finance reasoning. Articles are authored in-app, stored in
Postgres, and read publicly. v1 is standalone prose; the content format leaves a
clean seam to embed live AutoMana data (price charts, card tiles) in a later
iteration.

## Locked Decisions

| Decision | Choice |
|---|---|
| Authoring & storage | In-app editor + Postgres |
| Editor | Markdown editor with live side-by-side preview; body stored as **raw Markdown** |
| Audience / SEO | Public; SEO (prerender/SSR) deferred |
| Data link | Standalone prose for v1; **embed-ready** via Markdown directives later |
| Reading view | Pure centered single column (~680px measure) |
| Hub layout | Magazine grid (cover-image cards) |
| Cover image | **Deferred** — v1 uses a generated gradient/placeholder cover; `cover_image_url` column exists but no upload pipeline |
| Scope | Single author, draft/publish, tags. **No** comments, **no** image upload, **no** live embeds in v1 |

## Surfaces & Routing

| Route | Visibility | Description |
|---|---|---|
| `/analysis` | **Public** | Magazine grid of published articles |
| `/analysis/$slug` | **Public** | Centered single-column reading page |
| `/analysis/admin` | Auth-guarded | List of all articles (draft + published) + "New" |
| `/analysis/admin/$id` | Auth-guarded | Markdown editor + live preview |

The SPA root is an auth guard today. `/analysis` and `/analysis/$slug` must be
**explicitly carved out as public**. Everything under `/analysis/admin` stays
guarded.

## Data Model

One migration under `database/SQL/migrations/`. Table `content.article`
(schema name TBD against existing conventions during planning):

| Column | Type | Notes |
|---|---|---|
| `id` | uuid/serial PK | |
| `slug` | text unique | derived from title |
| `title` | text | |
| `excerpt` | text | shown on grid card + link previews |
| `cover_image_url` | text null | unused in v1; placeholder cover rendered when null |
| `body_markdown` | text | raw Markdown; embed directives live here later |
| `status` | text/enum | `draft` \| `published` |
| `tags` | text[] | |
| `read_minutes` | int | auto-computed on save (~230 wpm) |
| `author_id` | fk | single author for now |
| `published_at` | timestamptz null | set on first publish |
| `created_at` / `updated_at` | timestamptz | |

## Backend (layered architecture, strict rules)

- **Repository** `ArticleRepository(AbstractDBRepository)` — all DB access via
  `AbstractDBRepository` wrappers, never raw connection. CQS naming:
  - Reads: `list_published_articles`, `get_article_by_slug`, `list_all_articles` (admin)
  - Writes: `insert_article`, `update_article`, `delete_article`
- **Service** registered via `@ServiceRegistry.register`. Public list/detail
  services **hard-filter `status = 'published'`** so drafts cannot leak to
  anonymous readers. Use the `automana-create-service` skill to scaffold.
- **Router** — no direct DB access. Public GET endpoints (list/detail, published
  only) + auth-guarded write endpoints (create/update/publish/delete).
- No backend Markdown rendering — the SPA renders Markdown client-side.

## Frontend

- New feature folder `src/features/articles/` mirroring `cards`/`collection`
  (`api.ts`, `types.ts`, `components/`, `__tests__/`).
- Reading view renders sanitized Markdown via `react-markdown` (new dependency).
- Editor: textarea + live `react-markdown` preview pane.
- Grid card: gradient/placeholder cover (derived from title/tag) until
  `cover_image_url` is populated in a later iteration.

## Embed Seam (future, not v1)

Because the body is Markdown, live embeds later become a directive such as
`::card{id=123}` or a fenced block, resolved by a `react-markdown` plugin into a
live component (price spark, card tile). No v1 work — just don't choose a storage
format that forecloses it (raw Markdown satisfies this).

## Editorial Guidance

**Word counts by article type:**

| Type | Words | Read time | When |
|---|---|---|---|
| Spec alert / quick take | 250–500 | 1–2 min | "X just moved, here's why" |
| Standard market read | **700–1,200** | 3–5 min | bread-and-butter (default band) |
| Deep dive (format shift, regional arbitrage) | 1,500–2,500 | 7–11 min | flagship pieces |

Going past ~2,500 words rarely pays off online — split into a series instead.

**Structure that lands for finance analysis:**

1. **Headline = a specific, falsifiable claim** ("Sheoldred's floor is holding"
   beats "Sheoldred thoughts").
2. **Excerpt/dek** — 1–2 sentences; shown on the grid card and link previews.
3. **Lede states the thesis in the first 2 sentences** — no warm-up.
4. **Body in H2/H3 sections**, one idea each; show the data (chart screenshot
   for now, live embed later).
5. **End with "The trade" / takeaway** — what the reader should *do*.
6. **Disclose** any position held in the card discussed.

**Cadence:** 1–2 pieces/week is sustainable and builds a habit-forming archive.
Consistency beats volume. Mix evergreen (frameworks) with timely (spec alerts)
so the hub doesn't age badly.

## Out of Scope (v1)

- Image/cover upload + storage service
- Live data embeds
- Comments, reactions, subscriptions/email
- SEO prerender/SSR
- Multi-author roles/permissions

## Open Questions for Planning

- Exact schema to host `article` (new `content` schema vs existing).
- `read_minutes` computed in service on save vs DB trigger.
- Markdown sanitization library choice (e.g. `rehype-sanitize`).
