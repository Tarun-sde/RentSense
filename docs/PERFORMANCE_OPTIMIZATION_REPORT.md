# RentSense performance optimization report

Date: 2026-10-22. Local implementation and verification only; no Azure deployments, image pushes, or Neon mutations.

## Outcome and original causes

The user reported 4.73 seconds inside the Azure backend container and 6.12 seconds publicly for seven assets. Those production numbers were supplied, not reproduced here. Azure UAE North to Neon AWS US East 2 remains a cross-region path; its actual network RTT and post-change API latency are **Not measured**.

Verified code-level causes:
- List serialization lazily loaded rental, site/operator and telemetry relationships per asset, including full histories.
- Dashboard and fleet intelligence repeated that work; recommendations also selected and refreshed each generated record separately.
- Forecast GET regenerated and wrote many rows on every read.
- Pages discarded server state on unmount and coupled independent requests, causing repeated loading and optional-failure blank states.
- The page-local SSE lifecycle mixed reconnect/polling with full data reloads and treated an open connection as fresh telemetry.
- The frontend runner copied all node_modules rather than the standalone runtime.
- Fixed seed timestamps aged the demo scenarios; reset-based startup seeding was unsafe.

The handoff was read and independently checked. Not every proposed fix was adopted: recommendation synchronization must preserve persisted IDs used by actions and clock-dependent recommendations; it is batched, not removed. A second descending telemetry index is unnecessary given the existing reverse index scan. The working full Azure HTTPS hostname remains unchanged.

## Measurements

Method: backend/scripts/benchmark.py creates disposable SQLite, uses a fixed seed anchor, five TestClient requests per endpoint, SQLAlchemy cursor-event statement counts, median wall-clock time and SQL execution time. Seven seeded assets, then 93 extra assets without rentals/telemetry. These are local microbenchmarks, not a 100-fully-active-asset load test. Connection setup/pre-ping and transaction commits are not included in cursor statement counts; SQL time excludes remote network RTT. Runs were not on dedicated idle hardware.

| Endpoint | 7 assets statements before → after | 7 assets median ms before → after | 100 assets statements before → after | 100 assets median ms before → after |
|---|---:|---:|---:|---:|
| equipment | 22 → 1 | 13.23 → 8.97 | 208 → 1 | 117.93 → 8.71 |
| dashboard | 16 → 2 | 10.83 → 6.93 | 202 → 2 | 105.64 → 7.26 |
| anomalies | 15 → 1 | 12.49 → 6.50 | 294 → 1 | 118.80 → 5.94 |
| recommendations, subsequent requests | 35 → 4 | 18.42 → 13.25 | 314 → 4 | 122.64 → 10.80 |
| forecasts | 145 → 1 | 51.73 → 7.55 | 145 → 1 | 43.38 → 5.88 |
| impact | 5 → 7 | 15.02 → 7.91 | 5 → 7 | 8.61 → 15.07 |
| equipment/EQX1001 | 7 → 5 | 21.20 → 9.55 | 7 → 5 | 8.92 → 19.92 |

First recommendation request: 42 → 11 statements at seven assets. Writes still depend on actual changed/generated recommendations, unlike the bounded reads.

Equipment SQL median: 0.80 → 0.44 ms (seven), 10.74 → 0.35 ms (100). Equipment response bytes unchanged: 9,685 / 37,957. Other benchmark response byte sizes also remained unchanged for these fixtures. Impact deliberately trades two extra aggregate statements for bounded ORM materialization and correct site filtering; it is not a measured latency win at 100. Detail results are noisy and not universally faster. The primary result is eliminating per-asset network round trips, not claiming every endpoint improved.

Disposable PostgreSQL 16: migrations and seed succeeded; all eight smoke-test reads returned 200 (equipment, dashboard, anomalies, recommendations, forecasts, impact, site-filtered impact, detail). EXPLAIN (ANALYZE, BUFFERS) on the seven-asset fleet query: 1.985 ms execution, 4.629 ms planning, backward scan of ix_telemetry_equipment_timestamp, rental equipment_id index scan. Tiny joined tables used sequential scans, appropriately. No production EXPLAIN ran and no schema/index migration was added.

## Backend and database changes

- One shared fleet query selects latest telemetry and current rental using correlated, limited subqueries, joins site/operator once, and uses stable ID tie-breakers.
- Read-only request snapshots do not replace ORM relationship collections (which could otherwise cause accidental persistence changes).
- Detail loads only 20 recent telemetry points, up to 100 rental/audit entries by default (maximum 500), and up to 500 active alerts.
- Equipment accepts optional limit (1–500) and offset. No limit preserves existing callers. Search/site/type filtering happens before pagination; derived status is filtered before slicing. Literal search escapes SQL wildcards.
- Alerts/actions/recommendations and telemetry history accept nonnegative offset with their existing limits and deterministic timestamp/ID ordering. Existing array response shapes remain unchanged.
- Forecast GET computes the response without persisting it. Explicit seed generation still writes forecasts.
- Impact sums/grouping happen in SQL, recent records are capped at 100, and site_id is respected.
- Chat context reuses latest-row fleet loading instead of history eager loading and dialect-specific DISTINCT behavior.
- Synchronous telemetry persistence runs in the thread pool, leaving the event loop available for SSE; anomaly failure rolls back before continuing.
- PostgreSQL pool: size 5, max overflow 2, pool wait 10s, connect timeout 10s, pre-ping retained; SQL parameter logging hidden. No arbitrary connection recycling or Neon session options were added.
- Seed is opt-in via SEED_DEMO_DATA=true and refuses to populate a nonempty domain database. Fresh demo dates are relative to now; tests explicitly use the fixed anchor. --reset remains an explicitly destructive disposable-database-only operation.
- RUN_MIGRATIONS defaults true for compatibility; set false only after a controlled migration step. No existing rows are refreshed to improve appearance.
- Production cookies default Secure; local HTTP Compose explicitly defaults AUTH_COOKIE_SECURE=false. Azure must keep it true. HttpOnly/JWT/RBAC checks remain.
- Fresh seeding no longer creates a hardcoded CI administrator or fallback-password admin. Existing users are not deleted: inspect any previously seeded CI account separately before deployment.

## Frontend cache, rendering and recovery

TanStack Query is the only server-state cache. It supplies deduplication, cancellation, invalidation and retry behavior without a bespoke request-cache implementation. One persistent root provider; browser singleton only, a new client for each server access, no shared private server cache.

Stable keys are ["api", path including filters]. Operational stale time 30 seconds; sites/operators/chat status/forecasts five minutes; garbage collection ten minutes. No automatic focus refetch. Failed reads retry at most once for server/network errors, not auth/client errors. Reads have a 20-second timeout and consume the cancellation signal. Mutations are not automatically retried.

Dashboard, fleet, detail, actions, forecast and impact subscribe independently. Cached data survives background errors and revisits; first-load skeletons do not replace cached content. Unknown headline metrics use dashes; the fleet donut waits for actual KPIs. Errors expose retry or re-login. Login/logout clear cached data. Login remains reachable when an expired cookie exists; cookie presence is not treated as JWT validity.

Successful operational mutations cancel earlier reads and invalidate operational queries; mounted queries refetch, inactive ones are marked stale. Reference data remains cached. This broad invalidation favors correctness over the complexity of per-mutation dependency maps.

Search on the seven-item fleet remains immediate and local: it produces no keystroke requests. No debounce/virtualization framework was added. Maps/charts are dynamically imported with reserved loading areas. FleetMap now records the instance before its load event so early navigation cleans up WebGL resources. Existing map fallback and token behavior are preserved. Public assets are small icons rather than large raster content; no speculative image pipeline was added.

Total .next/static before: 4,032,690 bytes; after patched build: 4,083,898 bytes. This is aggregate uncompressed output, NOT first-route transferred JS. Cache machinery slightly increases aggregate output; code splitting defers heavy route components. Initial-route network waterfall, browser paint timings, mobile visual checks and Mapbox-token rendering: **Not measured**. No claim of lower total browser bytes.

## SSE and proxy

One connection per browser tab lives above route changes (disabled on login). Opening a stream reports STALE until a fresh valid telemetry event arrives. Freshness expires after 30 seconds. Invalid/old packets cannot falsely advance equipment state. Local cache updates replace whole-dashboard reloads per packet; derived intelligence invalidates at most once per 30 seconds.

On failure the source closes; retry starts around five seconds with exponential backoff capped at 60 seconds plus under one second jitter. A 20-second handshake timeout covers hung connection attempts. Fallback polling runs every 30 seconds after the previous request finishes, skips hidden tabs and never overlaps itself. Successful reconnection revalidates missed state. A healthy but idle stream stays STALE without continuous fallback polling. Cleanup clears source and all timers. Cached equipment reads in flight are cancelled before applying events, preventing a late REST response from overwriting an event.

Existing backend 15-second comment heartbeats, disconnect cleanup, no-cache and X-Accel-Buffering headers remain. Same-origin /api rewrite and full Azure HTTPS destination remain unchanged. No backend public-ingress change. Actual Azure SSE proxy buffering, idle timeout and reconnect behavior: **Not measured**; validate with the deployment checklist. SSE fanout is process-local: keep the current single backend process/replica model; do not scale it horizontally without a measured fanout solution.

## Containers and dependency checks

Frontend standalone output copies server.js, traced runtime dependencies, static and public assets, listens on 0.0.0.0:3000, retains curl health check. NEXT_PUBLIC_API_URL and Mapbox token remain build-time args; same-origin Azure build uses an empty API URL. Runtime changes cannot change already-inlined NEXT_PUBLIC values.

Measured existing local frontend image: 1,386,073,124 bytes. First standalone image: 303,459,192 bytes (~78% smaller). This is Docker image size, not registry compressed transfer size, and the existing image was not rebuilt as a controlled baseline. Final patched frontend image: 303,458,668 bytes (78.1% smaller than the existing local image). Backend image: 405,086,327 bytes; excludes local databases, tests and scripts, keeps necessary runtime dependencies.

Next.js and eslint-config-next patched from 16.3.4 to 16.3.8 after npm audit identified advisories. Compatible transitive fixes applied without --force. Production-only npm audit: zero findings. Full audit still reports five high findings in the development ESLint/braces chain; the suggested forced fix downgrades the Next lint config incompatibly and was not applied. The old middleware filename emits a deprecation warning; no speculative routing migration was mixed in.

## Verification

Executed:
- Backend suite: 143 tests passed in 13.27s (17 deprecation warnings), isolated SQLite; existing auth, telemetry, action, forecast and seed tests included.
- New backend regression: zero/100 assets, bounded list SQL counts, literal search, pagination and invalid bounds, forecast read has no INSERT/UPDATE/DELETE.
- Frontend lint, TypeScript no-emit, production build (13 routes), and four Node regression tests: successful creation invalidation, cache dedup/revisit/failure recovery, older telemetry/history cap, stale-open/reconnect/cleanup.
- Both final Docker images built locally. Frontend container served eight route shells and a static JS asset on port 3000 (200), allowed login with an expired cookie, and redirected an unauthenticated dashboard request (307). This verifies HTML/static delivery, not hydrated page behavior.
- SQLite backend container: health and seven equipment records.
- Disposable PostgreSQL container: migrations, seed, eight read routes, real login and Secure + HttpOnly cookie assertions; SQL EXPLAIN above.
- Direct backend SSE handshake returned the connected comment; Azure proxy streaming remains unverified.
- git diff --check.

Browser end-to-end UI tests were not run; the repository has no browser harness. Unit tests are not a substitute for browser validation. Azure proxy and Mapbox live rendering are not certified by these checks.

Reproduce:
```bash
DEBUG=false backend/venv/bin/python -m pytest backend/app/tests -q
backend/venv/bin/python backend/scripts/benchmark.py
cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm test
npm run build
npm audit --omit=dev
```

## Files changed

Backend:
- backend/app/services/{equipment_service,chat_context_service}.py
- backend/app/analytics/{anomaly_engine,recommendation_engine,impact_engine}.py
- backend/app/api/v1/{equipment,dashboard,anomalies,recommendations,forecasts,impact,telemetry,auth,alerts,actions}.py
- backend/app/core/config.py; backend/app/db/session.py
- backend/app/seed/seed.py; backend/docker-entrypoint.sh; backend/.dockerignore
- backend/app/tests/{conftest,test_seed,test_performance_regression}.py
- backend/scripts/benchmark.py; docker-compose.yml

Frontend:
- frontend/lib/{api,auth,query-client,useApiQuery,useTelemetryStream,telemetry-cache,telemetry-connection}.ts
- frontend/components/{QueryProvider,TelemetryProvider}.tsx; frontend/components/ui/QueryError.tsx
- frontend/components/dashboard/{HeroOverview,FleetMapCard}.tsx
- frontend/components/layout/{AppShell,TopBar}.tsx
- frontend/app/{layout,page}.tsx; frontend/app/{assets,actions,forecast,impact}/page.tsx; frontend/app/assets/[id]/page.tsx
- frontend/middleware.ts; frontend/next.config.ts; frontend/Dockerfile
- frontend/package.json; frontend/package-lock.json; frontend/tests/runtime.test.cjs

Docs/config: this report, README.md and .env.example. Pre-existing icon/favicon changes and layout icon metadata were preserved, not authored as performance work. PERFORMANCE_AUDIT_HANDOFF.md is the prior handoff, not a new implementation finding.

## Remaining limits and operational tradeoffs

- Cross-region RTT and frontend min replicas=0 cold starts remain. No budget-increasing replica/region changes were made. Measure warm/cold separately before spending money.
- Fleet-wide derived status still scans one latest-row snapshot per asset, O(n), though SQL round trips are bounded. Status-filter pagination currently loads matching fleet snapshots before slicing. At much larger fleets, measure and push the derived projection into SQL or introduce a bounded purpose-specific endpoint.
- Default equipment/reference lists preserve compatibility and are not hard-capped. UI continues showing the small fleet in full; actions/alerts use existing first-page limits. API offset permits deeper access, but full large-fleet UI pagination is a future product task.
- Recommendation GET still writes changed calculations and concurrent generation can race without a uniqueness/upsert redesign. Keep this known ceiling visible; measure before adding background infrastructure.
- No distributed cache, worker, broker, blanket memoization or extra production service.
- Chat/telemetry public endpoint policies were preserved rather than silently changing simulator/demo authentication; rate limits/device credentials and external AI timeouts deserve a separate security/reliability review.
- SQLite regression assertions are supplemented by PostgreSQL smoke tests, not a full PostgreSQL test suite or sustained load run.
- New relative seeding never repairs existing overdue records; those dates remain truthful. Use only an explicitly disposable database for scenario refresh.
- Existing seeded known-password accounts, if any, remain in existing databases. Remove/rotate them through an approved production operation.

## Deployment commands — NOT executed

Confirm Docker Hub namespace, registry access and existing Azure secret references first. These commands intentionally do not change ingress, region, replicas or database contents. Use immutable tags. Mapbox is a public browser token; set it in your shell before building if the interactive map is required.

```bash
export RENTSENSE_REGISTRY=tarun1joshi
export RENTSENSE_TAG=perf-20261022
docker build -t "$RENTSENSE_REGISTRY/rentsense-backend:$RENTSENSE_TAG" backend
docker build --build-arg NEXT_PUBLIC_API_URL= \
  --build-arg NEXT_PUBLIC_MAPBOX_TOKEN="$NEXT_PUBLIC_MAPBOX_TOKEN" \
  -t "$RENTSENSE_REGISTRY/rentsense-frontend:$RENTSENSE_TAG" frontend
docker login
docker push "$RENTSENSE_REGISTRY/rentsense-backend:$RENTSENSE_TAG"
docker push "$RENTSENSE_REGISTRY/rentsense-frontend:$RENTSENSE_TAG"

az containerapp update --resource-group rg-rentsense --name rentsense-backend \
  --image "$RENTSENSE_REGISTRY/rentsense-backend:$RENTSENSE_TAG" \
  --set-env-vars ENVIRONMENT=production AUTH_COOKIE_SECURE=true SEED_DEMO_DATA=false RUN_MIGRATIONS=true
az containerapp update --resource-group rg-rentsense --name rentsense-frontend \
  --image "$RENTSENSE_REGISTRY/rentsense-frontend:$RENTSENSE_TAG"

az containerapp revision list --resource-group rg-rentsense --name rentsense-backend --output table
az containerapp revision list --resource-group rg-rentsense --name rentsense-frontend --output table
```

Preserve current DATABASE_URL/JWT/admin secret references and full backend hostname. No new migration is required by this patch. RUN_MIGRATIONS=true executes already-existing Alembic head; review pending migrations before deploying. Azure Secure cookies require HTTPS. Local Compose defaults differ intentionally; use SEED_DEMO_DATA=true only when initializing a fresh, empty local demo database.

### Manual acceptance after deployment

1. Record current image/revision IDs before updating. Open frontend HTTPS, log in, verify HttpOnly/Secure cookie and protected mutation rejection when logged out.
2. Visit Dashboard → Fleet Assets → Dashboard within 30 seconds with DevTools network open. Confirm cached cards appear immediately, no duplicate identical reads, and one EventSource per tab.
3. Visit detail, actions, forecast and impact. Change filters; verify data updates independently and empty results are explicit.
4. Complete an authorized disposable-demo action/check-in/out; verify affected cached pages update. Do not perform this on real data merely to test.
5. Block one optional endpoint; other panels should render. Block network then restore; cached content should persist and retries should recover.
6. Leave simulator inactive: status must become STALE, not LIVE. Restart simulator: packets should update equipment without repeated whole-dashboard fetches. Disconnect stream: check bounded retries and non-overlapping 30-second fallback.
7. Confirm map rendering with the deployed token, early navigation away, mobile widths, scanner and modal flows.
8. Measure equipment/dashboard five warm requests from inside backend and through frontend, plus a separate cold frontend visit. Record p50/p95, SQL count and RTT; compare with the supplied 4.73/6.12-second baseline.

### Rollback

Record the previous backend/frontend image tags before deploying. Re-run the two az containerapp update commands with those exact known-good images (not assumed tags), retaining correct production secret references and ingress. There is no new schema migration to downgrade. Do not reseed or reset Neon. Old startup images may have unsafe seed behavior: inspect before rollback and keep seeding disabled where supported. Cache is browser-memory-only; a full reload drops it.

## Interview explanation

I measured SQL statements per request rather than guessing that React or seven records were inherently slow. Lazy ORM histories produced hundreds of round trips as fleet size grew. One latest-row fleet projection removed those round trips while retaining the existing business calculations. A persistent client query cache prevents navigation from throwing away loaded data, and SSE updates that cache with freshness and bounded reconnect logic. I verified SQL budgets, response behavior, tests, builds and disposable PostgreSQL, and explicitly separated local improvements from unmeasured cross-region production latency.
