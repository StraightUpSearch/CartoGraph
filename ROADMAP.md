# CartoGraph — Roadmap

> Phased delivery plan tied to the 7 implementation stacks in the brief. Each phase has a clear definition of done before the next begins.

---

## Phase 0 — Repository foundation (current)
**Goal:** Transform the FastAPI template into a CartoGraph-specific codebase with correct memory, identity, and planning files.

- [x] Add `CLAUDE.md` (Claude Code session memory)
- [x] Add `SOUL.md` (mission and product identity)
- [x] Add `ROADMAP.md` (this file)
- [x] Update `README.md` to reflect CartoGraph
- [ ] Add `config/variables.py` with all `[VARIABLE]` placeholders backed by environment variables
- [ ] Rename template-generic models and routes to CartoGraph-specific equivalents
- [ ] Confirm Docker Compose stack runs end-to-end (`docker compose watch`)

**Definition of done:** `docker compose watch` starts cleanly; `/docs` renders the CartoGraph API; all planning files are committed to `main`.

---

## Phase 1 — Foundation: data model + agent scaffold
**Stacks:** 2 (data model), 3 (agent pipeline — Agents 1–3)
**Target:** 10,000 validated UK ecommerce domains in database

### 1.1 Database schema
- [ ] Alembic migration: `domains` table with all JSONB field groups (see brief Stack 2 SQL)
- [ ] GIN indexes: `discovery`, `serp_intelligence`, `technical_layer`
- [ ] Scalar indexes: `country`, `status`, `domain_rating`, `organic_traffic_estimate`, `commercial_intent_score`, `platform`, `category_primary`
- [ ] Seed table: `keywords` for keyword queue management
- [ ] Seed table: `pipeline_runs` for agent audit log

### 1.2 Provider interface
- [ ] Abstract `DataSource` base class (`backend/app/agents/sources/base.py`)
- [ ] DataForSEO SERP implementation (queued mode: `TaskPost → TaskReady → TaskGet`)
- [ ] Mock/fixture implementation for tests

### 1.3 Celery + Redis integration
- [ ] Add Redis service to `compose.override.yml`
- [ ] Add Celery worker service to Docker Compose
- [ ] Define priority queues: one per agent type
- [ ] Dead letter queue configuration
- [ ] Retry policy: exponential backoff, circuit breakers per external source

### 1.4 Agents 1–3
- [ ] **Agent 1 — Keyword Miner:** Generate `[KEYWORD_SET]` from intent modifiers + product taxonomy. Weekly cron. JSON output schema.
- [ ] **Agent 2 — SERP Discovery:** Consume keyword queue, submit to DataForSEO, extract domains, detect SERP features. Daily rotating batches. Store payload hashes to S3.
- [ ] **Agent 3 — Domain Classifier:** Evidence-based ecommerce validation (product schema, checkout path, platform fingerprint, commercial SERP presence). Run before Agents 4/5. JSON output with `confidence` + `evidence[]`.

**Definition of done:** Agents 1–3 process a test fixture of 100 keywords → produce ≥50 classified ecommerce domains with valid JSON outputs. All tests pass.

---

## Phase 2 — Enrichment layer: Agents 4–7 + ClickHouse
**Stacks:** 3 (Agents 4–7), data analytics layer

### 2.1 Agents 4–7
- [ ] **Agent 4 — SEO Metrics:** DataForSEO Backlinks API + Moz Links API. Weekly for top 20%, bi-weekly for rest. Writes `seo_metrics` JSONB + pushes snapshot to ClickHouse.
- [ ] **Agent 5 — Tech Stack:** Self-hosted Wappalyzer via Playwright Chromium. Bi-weekly. Technology changelog delta detection. 15K domains/day capacity target.
- [ ] **Agent 6 — Intent Scoring:** Internal calculation from Agents 1/2/4/5 outputs. Scoring formula from brief. Evidence-explained output.
- [ ] **Agent 7 — Change Detection:** Monthly full delta + daily trending sampling. `change_tracking` JSONB + ClickHouse writes.

### 2.2 Analytics database
- [ ] ClickHouse Cloud instance provisioned
- [ ] PeerDB CDC pipeline: PostgreSQL → ClickHouse for `domain_metrics_history` and `serp_snapshots`
- [ ] `technology_changelog` table in ClickHouse
- [ ] Materialised views for dashboard aggregations (platform market share, trending scores)

### 2.3 Contact enrichment (GDPR-compliant)
- [ ] Contact scraping agent: generic business emails only (`info@`, `hello@`, `sales@`, `support@`, `contact@`)
- [ ] Social profile detection: Instagram, Facebook, LinkedIn, TikTok, YouTube, Pinterest
- [ ] Companies House API integration (quarterly enrichment)
- [ ] Removal workflow: domain owner erasure request → soft delete + audit log

**Definition of done:** Full pipeline runs on 1,000 domains end-to-end. All 7 agents produce valid outputs. ClickHouse receives CDC events. Cost per enriched domain ≤ £0.05.

---

## Phase 3 — API and auth layer
**Stack:** 4 (UX/API spec)

- [ ] REST API endpoints: `/domains`, `/domains/{id}`, `/search`, `/exports`, `/alerts`, `/webhooks`
- [ ] Workspace-scoped API token auth (separate from user JWT)
- [ ] Tier-based rate limiting middleware (feature flags per tier)
- [ ] Field gating: JSONB field masking by subscription tier
- [ ] Cursor pagination (stable sort by `domain_id`)
- [ ] Rate limits: Professional 100 req/min, Business 500 req/min, Enterprise custom
- [ ] Webhook delivery system (per-event + batch modes)
- [ ] Bulk domain import endpoint (`POST /api/v1/domains/import`)
- [ ] OpenAPI schema updated; frontend client regenerated

**Definition of done:** All endpoints return correct data with correct tier gating. Postman/HTTPie test suite passes. Frontend client generated successfully.

---

## Phase 4 — Frontend: Next.js dashboard
**Stack:** 4 (UX wireframes)

- [ ] Migrate from React/Vite to Next.js 15 on Vercel (or keep Vite for MVP speed — decision point)
- [ ] Dashboard: summary stats, top movers, pipeline health
- [ ] Main database view: filter panel (DR, traffic, intent, platform, category, SERP features, status)
- [ ] Configurable table columns
- [ ] Domain profile page: Overview, SEO, Technology, SERP, Contact, History tabs
- [ ] AI summary panel per domain
- [ ] Saved lists management
- [ ] Alerts management (create, edit, delete alert rules)
- [ ] Upgrade prompt modals (at each tier gate trigger)
- [ ] Tier-based nav visibility (PRO/BUSINESS badges on gated nav items)

**Definition of done:** Playwright smoke test passes: login → `/dashboard` → filter by platform → open domain profile → verify data renders. No blurred/gated fields visible to correct tier.

---

## Phase 5 — Monetisation
**Stack:** 5 (pricing + billing)

- [ ] Stripe integration: 5-tier subscription products (Free, Starter £39, Professional £119, Business £279, Enterprise custom)
- [ ] Annual pricing with discounts (15–18% off)
- [ ] Export credit system: counter per workspace per billing cycle
- [ ] API usage monitoring: counter per workspace per billing cycle
- [ ] Founding Member programme: 50% off annual Professional, 200-seat cap
- [ ] Add-on modules: UK Deep Data Pack, Affiliate Detection, Personal Contact Enrichment, Custom Keyword Tracking, Slack/Teams Notifications, Niche Packs
- [ ] Billing portal (Stripe Customer Portal)
- [ ] Team seat management (invite, remove, role assignment)
- [ ] Workspace sharing + SSO (Business+)

**Definition of done:** Test customer can sign up → select tier → pay via Stripe → access tier-appropriate features. Downgrade/upgrade flow works. Export credits decrement correctly.

---

## Phase 6 — Scale and automation
**Stack:** 6

- [ ] AI summary generation pipeline (Llama 3 8B self-hosted or GPT-4o mini)
- [ ] Monthly PDF report automation per saved list
- [ ] Alert system: technology changes, new domains, DR/DA shifts, SERP feature gains/losses
- [ ] Slack/Teams webhook delivery
- [ ] Zero-touch operations runbook (auto-scaling, circuit breakers, cost alerts)
- [ ] Monitoring stack: Prometheus + Grafana dashboards (agent health, queue depth, cost burn rate)
- [ ] Public changelog view in UI
- [ ] QA dashboard: data drift detection, error rate trends

**Definition of done:** Alert fires correctly for a test technology change. Monthly report PDF generates and emails. Grafana dashboard shows all 7 agent queue depths.

---

## Phase 7 — US market expansion
**Stack:** 7 (expansion layer)

**Entry criteria (all must be met before starting):**
- [ ] UK month-6 cohort retention ≥ 70%
- [ ] UK MRR ≥ £25,000
- [ ] Provider interface abstraction complete (no hard-coded UK assumptions in agents)
- [ ] ≥ 3 Enterprise customers validate cross-country demand

**Tasks:**
- [ ] US keyword set (separate from UK — different modifiers: "free shipping", "coupon", "BOPIS")
- [ ] DataForSEO US geo parameters (google.com, English US)
- [ ] Multi-currency UI (GBP + USD)
- [ ] US company registry enrichment (SEC EDGAR, state registries vs Companies House)
- [ ] CCPA/CPRA compliance layer (separate from UK GDPR)
- [ ] US PostgreSQL read replica for latency
- [ ] US pricing page

---

## Cost model at scale

| Scale | Domains tracked | Monthly infra | Monthly data APIs | Total/mo | Break-even MRR |
|-------|----------------|---------------|-------------------|----------|----------------|
| MVP | 10,000 | £400 | £200 | £600 | £600 (16 Starters) |
| Growth | 100,000 | £2,500 | £800 | £3,300 | £3,300 (28 Professionals) |
| Scale | 500,000 | £8,000 | £3,000 | £11,000 | £11,000 (40 Business) |
| Full UK | 1,000,000 | £14,000 | £5,500 | £19,500 | £19,500 (26 Enterprise) |

---

## Revenue targets

| Month | Free users | Paid users | MRR | Key milestone |
|-------|-----------|------------|-----|---------------|
| 3 | 500 | 50 | £2,475 | Founding members |
| 6 | 2,000 | 150 | £7,500 | Post AppSumo/ProductHunt |
| 9 | 4,000 | 300 | £18,000 | Organic growth + content |
| 12 | 7,000 | 500 | £32,000 | Full tier mix + first Enterprise |

---

## Launch sequence (Months 1–6)

| Month | Activity |
|-------|---------|
| 1–3 | Phases 1–3 (data model, agents, API). Founding Member programme open at 50% off annual Professional. Max 200 seats. |
| 3–4 | Phase 4 MVP frontend live. AppSumo Lifetime Deal (~500–1,000 lifetime users for validation). |
| 4–5 | ProductHunt launch. 40% off first year. |
| 5–6 | Phase 5 (full monetisation). Phase 6 automation begins. |
| 6+ | Standard pricing. Focus on UK full coverage (500K domains). Begin US entry criteria tracking. |
