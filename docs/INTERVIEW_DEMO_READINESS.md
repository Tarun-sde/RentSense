# Interview demo readiness

## Problems and root causes

The Azure frontend could be built without `NEXT_PUBLIC_MAPBOX_TOKEN`. Next.js replaces public environment values during `next build`, so setting the token only on the running Container App cannot repair an already-built bundle. The prior fleet map also announced Mapbox before its `load` event, hardcoded three site tabs and India-wide fallback bounds, retained filtered markers, inserted API strings with `innerHTML`, and used San Francisco coordinates when data was missing. The detail map defaulted to coordinates unrelated to the selected asset.

The missing build-time token is a code-confirmed failure mode, not a verified diagnosis of the deployed Azure image. No Azure revision, production browser network trace, or production token restrictions were inspected in this task. Check those before declaring the production root cause confirmed.

The hero greeting was always “Good Morning” and the UI/API defaults presented “Marcus Vance” as a logged-in person despite no trustworthy display-name field being exposed to these components. The old demo seed contained seven assets and an unsafe all-domain `--reset` command.

## Map implementation and configuration

Both maps now validate coordinates, prefer latest telemetry and then assigned-site coordinates, omit invalid points, clean up Mapbox instances/markers/timeouts, and report readiness only after Mapbox emits `load`. The fleet map derives sites and bounds from API data, removes filtered/deleted markers, updates status colors and coordinates, uses DOM `textContent` rather than interpolated popup HTML, and provides an honest stored-position fallback. The detail map no longer invents a location.

Mapbox GL CSS remains bundled from `globals.css`, standalone Next.js output is preserved, and the frontend Dockerfile exposes the build argument. Build with a public `pk.*` token from the operator's environment:

```bash
test -n "$NEXT_PUBLIC_MAPBOX_TOKEN"
docker build \
  --build-arg NEXT_PUBLIC_API_URL= \
  --build-arg NEXT_PUBLIC_MAPBOX_TOKEN="$NEXT_PUBLIC_MAPBOX_TOKEN" \
  --build-arg NEXT_PUBLIC_SIMULATOR_INTERVAL_SECONDS=60 \
  -t tarun1joshi/rentsense-frontend:v4 frontend
```

Do not commit `.env`, `.env.local`, or the token. Configure Mapbox URL restrictions for the exact production HTTPS frontend origin and, if needed, a separate local-development token. The token needs access to the Mapbox `dark-v11` style and fonts. In browser DevTools confirm WebGL is available and style/tile/font requests return 200; 401/403 generally indicates token scope or origin restrictions. Mapbox documents that restricted tokens require a compatible browser referrer and that localhost must be explicitly allowed: <https://docs.mapbox.com/accounts/guides/tokens/>.

## Browser-local greeting and identity

The server/client initial text is neutral `Welcome`, preventing hydration mismatch. After mount, the browser chooses:

- 05:00–11:59: Good Morning
- 12:00–16:59: Good Afternoon
- 17:00–20:59: Good Evening
- 21:00–04:59: Good Night

One timeout is scheduled for the next boundary and is recalculated on focus or visibility return. No date library was added. UI and backend defaults now use the neutral `Fleet Operator`; explicit actor names supplied by API clients remain untouched.

## Demo dataset

Normal seeding uses current UTC time; `ANCHOR_TIME` exists only for deterministic tests. The dataset contains 20 assets, 5 Indian demo sites, 10 explicitly fictional operators without personal contact details, 22 rentals, 120 telemetry readings, 15 alerts (11 open), 11 recommendations, 7 actions, 4 financial impact records, 240 forecasts, and 14 audit events. Open anomalies/recommendations use the existing rule engines. Completed actions use the existing savings formulas (INR 111,500 total). Forecast inputs are derived from overlapping historical rentals, not a hardcoded demand matrix; absent demand legitimately predicts zero.

At the injected reference time, status derivation produces 9 ACTIVE, 3 IDLE, 2 DUE_SOON, 2 OVERDUE, and 4 UNASSIGNED assets. Scenarios cover healthy/high utilization, excessive idle and low utilization, missing assignment, upcoming returns, short overdue periods, reassignment, completed interventions, realized INR impact, forecast history, and audit history. Coordinates follow assigned sites or fictional depot positions. Telemetry is seeded history: it does not claim that sensor events are currently streaming. LIVE/STALE/OFFLINE continues to depend on the real SSE event flow.

## Safe production refresh

Startup never refreshes or deletes data. Candidate IDs are `EQX1001`–`EQX1020`, `SITE-001`–`SITE-005`, `OP-001`–`OP-010`, and dependent rows, but IDs alone are NOT proof of ownership. New seeds store a content fingerprint in equipment metadata. Refresh requires that fingerprint to match every scoped record; new telemetry, operator edits, changed actions, or absent provenance block execution. Cross-namespace rental/action/impact references also block it. Authentication users, roles, password hashes, schema and migration history are preserved. PostgreSQL execution locks the domain tables with a five-second lock timeout, rechecks ownership, deletes and reseeds in one transaction; errors roll back.

**The legacy seven-asset production seed has no fingerprint and will be refused. Do not stamp it with a fingerprint or bypass the check.** First inspect an isolated Neon branch against the original seed and user activity. A reviewed, explicitly approved legacy migration is a separate prerequisite; alternatively prepare a new isolated demo database and approve a connection switch. Neither is performed here. The commands below can preview legacy production safely, but execution is supported only for an unchanged, provenance-marked new dataset. Even legitimate application activity can invalidate the fingerprint: stop and review rather than deleting those records.

Before touching Neon, record the active image/revision and create both an independent dump and a Neon branch. Neon describes branches as isolated copies of a parent database: <https://neon.com/docs/get-started-with-neon/workflow-primer>.

```bash
# Configure an approved libpq service and .pgpass locally (not in this repo).
# Load RENTSENSE_NEON_URL privately into the operator shell for the Python CLI.
backup="rentsense-before-demo-refresh-$(date -u +%Y%m%dT%H%M%SZ).dump"
PGSERVICE=rentsense-production pg_dump --format=custom --no-owner --no-acl --file="$backup"
pg_restore --list "$backup"

# Also create a child branch from the production branch in the Neon console.

cd backend
DATABASE_URL="$RENTSENSE_NEON_URL" venv/bin/python -m app.seed.seed --refresh-demo
```

Test restoring the dump into an isolated database. Review every dry-run count and require both `provenance_matches: True` and `safe_to_execute: True`. Never execute against the unmarked legacy seed. Only after backup verification and explicit approval, for a proven unchanged dataset:

```bash
cd backend
DATABASE_URL="$RENTSENSE_NEON_URL" venv/bin/python -m app.seed.seed \
  --refresh-demo --execute --confirm "REFRESH RENTSENSE DEMO DATA"
```

Run the dry-run again and API acceptance checks afterward. This task did not execute either production command. Repeating refresh on an unchanged marked dataset does not accumulate duplicates.

## Verification and performance

Focused coverage includes greeting boundaries/midnight, next-boundary scheduling, coordinate validation and fallback, dynamic site derivation/bounds, mocked Mapbox load/error/timeout, marker updates/removal and navigation cleanup, 20-asset counts/status distribution, relationship integrity, idempotency, dry-run behavior, unknown-record preservation, changed/unmarked provenance refusal, formula consistency, confirmation enforcement, and transactional rollback. Map mocks do not verify real geographic tiles or WebGL.

Final local verification (2026-10-23):

- `backend/venv/bin/python -m pytest backend/app/tests -q`: 157 passed; 17 dependency deprecation warnings.
- Frontend `npm run lint`, `npx tsc --noEmit`, `npm test`: passed (10 tests).
- Frontend `npm run build`: passed; existing Next middleware convention deprecation warning remains.
- Backend Docker build: passed, local `tarun1joshi/rentsense-backend:v3`.
- Frontend standalone Docker build: passed as `rentsense-frontend:readiness-test`, deliberately without a token to exercise the fallback build. Rebuild as the intended `v4` with the operator's valid token before release; do not deploy the tokenless test image as a map-ready release.
- Disposable PostgreSQL 16: migrations to head, seeding, provenance verification, atomic refresh, and injected failure after forecast writes with full rollback all passed. This did not connect to Neon.
- Container smoke checks: backend health and dashboard HTTP 200 with the expected 20-asset status distribution; standalone frontend login HTTP 200. Temporary smoke containers were removed afterward.
- `git diff --check`: passed.
- Browser automation had no enabled browser surface. Visual layout, real Mapbox style/tiles, URL restrictions, WebGL, and production proxy behavior are not verified.

The existing bounded fleet snapshot queries remain unchanged. Use the disposable benchmark before release:

```bash
backend/venv/bin/python backend/scripts/benchmark.py
```

Local SQLite/TestClient benchmark (five calls, concurrent build activity): equipment median 14.22 ms at 20 assets and 16.71 ms at 100 assets, exactly one SQL statement per request in both cases. Dashboard uses two statements. These local measurements are not comparable to the reported 0.54-second Azure network latency; they verify the bounded query path, not production speed.

Seeded telemetry stays stale until real ingestion or the separately feature-flagged simulator produces an event. The simulator remains disabled by default and was not enabled or deployed by this work.

## Build and deployment (not executed)

```bash
docker build -t tarun1joshi/rentsense-backend:v3 backend
docker push tarun1joshi/rentsense-backend:v3
docker push tarun1joshi/rentsense-frontend:v4

az containerapp update -g rg-rentsense -n rentsense-backend \
  --image tarun1joshi/rentsense-backend:v3 \
  --set-env-vars TELEMETRY_SIMULATOR_ENABLED=false
az containerapp update -g rg-rentsense -n rentsense-frontend \
  --image tarun1joshi/rentsense-frontend:v4

az containerapp revision list -g rg-rentsense -n rentsense-backend -o table
az containerapp revision list -g rg-rentsense -n rentsense-frontend -o table
```

The frontend token is baked into `v4`; setting `NEXT_PUBLIC_MAPBOX_TOKEN` only with `az containerapp update --set-env-vars` is insufficient.

## Rollback and remaining risks

```bash
az containerapp update -g rg-rentsense -n rentsense-backend --image tarun1joshi/rentsense-backend:v2 \
  --set-env-vars TELEMETRY_SIMULATOR_ENABLED=false
az containerapp update -g rg-rentsense -n rentsense-frontend --image tarun1joshi/rentsense-frontend:v3
```

If a data refresh must be reversed, point the applications at the pre-refresh Neon branch after reviewing credentials, or restore the verified dump into a separate database and switch only after validation. Do not restore over production blindly.

Real Mapbox tiles, Azure proxy behavior, production WebGL/browser combinations, Neon refresh, and Azure deployment remain operator acceptance steps. No valid token or production credential is stored in this repository.
