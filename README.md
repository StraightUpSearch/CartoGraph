# CartoGraph

**The only continuously updated UK database of ecommerce domains validated through commercial search intent analysis.**

CartoGraph continuously maps UK ecommerce domains against commercial SERP signals — technology stack, SEO metrics, intent scores, SERP feature presence, and change tracking — and makes that intelligence queryable via a SaaS dashboard and API.

---

## Quick links

- [SOUL.md](./SOUL.md) — Mission, ICPs, competitive moat
- [ROADMAP.md](./ROADMAP.md) — Phased delivery plan
- [CLAUDE.md](./CLAUDE.md) — Claude Code session memory (read before coding)
- [uk-ecom-intel-brief (1).md](<./uk-ecom-intel-brief (1).md>) — Full product specification

---

## Architecture

```
[CloudFlare CDN + WAF]
        |
[FastAPI on ECS Fargate] ←→ [Redis] ←→ [Celery — 7 Agent Types]
        |
[PostgreSQL + JSONB]  →(PeerDB CDC)→  [ClickHouse Cloud]
        |
[Next.js on Vercel]
        |
[S3] — raw SERP payloads, snapshots, export staging
```

**Seven-agent pipeline:**
```
Agent 1: Keyword Miner     — generates UK commercial keyword set (weekly)
Agent 2: SERP Discovery    — discovers domains from SERP results (daily)
Agent 3: Domain Classifier — validates ecommerce vs non-store (on discovery)
Agent 4: SEO Metrics       — DR, DA, traffic via DataForSEO + Moz (weekly)
Agent 5: Tech Stack        — Wappalyzer fingerprinting via Playwright (bi-weekly)
Agent 6: Intent Scoring    — commercial intent score 1–10 (weekly)
Agent 7: Change Detection  — monthly deltas + trending scores (monthly)
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI (Python) |
| ORM | SQLModel + SQLAlchemy |
| Database | PostgreSQL (JSONB enrichment, GIN indexes) |
| Analytics | ClickHouse Cloud (time-series, trending) |
| CDC | PeerDB (PostgreSQL → ClickHouse) |
| Task queue | Celery + Redis |
| Tech detection | Wappalyzer (self-hosted, MIT) via Playwright |
| Frontend | Next.js on Vercel (migrating from React/Vite) |
| Auth | JWT (users) + workspace-scoped tokens (API) |
| Billing | Stripe (5-tier subscriptions) |
| Monitoring | Prometheus + Grafana + Sentry |
| SERP data | DataForSEO queued mode |
| Package managers | uv (Python), Bun (JS) |

---

## Subscription tiers

| Tier | Price | Key feature |
|------|-------|-------------|
| Free | £0 | 25 domain lookups/mo |
| Starter | £39/mo | 500 lookups, platform filtering, 50 CSV credits |
| Professional | £119/mo | Unlimited lookups, all fields, API access (10K calls) |
| Business | £279/mo | 250K rows, API 50K calls, 12-month history, white-label |
| Enterprise | £749+/mo | Unlimited, custom SLA, full history, S3 delivery |

---

## Development setup

### Prerequisites
- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/) for Python
- [Bun](https://bun.sh/) for JavaScript

### Start the full stack

```bash
docker compose watch
```

### Local URLs
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Mailcatcher: http://localhost:1080

### Run tests

```bash
# Backend
cd backend && uv run pytest

# Frontend
cd frontend && bun run test

# E2E (Playwright)
cd frontend && bun run test:e2e
```

### MVP shipping checklist (run before every deploy)

```bash
cd frontend && bun run lint          # Biome lint
cd frontend && bun run typecheck     # TypeScript type check
cd backend && uv run mypy app/       # Backend type check
cd backend && uv run pytest          # Backend tests
cd frontend && bun run test:e2e      # Playwright smoke tests
```

Playwright smoke sequence:
1. Login as test user
2. Navigate to `/dashboard`
3. Open `/admin/projects` (returns 200)
4. Open `/domains` table view
5. Click a domain profile — verify data renders

### Generate frontend API client

```bash
cd frontend && bun run generate-client
```

Run this after any backend schema changes.

---

## Environment configuration

Copy `.env` and set required secrets before running:

```bash
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
FIRST_SUPERUSER_PASSWORD=<secure password>
POSTGRES_PASSWORD=<secure password>
DATAFORSEO_LOGIN=<your DataForSEO login>
DATAFORSEO_PASSWORD=<your DataForSEO password>
```

See [development.md](./development.md) for full environment variable reference.

---

## Deployment

See [deployment.md](./deployment.md) for Docker Compose + Traefik production setup with automatic HTTPS.

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

---

## License

MIT
