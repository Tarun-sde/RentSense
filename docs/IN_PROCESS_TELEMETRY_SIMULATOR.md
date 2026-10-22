# In-process telemetry simulator

## Architecture and behavior

FastAPI starts one `telemetry-simulator` asyncio task from its lifespan and cancels it on shutdown. The task does no work by default. When enabled, it watches the existing SSE `ConnectionManager`; the first dashboard subscriber causes an immediate fleet tick, all subscribers share that tick, and production stops writing after the last subscriber plus the idle grace period. Synchronous SQLAlchemy work runs in Starlette's bounded thread pool, so Neon latency does not block the ASGI loop.

Each cycle uses the optimized fleet snapshot query to load equipment, current rental/site, and only the latest telemetry row. It then calls the existing telemetry persistence, anomaly evaluation, alert synchronization, status calculation, and SSE broadcast path. This preserves API/event schemas and alert deduplication. The seven original movement/behavior profiles were adapted from the removed standalone HTTP simulator; unknown assets use their current site (or last coordinates) and a conservative default profile. A cycle is capped at 100 assets by default.

Counters advance from the latest stored reading by elapsed active simulation time: engine hours never advance faster than wall time, idle hours cannot exceed engine hours, fuel is clamped to 0–100, coordinates remain inside each profile radius, and timestamps are UTC. Paused time is not backfilled when a viewer returns.

## Lifecycle, ownership, and failure recovery

`backend/main.py` owns startup and shutdown. Repeated starts in one process are idempotent. PostgreSQL uses a session-level advisory lock, so only one worker or replica can own the simulator; loss of that ownership connection stops the loop safely. SQLite only has process-local protection and is for local/tests, not multi-worker simulation. Keep the supported Azure deployment at one Uvicorn worker and one backend replica: SSE fanout is also process-local. The advisory lock is a safety net, not a distributed SSE architecture.

A failed database cycle is rolled back, logged once at cycle level, and retried with bounded exponential backoff. Sessions are short-lived. Empty fleets yield zero inserts and recover on a later cycle. Removed equipment disappears from the next snapshot. The simulator never controls rental dates or financial records and performs no deletes.

Viewer detection is reliable only when the browser's EventSource reaches `/api/v1/telemetry/stream`. The existing frontend uses one provider-level connection, the Next.js rewrite targets that endpoint, and Nginx disables buffering. Azure proxy streaming was not tested locally. Safe failure behavior is intentional: if SSE cannot connect, the frontend uses bounded polling and reports STALE/OFFLINE, while the simulator remains idle instead of generating unseen writes.

## Configuration

| Variable | Default | Meaning |
| --- | ---: | --- |
| `TELEMETRY_SIMULATOR_ENABLED` | `false` | Opt in to simulation. |
| `SIMULATOR_INTERVAL_SECONDS` | `60` | Seconds between fleet ticks; values are constrained to 10–3600. |
| `SIMULATOR_ACTIVE_VIEWERS_ONLY` | `true` | Require at least one SSE viewer, with grace. |
| `SIMULATOR_IDLE_GRACE_SECONDS` | `60` | Avoid churn during brief navigation/reconnects. |
| `SIMULATOR_MAX_EQUIPMENT_PER_CYCLE` | `100` | Hard write bound per tick. |
| `NEXT_PUBLIC_SIMULATOR_INTERVAL_SECONDS` | `60` | Frontend build-time freshness contract. Must match the backend interval. |

Frontend freshness is 2.5 expected intervals (150 seconds at the default), with a 30-second floor. Opening an SSE connection alone is STALE; only a valid, recent telemetry event changes it to LIVE.

## Write volume, retention, and cost

For seven assets at 60 seconds, each active tick inserts seven telemetry rows. One continuous hour is about 420 rows (plus the immediate opening tick), eight active hours/day is about 100,800 rows/month, and continuous 24/7 use is 10,080/day or 302,400 rows per 30 days. Zero viewers after grace produces zero rows; multiple viewers do not multiply writes. A disconnect can add at most the ticks falling inside its configured grace window.

Synthetic and real telemetry are not marked separately in the current schema. Consequently this change never purges data and no automatic retention job was added. Monitor table growth and establish an explicitly approved, provenance-aware retention policy before deleting anything. Sharing the backend avoids another container, but CPU-active time and Neon operations can still affect charges.

## Files changed

- `backend/app/services/telemetry_simulator.py`: ownership, scheduling, generation, persistence, and recovery.
- `backend/main.py`, config, connection manager, and telemetry API: lifecycle, validated flags, viewer wakeups, shared persistence.
- frontend telemetry connection and Dockerfile: interval-aligned freshness contract.
- Compose and `.env.example`: in-process flags; standalone simulator service removed.
- focused backend/frontend tests and this runbook.

## Deployment (do not run from this change)

Record the current revision/image and preserve all existing secret references first:

```bash
docker build -t tarun1joshi/rentsense-backend:v3 backend
docker push tarun1joshi/rentsense-backend:v3

# Frontend changed only for freshness timing; keep its existing v3 available for rollback.
docker build --build-arg NEXT_PUBLIC_API_URL= \
  --build-arg NEXT_PUBLIC_SIMULATOR_INTERVAL_SECONDS=60 \
  --build-arg NEXT_PUBLIC_MAPBOX_TOKEN="$NEXT_PUBLIC_MAPBOX_TOKEN" \
  -t tarun1joshi/rentsense-frontend:v4 frontend
docker push tarun1joshi/rentsense-frontend:v4

az containerapp update --resource-group rg-rentsense --name rentsense-backend \
  --image tarun1joshi/rentsense-backend:v3 \
  --set-env-vars TELEMETRY_SIMULATOR_ENABLED=true SIMULATOR_INTERVAL_SECONDS=60 \
    SIMULATOR_ACTIVE_VIEWERS_ONLY=true SIMULATOR_IDLE_GRACE_SECONDS=60
az containerapp update --resource-group rg-rentsense --name rentsense-frontend \
  --image tarun1joshi/rentsense-frontend:v4

az containerapp show --resource-group rg-rentsense --name rentsense-backend \
  --query '{fqdn:properties.configuration.ingress.fqdn,image:properties.template.containers[0].image,replicas:properties.template.scale}'
curl -fsS "https://$(az containerapp show -g rg-rentsense -n rentsense-backend --query properties.configuration.ingress.fqdn -o tsv)/health"
curl -fsS "https://$(az containerapp show -g rg-rentsense -n rentsense-backend --query properties.configuration.ingress.fqdn -o tsv)/ready"
```

Open the public frontend and inspect one `telemetry` EventSource. Confirm a fresh packet arrives promptly, all seven assets update once per minute, a second browser does not double database inserts, and LIVE becomes STALE after packets genuinely stop. Measure five warm requests without and with an active viewer:

```bash
BACKEND_URL="https://$(az containerapp show -g rg-rentsense -n rentsense-backend --query properties.configuration.ingress.fqdn -o tsv)"
for i in 1 2 3 4 5; do curl -sS -o /dev/null -w '%{time_total}\n' "$BACKEND_URL/api/v1/equipment"; done
az containerapp logs show -g rg-rentsense -n rentsense-backend --follow
```

## Immediate disable and rollback

Disabling is non-destructive and requires no schema rollback:

```bash
az containerapp update -g rg-rentsense -n rentsense-backend \
  --set-env-vars TELEMETRY_SIMULATOR_ENABLED=false
```

Return to the supplied known-good images if needed, preserving production environment variables and secret references:

```bash
az containerapp update -g rg-rentsense -n rentsense-backend --image tarun1joshi/rentsense-backend:v2 \
  --set-env-vars TELEMETRY_SIMULATOR_ENABLED=false
az containerapp update -g rg-rentsense -n rentsense-frontend --image tarun1joshi/rentsense-frontend:v3
```

No migration was added. Do not reseed or purge Neon during deployment or rollback.

## Verification and remaining limits

Measured locally on disposable SQLite (not Neon): a seven-asset cycle took 15.10 ms on its first run and 7.39 ms on its second. Each used one transaction, eight SELECTs, seven INSERTs, and no DELETEs; alert state caused four then three UPDATEs. With no SSE viewer, an enabled simulator performed no cycles. Twenty warm `/api/v1/equipment` reads measured 3.97 ms median disabled versus 4.20 ms enabled-but-idle; this is not a production latency claim. The broader disposable benchmark measured the seven-asset equipment endpoint at 5.17 ms median with one SQL query and the 100-asset endpoint at 6.73 ms with one query.

Verification completed: 148 backend tests; frontend lint, TypeScript, five runtime tests, and a 13-route production build. Both Docker images built; container smoke tests returned backend health, seven seeded assets, and a live frontend response. Azure-proxied SSE, Azure/Neon billing, sustained production memory/CPU, and public production latency require post-deployment measurement. The local loop counters (`cycles`, `inserted_records`) support tests/log correlation but are intentionally not exposed through a public control endpoint.
