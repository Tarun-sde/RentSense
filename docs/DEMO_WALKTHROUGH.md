# RentSense interview walkthrough (3–5 minutes)

1. Open the dashboard. Explain that the KPIs are calculated from 20 related equipment, rental, telemetry and alert records—not hardcoded totals. Point out the status distribution and that the greeting uses the visitor's local time.

2. Open the fleet map. Show five geographically separated demo sites, select a site, center the fleet, hover a marker and open its asset. Explain that invalid coordinates are rejected and sites/bounds come from the API. The top-bar stream badge is authoritative: seeded readings are historical and should show STALE unless a fresh SSE telemetry event arrives.

3. Open `EQX1001`. Its accumulated idle time produces IDLE/low-utilization signals. Show telemetry history, the active anomalies and the recommendation to reassign it. Explain the rule inputs—engine hours, idle hours, rental assignment and due date—rather than calling the recommendation AI magic.

4. Open the Action Queue. Show the pending reassignment, missing-operator investigation and overdue return beside completed interventions. Explain that completing an action writes an audit event and can create a formula-based impact record.

5. Open Financial Impact and Forecasting. Show the completed INR savings calculations and the per-site weighted-moving-average forecasts with confidence/backtest information. Clarify that these are deterministic portfolio-demo analytics over seeded history, not claims from a live customer fleet.

Close by noting the boundary honestly: FastAPI/PostgreSQL APIs, status derivation, actions, SSE delivery, caching, maps and analytics are functional; the interview dataset and telemetry history are fictional. LIVE is shown only for genuinely fresh events.
