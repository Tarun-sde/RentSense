# RentSense Control Tower

> **Real-Time Heavy Equipment Telemetry, Deterministic Anomaly Detection, Demand Forecasting, and Automated ROI / Cost Avoidance Tracking.**

---

## 1. Project Overview & Business Story

In heavy civil and commercial construction, equipment rental waste drains up to 30% of project margins due to **untracked idle standby time**, **overdue contract penalty surcharges**, and **unassigned idle assets**.

**RentSense Control Tower** closes the operational intelligence loop:

$$\text{DETECT} \longrightarrow \text{EXPLAIN} \longrightarrow \text{RECOMMEND} \longrightarrow \text{ACT} \longrightarrow \text{MEASURE IMPACT}$$

1. **Ingests Live Telemetry**: Engine runtime, idle hours, fuel percentage, and GPS positioning streamed in real time via Server-Sent Events (SSE).
2. **Detects Operational Anomalies**: Evaluates compound mathematical signals (excessive idle $>8\text{h}$, low utilization $<20\%$, zero runtime, overdue contracts).
3. **Explains in Plain Language**: Generates deterministic, human-readable diagnostics explaining *why* an alert fired with exact numeric evidence.
4. **Recommends Optimal Interventions**: Ranks high-priority actions (`RETURN`, `REASSIGN`, `EXTEND`, `INVESTIGATE`) with estimated cost savings.
5. **Enables 1-Click Operational Action**: Operators execute transfers or handoffs directly in the **Action Queue**, transitioning rental states and auto-resolving alerts.
6. **Measures Realized Financial ROI**: Records auditable, deterministic cash savings strictly upon action completion in the **Avoided Impact Ledger**.

---

## 2. System Architecture

```
                                  ┌────────────────────────┐
                                  │   Heavy Fleet Sensors  │
                                  │   (Simulator / GPS)    │
                                  └───────────┬────────────┘
                                              │ POST /api/v1/telemetry
                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             RentSense FastAPI Backend                            │
│                                                                                  │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐ │
│  │   Telemetry Ingest    │  │   Anomaly Engine      │  │   Demand Forecasting  │ │
│  │   & SSE Broadcast     │  │   (Deterministic)     │  │   (3-Week WMA + MAE)  │ │
│  └───────────┬───────────┘  └───────────┬───────────┘  └───────────┬───────────┘ │
│              │                          │                          │             │
│              ▼                          ▼                          ▼             │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐ │
│  │   Action Lifecycle    │  │   Financial Impact    │  │   Structured Audit    │ │
│  │   & Alert Resolution  │  │   Engine (Realized)   │  │   Event Trail         │ │
│  └───────────────────────┘  └───────────────────────┘  └───────────────────────┘ │
└─────────────────────────────┬────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌───────────────────────────────────────────┐
        │  SQLite (Dev) / PostgreSQL (Prod) Engine  │
        └───────────────────────────────────────────┘
                              ▲
                              │ SSE Live Stream + REST API
                              ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                       RentSense Next.js Control Tower UI                         │
│                                                                                  │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ │
│  │ Fleet Dashboard │ │ Tactical Map    │ │ Action Queue    │ │ Avoided Impact  │ │
│  │ & KPIs (Live)   │ │ & GPS Polling   │ │ & Modal Actions │ │ Ledger & ROI    │ │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Technology Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, Alembic, Pydantic v2, Uvicorn, SSE (Server-Sent Events).
- **Frontend**: Next.js 15+ (App Router, Turbopack), React 19, TypeScript, Vanilla CSS + Tailwind tokens, Recharts, Lucide Icons.
- **Database**: SQLite (local development), PostgreSQL 16 (production).
- **Orchestration**: Docker, Docker Compose, Nginx (unbuffered SSE reverse proxy).
- **Design System**: *Operational Elegance* (Warm canvas `#fbf9f4`, radial depth, Playfair Display headers, Inter UI, `#ff5a24` signal color, glassmorphism cards).

---

## 4. Local Setup & Installation

### Prerequisites
- Python 3.11 or higher
- Node.js 20+ and npm
- Git

### Backend Setup
```bash
cd backend
python -m venv venv

# Windows activate:
.\venv\Scripts\activate

# Linux/macOS activate:
source venv/bin/activate

pip install -r requirements.txt
```

### Frontend Setup
```bash
cd ../frontend
npm install
```

---

## 5. Environment Variables

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

| Variable | Description | Default |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Runtime mode (`development`, `production`) | `development` |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./rentsense.db` |
| `FRONTEND_URL` | URL of the frontend for CORS whitelisting | `http://localhost:3000` |
| `CORS_ORIGINS` | Comma-separated CORS allowed origins | `http://localhost:3000,http://127.0.0.1:3000` |
| `NEXT_PUBLIC_API_URL` | Base API URL for Next.js client | `http://localhost:8000` |
| `TELEMETRY_SIMULATOR_ENABLED` | Enable the in-process demo simulator | `false` |
| `SIMULATOR_INTERVAL_SECONDS` | Active-viewer telemetry interval (10–3600 seconds) | `60` |
| `SIMULATOR_ACTIVE_VIEWERS_ONLY` | Suspend writes without SSE viewers | `true` |
| `SIMULATOR_IDLE_GRACE_SECONDS` | Continue briefly after the last viewer leaves | `60` |
| `ALERT_DUE_SOON_HOURS` | Lead hours for due soon notification | `48` |
| `IDLE_HOURS_THRESHOLD` | Max acceptable idle runtime before anomaly | `8.0` |
| `LOW_UTILIZATION_THRESHOLD` | Minimum acceptable utilization fraction | `0.20` |

---

## 6. Database Migrations & Seeding

### Apply Alembic Migrations
```bash
cd backend
.\venv\Scripts\alembic upgrade head
```

### Seed Initial Data

Seeding now only initializes an empty database and uses dates relative to today. Existing data is preserved. Docker startup does not seed unless you explicitly set `SEED_DEMO_DATA=true` for a fresh demo database; set it back to `false` afterward. Never use the seeder’s `--reset` option against Neon or data you want to keep. Configure `ADMIN_PASSWORD` rather than relying on a default login.

Production HTTPS cookies default to Secure; local HTTP Compose defaults `AUTH_COOKIE_SECURE=false`. Keep it `true` on Azure. See [performance results, verification and deployment instructions](docs/PERFORMANCE_OPTIMIZATION_REPORT.md).
The old standalone simulator container has been replaced by the backend lifespan task; see [the simulator runbook](docs/IN_PROCESS_TELEMETRY_SIMULATOR.md).

Populates 7 representative heavy assets, 3 jobsites, 4 certified operators, active rentals, historical telemetry, and baseline forecasts:
```bash
.\venv\Scripts\python.exe app/seed/seed.py
```

---

## 7. Running the Application

### 1. Start FastAPI Backend
```bash
cd backend
.\venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8000 --reload
```
- API Health: `http://127.0.0.1:8000/health`
- Readiness Probe: `http://127.0.0.1:8000/ready`
- Interactive OpenAPI Docs: `http://127.0.0.1:8000/docs`

### 2. Start Next.js Frontend
```bash
cd frontend
npm run dev
```
- Open Control Tower: `http://localhost:3000`

### 3. Start Telemetry Simulator (Optional)
```bash
cd simulator
python main.py
```

---

## 8. Automated Testing & Verification

### Run Full Backend Pytest Suite (142 Tests)
```bash
cd backend
.\venv\Scripts\python.exe -m pytest
```

### Run Frontend Static Analysis & Production Build
```bash
cd frontend
npm run lint
npm run build
```

---

## 9. Docker & Container Deployment

### Run Full Stack with Docker Compose
```bash
docker compose up --build -d
```

### Services Started:
1. `rentsense-db`: PostgreSQL 16 on port `5432` with persistent volume `pgdata`.
2. `rentsense-backend`: FastAPI on port `8000` with HTTP healthcheck (`/health`).
3. `rentsense-frontend`: Next.js production server on port `3000`.
4. `rentsense-nginx`: Nginx reverse proxy on port `80` with unbuffered SSE streaming.

### Run with Telemetry Simulator Profile:
```bash
docker compose --profile simulation up --build -d
```

---

## 10. Production Nginx Reverse Proxy Architecture

For bare-metal or cloud VM deployments, `nginx/nginx.conf` routes traffic securely:
- `/api/` $\longrightarrow$ `backend:8000`
- `/api/v1/telemetry/stream` $\longrightarrow$ `backend:8000` with `X-Accel-Buffering: no;` and `proxy_buffering off;` (enables realtime unbuffered SSE streaming).
- `/` $\longrightarrow$ `frontend:3000`

---

## 11. Complete Demo Workflow

1. **Fleet Surveillance**: Observe 7 live assets on the Dashboard tactical map with dynamic status pills (`ACTIVE`, `IDLE`, `OVERDUE`, `DUE_SOON`, `UNASSIGNED`).
2. **Anomaly Trigger**: `EQX1001` (CAT 320 Excavator) records 14.2h idle out of 16.0h runtime (11.2% utilization).
3. **Explainable Diagnostic**: AI Insight card explains: *"Asset EQX1001 has accumulated 14.2h idle engine time, exceeding the 8.0h threshold."*
4. **Recommendation**: Suggests `REASSIGN` to *Highland Medical Center* with **+$810.00** estimated cost avoidance.
5. **Operator Action**: Click **Execute Action** $\longrightarrow$ Opens the **Action Queue** (`/actions`) $\longrightarrow$ Click **Complete Action** with destination *Highland Medical Center*.
6. **State Transition & Alert Resolution**: Rental site updates, open alerts auto-resolve, and an audit event is logged.
7. **Verified ROI**: Navigate to **Avoided Impact** (`/impact`) to view **+$1,350.00** in verified realized savings and inspect the deterministic calculation ledger.

---

## 12. Security & Production Hardening Summary

- **Environment Centralization**: All secrets, database URLs, and thresholds loaded via Pydantic `BaseSettings`.
- **CORS Whitelisting**: Strict origin validation preventing wildcard access with credentials.
- **Server-Side Financial Security**: Realized savings are calculated exclusively by the backend upon action completion; client cannot spoof savings amounts.
- **Bounded Pagination**: All query endpoints enforce `ge=1, le=500` limits.
- **Sanitized Error Responses**: Internal stack traces and database credentials are never leaked to HTTP clients.
- **Alembic Versioning**: Reproducible schema migrations tracking all 10 relational tables.

---

## 13. Known Limitations & Roadmap

- **Authentication**: Phase 0–6 scoped single-operator / commander mode (`AUTH_ENABLED=false`). Production RBAC role flags are present in config for future SSO/OAuth2 expansion.
- **Multi-Tenant Partitioning**: Designed for single enterprise fleet operations.

---

*RentSense Control Tower — Engineered for operational clarity and deterministic financial impact.*
