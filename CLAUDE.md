# CartoGraph — Claude Code Memory

> This file is auto-loaded by Claude Code at session start. Read it fully before writing any code.

---

## Project identity

**Name:** CartoGraph
**One-liner:** The only continuously updated UK database of ecommerce domains validated through commercial search intent analysis.
**Current phase:** Phase 1 — Foundation (data model + agent scaffold)
**Primary brief:** `uk-ecom-intel-brief (1).md` — read this before writing any domain logic.

---

## Architecture overview

```
[CloudFlare CDN + WAF]
        |
[FastAPI on ECS Fargate]  ←→  [Redis] ←→ [Celery Worker Fleet — 7 agent types]
        |
[PostgreSQL RDS]  →(PeerDB CDC)→  [ClickHouse Cloud]
        |
[Next.js on Vercel]  (frontend — migration target from current React/Vite)
        |
[S3] — raw SERP payloads, HTML snapshots, export staging
[Sentry + Prometheus + Grafana] — observability
```

---

## Tech stack

### Backend (current)
- **FastAPI** — REST API framework
- **SQLModel + SQLAlchemy** — ORM (PostgreSQL)
- **PostgreSQL** — primary database, JSONB for enrichment fields, GIN indexes
- **Alembic** — migrations
- **Pydantic v2** — validation and settings
- **JWT auth** — existing, keep as-is for user auth; workspace-scoped tokens for API auth
- **Celery + Redis** — task queue for 7-agent pipeline (add this)
- **Playwright** — headless Chromium for tech detection (Agent 5)
- **pwdlib + Argon2** — password hashing
- **Sentry** — error tracking
- **uv** — Python package manager
- **ruff + mypy** — linting/typing

### Analytics (to add)
- **ClickHouse Cloud** — time-series metrics, trending, historical queries
- **PeerDB** — CDC from PostgreSQL → ClickHouse

### Frontend (migration target)
- **Current:** React + Vite + TypeScript + TanStack Router + Tailwind + shadcn/ui
- **Target:** Next.js 15 on Vercel (SSR for SEO, edge caching)
- **Bun** — package manager and monorepo workspace
- **Biome** — linting/formatting

### Key third-party integrations
| Integration | Purpose | Agent |
|-------------|---------|-------|
| DataForSEO SERP API (queued mode) | SERP discovery (~£0.0005/query) | Agent 2 |
| DataForSEO Backlinks API | DR, referring domains, backlinks | Agent 4 |
| Moz Links API | DA, PA, Spam Score (supplementary) | Agent 4 |
| python-Wappalyzer (self-hosted) | Tech fingerprinting, 13K+ signatures | Agent 5 |
| crawl4ai | Async crawling, structured data extraction | Agent 3 |
| Companies House API | UK company verification | Enrichment |
| Stripe | Subscription billing | Monetisation |

---

## The 7-agent pipeline

Execute in this order. Run Agent 3 BEFORE Agents 4/5 to avoid wasting API budget.

```
Agent 1: Keyword Miner       — generates [KEYWORD_SET] (weekly)
Agent 2: SERP Discovery      — discovers domains from SERP results (daily, rotating batches)
Agent 3: Domain Classifier   — validates ecommerce vs non-store (on discovery)
Agent 4: SEO Metrics         — DR, DA, traffic, backlinks via DataForSEO + Moz (weekly)
Agent 5: Tech Stack          — Wappalyzer fingerprinting via Playwright (bi-weekly)
Agent 6: Intent Scoring      — commercial intent score 1-10, modifier density (weekly)
Agent 7: Change Detection    — monthly deltas, trending scores, alerts (monthly + daily sampling)
```

Each agent: idempotent outputs keyed by `job_id + entity_id`. Exponential backoff with circuit breakers per external data source.

---

## Data model

Three grains: **domain**, **URL**, **keyword** — joined via timestamped fact tables.

Core table: `domains` — PostgreSQL with JSONB columns for all enrichment groups:
`discovery`, `ecommerce`, `seo_metrics`, `intent_layer`, `serp_intelligence`, `technical_layer`, `contact`, `marketplace_overlap`, `paid_ads_presence`, `meta`, `change_tracking`, `confidence_score`, `pipeline`, `ai_summary`

Every confidence score includes an `evidence` array (explainability requirement).

**Schema version:** `1.0.0` — include `schema_version` on every record.

Full migration SQL is in `uk-ecom-intel-brief (1).md` → Stack 2.

---

## Subscription tiers and field gating

| Tier | Price | Key limits |
|------|-------|-----------|
| Free | £0 | 25 lookups/mo, 8 fields, 100 rows/view |
| Starter | £39/mo | 500 lookups, 20 fields, 5K rows, 50 CSV credits |
| Professional | £119/mo | Unlimited lookups, all fields, 50K rows, 500 CSV credits, API 10K calls |
| Business | £279/mo | 250K rows, 2K CSV credits, API 50K calls, historical 12mo |
| Enterprise | £749+/mo | Unlimited everything, custom SLA, full history |

Implement tier gating as **feature flags** at the API middleware layer. Never hard-code tier logic in agent or domain code.

---

## GDPR compliance rules — implement in EVERY agent

1. Store only generic business emails (`info@`, `hello@`, `sales@`, `support@`, `contact@`) — never personal emails.
2. Do not bulk-scrape personal contact data.
3. Implement domain owner removal workflow (right to erasure).
4. Store contact signals, not harvested address books.
5. Gate personal contact enrichment behind paid add-on + explicit user consent.

---

## SERP data collection — critical constraint

Direct automated querying of Google violates their ToS. **Always use licensed providers.**

Data source modes:
- **Mode A (preferred):** DataForSEO queued mode — `TaskPost → TaskReady → TaskGet`
- **Mode B:** Keyword database SERP endpoints (Ahrefs, SEMrush API)
- **Mode C:** Customer-connected Search Console imports

Implement a **provider interface** (`DataSource` abstract class) so any source can be swapped without changing agent logic.

---

## Dev environment commands

```bash
# Start full stack (Docker Compose)
docker compose watch

# Backend only
cd backend && uv run fastapi dev app/main.py

# Frontend only
cd frontend && bun run dev

# Run backend tests
cd backend && uv run pytest

# Run frontend tests
cd frontend && bun run test

# Generate frontend client from OpenAPI
cd frontend && bun run generate-client

# Pre-commit hooks
prek run
```

**Local URLs:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Mailcatcher: http://localhost:1080

---

## Code conventions

### Backend
- **Formatter/linter:** ruff (configured in `pyproject.toml`)
- **Type checker:** mypy (strict)
- **Package manager:** uv
- **Test framework:** pytest
- Follow existing SQLModel patterns in `backend/app/`
- All agent outputs must be JSON-serialisable Pydantic models
- Every new endpoint needs a corresponding pytest test

### Frontend
- **Formatter/linter:** Biome
- **Package manager:** Bun
- **Component library:** shadcn/ui + Radix UI
- Auto-generated API client — run `bun run generate-client` after backend changes
- Use TanStack Query for all server state

---

## Key files

| File | Purpose |
|------|---------|
| `uk-ecom-intel-brief (1).md` | Complete product spec — source of truth for all domain logic |
| `SOUL.md` | Mission, ICPs, competitive moat |
| `ROADMAP.md` | Phased delivery plan |
| `backend/app/main.py` | FastAPI application entry point |
| `backend/app/models.py` | SQLModel domain models |
| `backend/app/api/` | API route handlers |
| `compose.yml` | Production Docker Compose |
| `compose.override.yml` | Dev overrides |
| `.env` | Environment variables (never commit secrets) |

---

## MVP shipping checklist — run before every deploy

This is non-negotiable. 30–90 seconds of automation prevents "works on my machine" redeploy pain.

```bash
# 1. Frontend lint (Biome)
cd frontend && bun run lint

# 2. TypeScript type check
cd frontend && bun run typecheck

# 3. Backend type check
cd backend && uv run mypy app/

# 4. Backend tests (must pass 100%)
cd backend && uv run pytest

# 5. Playwright smoke tests (E2E)
cd frontend && bun run test:e2e
```

**Playwright smoke sequence (minimum viable):**
1. Login as test user → assert redirect to `/dashboard`
2. Open `/admin/projects` → assert HTTP 200
3. Open `/domains` table view → assert rows render
4. Click a domain row → open profile page → assert domain name visible
5. Assert no JS console errors on any of the above pages

All 5 steps must pass green before merging to `main` or deploying to staging/production. If any step fails, fix it — do not skip the check.

---

## Current sprint: Phase 1 tasks

1. Add `domains` table migration (Alembic) using SQL from brief Stack 2
2. Add `config/variables.py` with all `[VARIABLE]` placeholders as environment-backed config
3. Implement `DataSource` provider interface (abstract base class)
4. Scaffold Celery + Redis integration into existing Docker Compose
5. Build Agent 1 (Keyword Miner) skeleton with JSON output schema
6. Build Agent 2 (SERP Discovery) skeleton with DataForSEO queued-mode integration
7. Build Agent 3 (Domain Classifier) with evidence-based output

Do not start Phase 2 until all three agents produce valid JSON outputs against test fixtures.
