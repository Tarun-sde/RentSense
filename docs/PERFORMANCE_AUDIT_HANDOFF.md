# RentSense Performance Audit Handoff

## 1. Executive Summary

RentSense is a portfolio-scale fleet control tower. The expected production load for this audit is a small number of concurrent demo users, seven assets today, telemetry every five seconds when the optional simulator runs, and eventual growth to 100-10,000 assets. The repository is functionally broad and well tested on the backend, but its main read paths perform too many database round trips for a database hosted across regions.

The strongest explanation for the measured `GET /api/v1/equipment` time (4.732588 seconds inside the backend container, 6.123103 seconds publicly) is a confirmed N+1 query pattern. One equipment list can lazily load rentals, telemetry, sites, and operators per asset. The dashboard, anomalies, and recommendations repeat the same pattern. Each round trip crosses Azure UAE North to Neon AWS us-east-2, so even seven assets are visibly slow.

The other P0 defects are: `GET /forecasts` mutates the database and normally inserts a new batch on every request; the frontend intentionally bypasses all caching and reloads on every mount; the SSE “LIVE” state means only that a connection opened, not that telemetry is fresh; and fixed September 2026 seed dates make the live demo increasingly overdue and financially misleading.

No application code, database, deployment, or infrastructure was changed. Only this handoff was created.

## 2. Current Architecture and Deployment

```text
Browser (React client pages)
  -> public Azure Container App: Next.js 16 / Node 20
     -> Next.js /api/:path* rewrite
        -> full public HTTPS hostname of FastAPI Azure Container App
           -> synchronous FastAPI route / SQLAlchemy session
              -> Neon PostgreSQL in AWS us-east-2 (Ohio)

Optional simulator container
  -> POST /api/v1/telemetry
     -> PostgreSQL write + anomaly/alert work
     -> in-process asyncio queues
        -> GET /api/v1/telemetry/stream (SSE)
           -> browser EventSource
```

- Browser code: every page under `frontend/app` is a client component; data helpers are in `frontend/lib/api.ts`; SSE and fallback polling are in `frontend/lib/useTelemetryStream.ts`.
- Next.js server: `frontend/next.config.ts` rewrites `/api/*` to a hardcoded Azure backend hostname. The production image runs `next start`.
- FastAPI: `backend/main.py` mounts `backend/app/api/v1/router.py`. Route functions are mostly synchronous and therefore run in FastAPI's worker thread pool.
- Database: SQLAlchemy's synchronous engine is defined in `backend/app/db/session.py`; models are under `backend/app/models`; Alembic has three migrations.
- Background/optional: `simulator/main.py` posts telemetry. There is no durable event broker or separate job worker. The SSE connection registry exists only in one backend process.
- Local Docker Compose adds Nginx and PostgreSQL. The described Azure deployment does not use this Nginx path, and the frontend rewrite targets the backend's public FQDN despite the stated internal-only ingress design. Verify the deployed ingress/DNS behavior.

Production constraints supplied with the task: backend 0.25 vCPU/0.5 GiB, one replica; frontend 0.5 vCPU/1 GiB, scale-to-zero allowed; Azure UAE North; Neon Ohio. These constraints make round-trip count, cold starts, and image size more important than CPU micro-optimizations.

## 3. Verified Baseline and Known Measurements

| Item | Status | Evidence |
|---|---|---|
| Backend equipment request | Supplied measurement | 4.732588 s from inside backend container |
| Public equipment request | Supplied measurement | 6.123103 s |
| Dataset | Supplied and code-confirmed | Seeder defines 7 equipment records and 6 telemetry points per asset |
| Frontend lint | Verified 2026-10-22 | `npm run lint` completed with exit code 0 |
| Backend tests | Not run | `/usr/bin/python` has no `pytest`; dependencies were not installed |
| Test inventory | Static inspection | About 145 backend `test_*` functions; no frontend test files; no tracked CI workflow |
| Local installed frontend | Observed, not production image | `node_modules` 750 MiB; `.next` 183 MiB, including dev cache/source maps |

Do not treat local directory sizes as production image sizes. Measure the built image directly after switching to standalone output.

## 4. Repository/File Dependency Map

| User flow | Frontend | API | Main backend/database path |
|---|---|---|---|
| Dashboard | `frontend/app/page.tsx` | dashboard, equipment, alerts, recommendations | `dashboard.py`, `equipment.py`, recommendation generation and sync |
| Assets | `frontend/app/assets/page.tsx` | equipment | `equipment.py:list_equipment` -> `equipment_service.py` -> ORM relationships |
| Asset detail | `frontend/app/assets/[id]/page.tsx` | equipment detail, anomalies, recommendations | three independent API calls; detail hydrates full relationship collections |
| Actions | `frontend/app/actions/page.tsx` | actions, sites, equipment | list reads plus authenticated mutations in `actions.py` |
| Forecast | `frontend/app/forecast/page.tsx` | forecasts, sites | deterministic generator plus database sync on GET |
| Impact | `frontend/app/impact/page.tsx` | impact, sites | `impact_engine.py:get_fleet_impact_summary` |
| Telemetry | dashboard/detail hooks | SSE plus equipment/dashboard polling | public telemetry ingest, in-memory queues, PostgreSQL |
| Chat | `frontend/components/chat/ChatAssistant.tsx` | chat/status and chat/stream | live context queries plus external Gemini call |
| Authentication | login/middleware/API calls | auth login/logout/me | JWT in HttpOnly cookie; user lookup per protected request |

Important configuration: `docker-compose.yml`, `backend/Dockerfile`, `backend/docker-entrypoint.sh`, `frontend/Dockerfile`, `frontend/next.config.ts`, `nginx/nginx.conf`, `.dockerignore` files, and `.env.example`.

## 5. Critical Performance Findings

### F1 — Fleet reads issue N+1 queries across a high-latency region

- **Severity / confidence:** P0, Confirmed.
- **Evidence:** `backend/app/api/v1/equipment.py:26-64` loads all equipment and calls `build_equipment_list_item` per row. `backend/app/services/equipment_service.py:15-55` accesses lazy `rentals`, `telemetry`, `site`, and `operator` relationships. `dashboard.py:19-36`, `anomaly_engine.py:363-384`, and `recommendation_engine.py:213-235` repeat per-equipment access or explicit queries.
- **Mechanism:** For seven assets, equipment listing can make one base query, up to two collection queries per asset, and site/operator queries for active rentals. Dashboard and intelligence calls add similar traffic. Remote database latency dominates the small amount of Python work.
- **Growth:** Query count grows linearly with assets; relationship hydration also loads every historical rental/telemetry record. At 1,000 or 10,000 assets the endpoint is not viable.
- **Correction:** Build one shared fleet snapshot query. Fetch equipment plus current open rental/site/operator and latest telemetry in a bounded number of SQL statements (PostgreSQL window function or `DISTINCT ON`, plus `selectinload` only where appropriate). Reuse it in equipment, dashboard, anomalies, and recommendations. Push type/search/site filters and pagination into SQL.
- **Regression risks:** Preserve status precedence, records without telemetry, missing site/operator cases, and deterministic ordering. Add a query-count assertion before changing behavior.

### F2 — Forecast GET writes an effectively unique batch on every request

- **Severity / confidence:** P0, Confirmed.
- **Evidence:** `backend/app/api/v1/forecasts.py:29-39` generates then synchronizes forecasts during GET. `forecasting.py:224` uses `current_time + timedelta(weeks=w)`, including current microseconds. `forecasting.py:268-301` checks exact `(site_id, equipment_type, forecast_date)` equality and then commits. A later request normally has different timestamps and does not match. Default output is 3 sites × 6 types × 4 weeks = 72 existence queries/inserts per request.
- **Mechanism:** A read creates database writes, performs one lookup per forecast, grows the table indefinitely, and adds many cross-region round trips. Repeated page navigation is enough to trigger it.
- **Correction:** The smallest fix is to stop syncing from the GET because responses are computed in memory and no read path consumes persisted forecasts. If persistence is required, normalize to a week boundary, add a unique constraint, and use one bulk PostgreSQL upsert from an explicit job or mutation.
- **Regression risks:** Confirm no external reporting consumer relies on persisted forecast rows. Existing duplicate rows need a separate, reviewed cleanup plan; do not delete them in the code change.

### F3 — Every navigation starts uncached client fetches and resets to skeletons

- **Severity / confidence:** P0 for demo responsiveness, Confirmed.
- **Evidence:** All read helpers in `frontend/lib/api.ts` use `cache: "no-store"`. Dashboard, assets, actions, forecast, impact, and detail pages are client components and fetch in mount effects. Each sets loading true before requests (`page.tsx:29-48`, `assets/page.tsx:27-43`, `actions/page.tsx:52-74`, `forecast/page.tsx:35-55`, `impact/page.tsx:34-54`, detail `:50-73`). There is no shared client cache or retained route data.
- **Mechanism:** Client navigation remounts pages, discards prior results, shows skeletons, and repeats slow backend calls. The dashboard makes four calls; asset detail makes three. `Promise.all` makes required requests wait for the slowest, though dashboard/detail deliberately isolate some optional failures.
- **Correction:** First make backend reads fast. Then use the App Router's server data path for initial read-only data and a short revalidation window, or add a minimal shared cache/deduplication layer already supported by React/Next. Retain previous data while refreshing. Do not add Redux or Redis.
- **Regression risks:** Do not cache authenticated mutations or stale operational state for long. Invalidate/refresh after check-in, checkout, action, and equipment creation.

### F4 — The date-fixed demo silently changes meaning over time

- **Severity / confidence:** P0 for demo correctness, Confirmed.
- **Evidence:** `backend/app/seed/seed.py:29` anchors all data to 2026-09-01. Active due dates are offsets from that instant, including an intentionally two-day overdue rental at seed time (`:301-311`). Status and anomaly code compare these values with the actual clock. On 2026-10-22, multiple active rentals are many weeks overdue, not in the intended mixed status distribution.
- **Mechanism:** The same immutable seed produces increasingly severe overdue statuses, recommendations, and surcharge/impact narratives. Seeded messages remain frozen at “48.0h overdue,” disagreeing with live calculations.
- **Correction:** Keep deterministic relative offsets, but choose the anchor at first demo initialization (UTC day boundary) and persist a seed/version marker. For tests, pass an explicit fixed anchor. Never reseed an existing non-empty deployment just to move dates.
- **Regression risks:** Changing the default anchor can change snapshot tests and demo screenshots. Never call the destructive `reset=True` path automatically on a populated database.

### F5 — SSE health and fallback behavior create false “LIVE” and expensive retry loops

- **Severity / confidence:** P1, Confirmed behavior; production frequency Requires Measurement.
- **Evidence:** `frontend/lib/useTelemetryStream.ts:100-104` sets `LIVE` on socket open. Heartbeats do not update `lastEventTime`; there is no freshness timeout. On any error it starts polling two already-expensive endpoints every 6 seconds and retries SSE every 5 seconds (`:118-133`). Dashboard and asset detail each instantiate the hook, so navigation reconnects; separate mounted consumers would create separate streams.
- **Mechanism:** With no simulator, a healthy idle stream remains “LIVE” forever although no fresh telemetry exists. A broken proxy/backend creates repeated equipment+dashboard load. Detail fallback calls its full three-request `loadDetail`, while the hook also fetches equipment/dashboard and discards the latter data through the detail callback contract.
- **Correction:** Display connection health separately from telemetry freshness. Track the last telemetry timestamp and show STALE when older than a chosen demo threshold. Back off reconnects with jitter and cap polling frequency. For detail, use an asset-specific fallback or let the callback own polling. A layout-level singleton stream is optional only if simultaneous consumers are demonstrated.
- **Regression risks:** Avoid declaring a quiet fleet offline merely because no packets are expected. Keep cleanup coverage for EventSource, timers, and backend subscriber queues.

## 6. Backend Database Query Findings

### F6 — Detail reads hydrate unbounded history to return bounded slices

- **Severity / confidence:** P1 at scale, Confirmed.
- **Evidence:** `equipment_service.py:101-104` slices `equipment.telemetry[:20]` only after lazy-loading the entire ordered telemetry collection, and returns all rentals, alerts (filtered in Python), and audit events. The endpoint has no history pagination.
- **Correction:** Query the last 20 telemetry rows directly, query only open alerts, and paginate rental/audit histories. For seven assets this is not the current bottleneck; it becomes necessary as telemetry accumulates.
- **Regression risks:** Maintain descending chronology and response shape.

### F7 — Filtering and pagination happen after full fleet enrichment

- **Severity / confidence:** P1, Confirmed.
- **Evidence:** `equipment.py:26-64` only applies type in SQL. Search, site, and derived status filters run after every row has been enriched. There is no limit/offset or cursor.
- **Correction:** Push search and site predicates into SQL; add bounded pagination. Derived status may require a snapshot subquery or can remain post-query for the seven-record demo, but pagination semantics must be defined if status stays computed in Python.
- **Regression risks:** ILIKE/JSON model search behavior and case handling must remain compatible.

### F8 — Read endpoints perform mutable recommendation and alert work

- **Severity / confidence:** P1, Confirmed.
- **Evidence:** `recommendations.py:33-35` regenerates and commits recommendations on every GET. `recommendation_engine.py:242-283` does a lookup per result and refreshes every row after commit. Telemetry ingest commits the telemetry row, then `alert_service` performs additional sync/commit work.
- **Correction:** Make recommendation GET read-only. Generate/sync during telemetry ingest or an explicit refresh operation, using batch upsert and a uniqueness rule. Keep a single transaction for telemetry plus derived alert state where practical.
- **Regression risks:** Ensure stale recommendations are resolved/expired and ingest failures cannot leave contradictory telemetry and alert state.

### F9 — Indexes are numerous but do not match the hottest compound predicates

- **Severity / confidence:** P1 at 1,000+ records, Likely; verify with `EXPLAIN (ANALYZE, BUFFERS)`.
- **Evidence:** Migrations mostly create single-column indexes. Hot predicates are `(equipment_id, checked_in_at IS NULL)`, `(equipment_id, status, type)`, and ordered `(status, created_at)`. Telemetry correctly has `(equipment_id, timestamp)` but should be descending for latest-row access. Forecasts lack a uniqueness constraint for their natural key.
- **Correction:** After query consolidation, measure and add only indexes used by plans: a partial active-rental index, latest-telemetry compound index, and natural-key uniqueness for persisted forecasts/recommendations if persistence remains.
- **Regression risks:** Each index increases ingest/write cost and Neon storage; remove redundant single-column indexes only after plan verification.

### F10 — Pool and timeout behavior is implicit

- **Severity / confidence:** P1 reliability, Requires Measurement.
- **Evidence:** `backend/app/db/session.py:10-14` sets only `pool_pre_ping=True`. There is no explicit connect timeout, statement timeout, pool size/overflow, recycle policy, or request timing. Uvicorn starts one process.
- **Correction:** First co-locate database and app. Then set conservative pool bounds for 0.25 vCPU/0.5 GiB and Neon limits, plus driver connect timeout and PostgreSQL statement timeout. Add route and query-count/timing logs without parameter values.
- **Regression risks:** Pools that are too small serialize SSE-adjacent REST traffic; too large can exhaust Neon connections. Measure before choosing numbers.

## 7. Frontend Fetching and Rendering Findings

### F11 — Duplicate reference-data requests and whole-page failure coupling

- **Severity / confidence:** P1 for navigation, Confirmed.
- **Evidence:** Actions fetch actions/sites/equipment together; forecast refetches sites whenever horizon changes; impact refetches sites whenever site selection changes. These use `Promise.all`, so a sites failure hides otherwise usable page data. No AbortController prevents stale updates after rapid selection/navigation.
- **Correction:** Cache sites/equipment reference data for the session or render it from a server parent. Fetch changed primary data independently; pass `AbortSignal` through helpers and ignore aborted responses. Preserve old content during refresh.
- **Regression risks:** Avoid showing options that were removed server-side indefinitely; a short TTL or mutation invalidation is enough.

### F12 — Heavy browser libraries are eagerly bundled into route trees

- **Severity / confidence:** P2, Confirmed code path; bundle impact Requires Measurement.
- **Evidence:** Mapbox is statically imported by `FleetMapCard.tsx` and `MiniMap.tsx`; Recharts is statically imported on dashboard/detail/forecast/impact; `html5-qrcode` is used by the scan route. The local dev output contains a roughly 3.1 MiB Mapbox JavaScript chunk plus source maps, but that is not a production transfer measurement.
- **Correction:** Run a production bundle analysis first. Dynamically import maps, charts below the fold, and the QR scanner with loading placeholders; render maps only when visible. This matters less than database latency for seven records.
- **Regression risks:** Dynamic components are client-only and can shift layout; reserve fixed dimensions and test navigation.

Client-side list filtering and chart data transforms are trivial for seven records and should not be memoized yet. Virtualization becomes useful only after pagination still leaves hundreds of rows rendered. Search currently filters an already-loaded seven-item array, so debouncing is unnecessary until search is server-side.

## 8. Real-Time Telemetry Findings

- Browser establishment: `EventSource` connects through `/api/v1/telemetry/stream`; native EventSource auto-retry is disabled by explicitly closing on error and replaced with a fixed 5-second timer.
- Backend lifecycle: `telemetry.py:151-172` sends an initial comment, waits on a per-client bounded queue, emits a 15-second comment heartbeat, detects disconnect, and unregisters in `finally`. This cleanup is sound for normal cancellation.
- Buffering: FastAPI sends `X-Accel-Buffering: no`. Local Nginx disables buffering and sets a one-day timeout. The Azure/Next rewrite path is not configured in this repository, so end-to-end proxy streaming and timeout behavior remain unverified.
- Resource use: each connection owns a queue of at most 100 events. Oldest events are dropped, preventing unbounded memory. With one backend replica, in-memory fanout works. It will lose events across restarts and will not span replicas; current max-replica=1 makes that acceptable.
- Blocking path: `ingest_telemetry` is `async def` but performs synchronous SQLAlchemy queries/commits directly on the event loop before awaiting broadcast (`telemetry.py:28-93`). Slow Ohio database calls can block other async streams. Change it to a synchronous route or move to an async database stack only if broader async conversion is justified; the synchronous-route change is smaller.
- Cost/correctness: telemetry POST is public because the entire telemetry router is mounted without auth. An unauthenticated caller can create high-rate records and trigger database/anomaly/notification work. Protect ingestion with a simulator/device credential and rate/size limits; keep stream access policy explicit.
- Simulator absent: stream stays connected and sends only heartbeat comments. UI reports LIVE even with stale seeded telemetry. See F5.

## 9. Docker and Deployment Findings

### F13 — Frontend runner copies all build dependencies instead of standalone output

- **Severity / confidence:** P1 for cold start/pull/storage, Confirmed.
- **Evidence:** `frontend/Dockerfile:31-34` copies `package.json`, all builder `node_modules`, all `.next`, and public files. `next.config.ts` does not enable `output: "standalone"`.
- **Correction:** Enable Next standalone output and copy `.next/standalone`, `.next/static`, and `public` into the runner. Keep the multi-stage build. Measure `docker image inspect` before/after.
- **Regression risks:** Verify rewrites, public assets, and runtime environment variables. `NEXT_PUBLIC_*` values are build-time constants, not runtime configuration.

### F14 — Cross-region database placement multiplies every query defect

- **Severity / confidence:** P0 architecture/config, Strongly supported.
- **Evidence:** Supplied production regions are Azure UAE North and Neon AWS us-east-2. The API is already 4.7 seconds from inside the backend for seven assets, and confirmed code makes many round trips.
- **Correction:** Remove N+1 traffic first, then place PostgreSQL in the nearest practical region to the app (or move the app near the database). Region alignment is likely the largest infrastructure improvement and does not require new services.
- **Regression risks:** Database migration/region moves require backups, tested restore, downtime/replication planning, and secret rotation. Do not move production data as part of a code fix.

- Backend startup runs `alembic upgrade head`, two database bootstrap scripts, and password hashing/user lookup before Uvicorn starts. This is safe for one replica but adds cold-start/database dependency and can race with multiple replicas. Keep for the one-replica demo or move migration to a deployment job before scaling.
- Frontend min replicas 0 guarantees occasional cold starts. For a portfolio demo, choose between lowest cost and predictable first impression; a scheduled warm-up or min replica 1 costs money. Measure cold-start p50/p95 before changing.
- Health checks exist in Dockerfiles and Compose. Azure probe configuration is not present here and remains unverified.
- `.dockerignore` files correctly exclude `.env`, dependencies, build output, VCS data, and Python caches.
- `next.config.ts` hardcodes the backend public FQDN. This conflicts with the stated internal-only ingress and makes environment promotion harder. Use a server-only environment destination at build/deploy time and confirm Azure internal DNS; do not expose the backend merely to satisfy the rewrite.

## 10. Date-Sensitive Demo Data Findings

- F4 is the main defect. `ANCHOR_TIME` is fixed and all rental, telemetry, alert, action, forecast, impact, and audit dates derive from it.
- The seeder is mostly idempotent when `reset=False`, using existence checks. The command-line entry at `seed.py:1042` calls `reset=True`, and `reset_database` bulk-deletes nearly all demo domain tables. It intentionally omits users. Treat this script as destructive and never run it against production.
- Container startup calls `seed_database(db, reset=True)` only when the equipment table is absent or empty. It also runs Alembic first, so the “table absent” branch is normally unreachable after a successful migration. An accidentally empty production equipment table would cause a destructive replacement of related domain data.
- Hardcoded forecast histories in `forecasting.py:161-187` are demo fixtures, not database-derived forecasts. Label them as demo data or replace them later; this is a product-correctness issue, not today’s latency bottleneck.
- Old dates influence overdue anomalies and recommendations. Existing impact records are seeded fixed amounts; live action impact calculation uses current state, so UI totals can mix historical seeded narratives with current overdue conditions.

## 11. Security and Reliability Risks

### F15 — Cookie transport and expensive public endpoints need production hardening

- **Severity / confidence:** P0 security/cost, Confirmed.
- **Evidence:** `auth.py:39-47` always sets `secure=False`, even in production. Telemetry ingestion and chat routers are public (`router.py:23-33`). Chat invokes an external paid/limited service and has no visible rate limit or request timeout at the route boundary. Mutation routes for rentals/actions and equipment creation are authenticated.
- **Correction:** Set `secure=True` in production based on trusted configuration, retain HttpOnly/SameSite, and test forwarded HTTPS behavior. Authenticate telemetry ingestion with a separate device/simulator secret. Require user auth and a simple per-instance rate/concurrency limit for chat, plus explicit upstream timeout. For max replica 1, an in-memory limiter is an acceptable documented ceiling.
- **Regression risks:** Secure cookies do not work over local HTTP, so preserve a development-only false setting. EventSource credentials/cross-origin policy must be tested if stream auth changes.

### F16 — Impact site filter is accepted but ignored

- **Severity / confidence:** P1 correctness, Confirmed.
- **Evidence:** `impact.py:20-29` accepts `site_id` then calls `get_fleet_impact_summary(db)` without it. The frontend reloads on site selection and therefore shows fleet-wide values under a selected site.
- **Correction:** Pass the filter into the service and apply it consistently to realized records, pending recommendations where a site can be identified, counts, and breakdowns. Add a two-site regression test.
- **Regression risks:** Define whether “Central Logistics”/null-site records belong in a site-specific view.

- Login has no rate limiting; bcrypt makes brute-force attempts intentionally CPU-expensive on a 0.25-vCPU container. Add a small IP/email attempt limiter at ingress or app level.
- `AUTH_ENABLED` is configured but not used to govern route protection. Current protected dependencies always require auth; remove the dead flag or implement only if a documented mode truly needs it.
- Global exception logging includes exception strings. No secrets were printed during this audit, but external-service/database exceptions should be reviewed for credential-bearing URLs before production logging.
- Checkout validates “no active rental” then inserts without a database uniqueness constraint. Concurrent requests can create two open rentals. Add a partial unique index on `rentals(equipment_id) WHERE checked_in_at IS NULL` and handle integrity errors.

## 12. Recommended Optimizations (P0 / P1 / P2)

### P0

1. Consolidate fleet/current-rental/latest-telemetry queries and reuse the snapshot across equipment/dashboard/anomaly/recommendation paths (F1).
2. Stop forecast persistence on GET; prevent duplicate growth (F2).
3. Co-locate application and database after query-count fixes; measure both stages (F14).
4. Replace fixed demo dates safely for new deployments without reseeding existing data (F4).
5. Restore safe production boundaries: Secure cookie, protected/rate-limited telemetry and chat (F15).
6. After backend latency falls, retain/cached initial frontend data across navigation (F3).

### P1

7. Bound equipment detail histories and move filters/pagination to SQL (F6-F7).
8. Remove recommendation mutations from GET and batch derived-state writes (F8).
9. Correct SSE freshness, fallback scope, and retry backoff; make sync DB work avoid blocking the async event loop (F5).
10. Fix site-filter correctness and add active-rental concurrency protection (F16).
11. Build the frontend as Next standalone and verify Azure probe/rewrite behavior (F13).
12. Add measured compound indexes and explicit database timeouts/pool bounds (F9-F10).

### P2

13. Independently load/cache reference data and add request cancellation (F11).
14. Measure bundles and dynamically load Mapbox/Recharts/QR only where useful (F12).
15. Add frontend tests and CI only for the critical navigation/auth/SSE behavior listed below.

## 13. Exact Files and Functions Requiring Changes

| Priority | File | Function/config | Intended change |
|---|---|---|---|
| P0 | `backend/app/services/equipment_service.py` | `get_current_rental`, `get_latest_telemetry`, builders | Accept preloaded/batched snapshot; stop lazy full collections |
| P0 | `backend/app/api/v1/equipment.py` | `list_equipment`, detail | SQL filtering/pagination and bounded relation queries |
| P0 | `backend/app/api/v1/dashboard.py` | `get_dashboard_kpis` | Reuse fleet snapshot/SQL aggregation |
| P0 | `backend/app/analytics/anomaly_engine.py` | `evaluate_fleet_anomalies` | Remove per-asset queries |
| P0 | `backend/app/analytics/recommendation_engine.py` | fleet generation/sync | Batch reads; separate/batch writes |
| P0 | `backend/app/api/v1/forecasts.py` | `get_demand_forecasts` | Remove sync side effect |
| P0 | `backend/app/analytics/forecasting.py` | `sync_forecasts_to_db` | Delete if unused, otherwise normalize/bulk upsert |
| P0 | `backend/app/seed/seed.py` | `ANCHOR_TIME`, seed entry point | Relative first-seed anchor; guard destructive reset |
| P0 | `backend/app/api/v1/auth.py` | `login` | Environment-aware Secure cookie |
| P0 | `backend/app/api/v1/router.py`, `telemetry.py`, `chat.py` | router protection | Auth/device key, throttling, timeouts |
| P1 | `frontend/lib/api.ts` | all fetch helpers | Signals and deliberate cache policy |
| P1 | frontend route pages | mount loaders | server initial data/retained shared state; independent refresh |
| P1 | `frontend/lib/useTelemetryStream.ts` | hook | freshness, backoff, scoped polling |
| P1 | `backend/app/api/v1/impact.py`, `impact_engine.py` | impact summary | honor `site_id`, aggregate in SQL as volume grows |
| P1 | `backend/app/db/session.py` | engine creation | measured pool/connect/statement timeout settings |
| P1 | new Alembic migration | indexes/constraints | active rental uniqueness and measured compound indexes |
| P1 | `frontend/next.config.ts`, `frontend/Dockerfile` | build/deploy | standalone output and environment-safe backend destination |

## 14. Proposed Regression Tests

1. Equipment list returns the same schema/statuses with a fixed upper query count independent of fleet size (for example 7 vs 100 assets).
2. Dashboard, anomalies, and recommendations likewise have bounded query counts and handle no rental/no telemetry/missing assignment.
3. Two successive forecast GETs do not increase the forecast-row count; ideally GET performs zero writes.
4. Forecast natural key is unique if persistence remains, including concurrent calls.
5. Equipment detail fetches at most 20 telemetry rows and paginates history in stable descending order.
6. Seed with a supplied anchor preserves the intended ACTIVE/IDLE/DUE_SOON/OVERDUE/UNASSIGNED mix; rerun without reset is idempotent.
7. Production login cookie is Secure/HttpOnly/SameSite; development HTTP remains usable.
8. Unauthenticated telemetry ingest/chat is rejected or throttled; authorized simulator flow still broadcasts.
9. SSE UI distinguishes connected-but-stale from fresh; timers/EventSource are cleaned up; fallback backs off and does not duplicate detail requests.
10. Impact `site_id` changes totals and excludes records from other sites.
11. Concurrent checkout for one asset leaves exactly one open rental.
12. Frontend navigation back to dashboard/assets reuses visible data and does not flash zero placeholder metrics.

Existing backend coverage includes auth, actions, anomaly rules, chat, dashboard, equipment, forecasting, health, impact, intelligence APIs, models, notifications, recommendations, rentals, seed, SSE fallback, status, telemetry, production security, and an acceptance flow. Missing: query-count/performance assertions, forecast GET idempotency, impact site filtering, concurrency, frontend rendering/navigation, request cancellation, and production proxy behavior.

## 15. Benchmarking and Verification Commands

Run against a disposable/test database only. Do not run the reset seeder against production.

```bash
# Backend tests, once the existing environment has dependencies
cd backend
python -m pytest -q

# Frontend checks
cd frontend
npm run lint
npm run build

# Warm/cold endpoint timings; record DNS/connect/TTFB/total separately
curl -sS -o /dev/null -w 'connect=%{time_connect} ttfb=%{time_starttransfer} total=%{time_total}\n' \
  https://<frontend-host>/api/v1/equipment

# Repeat warm requests and preserve raw samples; do not report invented averages
for i in $(seq 1 20); do
  curl -sS -o /dev/null -w '%{time_total}\n' https://<frontend-host>/api/v1/equipment
done

# Production image sizes
docker build -t rentsense-frontend:audit frontend
docker image inspect rentsense-frontend:audit --format '{{.Size}}'
docker history rentsense-frontend:audit

# Database plans (substitute representative read-only SQL generated by SQLAlchemy)
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;
```

Instrument SQLAlchemy in tests to count `before_cursor_execute` events. Benchmark 7, 100, 1,000, and 10,000 assets with synthetic disposable data. Record response p50/p95, SQL statement count, rows loaded, payload bytes, backend CPU/memory, database time, and public-vs-container delta. For SSE, hold 1/10/50 connections, stop the simulator, interrupt the proxy, and verify freshness labels, reconnect rate, polling rate, queue cleanup, and backend memory.

## 16. Risks and Compatibility Considerations

- Status is derived from current time, rental, and latest telemetry. A SQL rewrite must preserve `status_service.py` precedence exactly.
- Eager-loading multiple one-to-many collections in one joined query causes a Cartesian row explosion. Use a latest-row subquery plus selective `selectinload`, not one giant join.
- PostgreSQL `DISTINCT ON` is efficient but SQLite tests need an alternate window-function implementation or test-specific compatibility.
- Caching improves navigation but can hide mutations. Invalidate only affected keys after successful writes.
- Authentication changes can break local HTTP, EventSource, and the simulator. Separate browser session auth from device ingestion credentials.
- Standalone Next output must include static/public assets and support the deployed rewrite configuration.
- Region migration is operationally risky and must be separately planned; code/query changes are reversible and should land first.

## 17. Recommended Implementation Order

1. Add query-count, forecast-idempotency, seed-status, impact-filter, cookie, ingestion-auth, and SSE-freshness regression tests.
2. Implement the shared fleet snapshot and convert equipment/dashboard/anomaly/recommendation reads; benchmark inside the backend.
3. Make forecast/recommendation GETs read-only and fix impact filtering/concurrent open-rental protection.
4. Harden cookie, telemetry, chat, timeouts, and telemetry sync route behavior.
5. Fix seed anchoring for new databases with strict no-reset safeguards.
6. Add frontend retained/server data, cancellation, and corrected SSE state/backoff; benchmark navigation publicly.
7. Switch frontend image to standalone output and validate assets, health, and rewrites.
8. Only after query consolidation, use query plans to add indexes/pool bounds and decide whether regional relocation is required. Regional alignment should then be scheduled as its own operational change.
9. Measure bundles and dynamically import heavy visuals only if transfer/interaction data justifies it.

## 18. Open Questions / Unverified Hypotheses

- The supplied Azure and Neon regions, replica allocations, ingress modes, and measurements were not independently queried from cloud control planes.
- The backend is described as internal-only, but the checked-in rewrite uses its full public HTTPS hostname. Confirm whether that hostname is reachable from the frontend container and whether traffic stays internal.
- Azure Container Apps proxy buffering, idle timeout, cookie forwarding, and SSE duration were not observable locally.
- No production database query plan, row counts beyond supplied seed facts, Neon pool limits, or connection metrics were available.
- Backend tests could not run because the existing system Python lacks `pytest`; no dependencies were installed. Frontend lint passed. A production frontend build was not used as a benchmark, and local `.next` sizes are development artifacts.
- Browser console/network traces and Core Web Vitals were not captured because no running authenticated production session was provided.
- Actual Docker image sizes, cold-start time, warm p50/p95, frontend bundle transfer sizes, and memory under concurrent SSE clients require measurement.
- AI provider timeout/retry behavior and actual billing limits should be verified against the installed SDK and production account settings before choosing limits.

**Verdict:** Fix the cross-region N+1 reads and forecast write-on-read first; then correct demo time/auth/SSE behavior and remove navigation refetch churn.

**Not checked:** live cloud configuration, live Neon plans/data, browser runtime console, built image registry layers, and backend runtime tests for the reason above.
