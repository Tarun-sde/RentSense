import type { TelemetryStreamEvent } from "../types";
import type { ConnectionState } from "./useTelemetryStream";

export const FRESHNESS_MS = 30_000;
export const POLL_MS = 30_000;

export function connectTelemetry(options: {
  onState: (state: ConnectionState) => void;
  onEvent: (event: TelemetryStreamEvent) => void;
  refresh: () => Promise<unknown>;
}) {
  let source: EventSource | undefined;
  let stopped = false;
  let connected = false;
  let lastTimestamp = 0;
  let failures = 0;
  let pollInFlight = false;
  let pollTimer: ReturnType<typeof setTimeout> | undefined;
  let handshakeTimer: ReturnType<typeof setTimeout> | undefined;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;

  const poll = async () => {
    pollTimer = undefined;
    if (stopped || connected || pollInFlight) return;
    if (!document.hidden) {
      pollInFlight = true;
      try {
        await options.refresh();
        if (!stopped && !connected) options.onState("POLLING");
      } catch {
        if (!stopped && !connected) options.onState("OFFLINE");
      } finally { pollInFlight = false; }
    }
    if (!stopped && !connected) pollTimer = setTimeout(poll, POLL_MS);
  };

  const connect = () => {
    if (stopped) return;
    options.onState("RECONNECTING");
    const fail = () => {
      if (stopped) return;
      clearTimeout(handshakeTimer);
      source?.close();
      connected = false;
      options.onState("RECONNECTING");
      if (!pollTimer && !pollInFlight) pollTimer = setTimeout(poll, POLL_MS);
      clearTimeout(retryTimer);
      retryTimer = setTimeout(connect, Math.min(60_000, 5_000 * 2 ** Math.min(failures++, 4)) + Math.random() * 1000);
    };
    try {
      source = new EventSource(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/telemetry/stream`, { withCredentials: true });
      handshakeTimer = setTimeout(fail, 20_000);
      source.onopen = () => {
        if (stopped) return;
        clearTimeout(handshakeTimer);
        connected = true;
        if (failures) void options.refresh().catch(() => {});
        clearTimeout(pollTimer);
        pollTimer = undefined;
        options.onState("STALE");
      };
      source.addEventListener("telemetry", (message: MessageEvent) => {
        if (stopped) return;
        try {
          const event = JSON.parse(message.data) as TelemetryStreamEvent;
          const timestamp = Date.parse(event.timestamp);
          if (!["ACTIVE", "IDLE", "DUE_SOON", "OVERDUE", "UNASSIGNED"].includes(event.status) || !event.equipment_id || !Number.isFinite(timestamp) || timestamp > Date.now() + 5000 ||
            ![event.engine_hours, event.idle_hours, event.fuel_pct, event.latitude, event.longitude, event.utilization_rate].every(Number.isFinite)) return;
          lastTimestamp = Math.max(lastTimestamp, timestamp);
          failures = 0;
          options.onState(Date.now() - lastTimestamp <= FRESHNESS_MS ? "LIVE" : "STALE");
          options.onEvent(event);
        } catch { /* Ignore malformed packets; the freshness timer still expires. */ }
      });
      source.onerror = fail;
    } catch { fail(); }
  };

  const freshnessTimer = setInterval(() => {
    if (connected && Date.now() - lastTimestamp > FRESHNESS_MS) options.onState("STALE");
  }, 5000);
  connect();
  return () => {
    stopped = true;
    source?.close();
    clearTimeout(pollTimer);
    clearTimeout(retryTimer);
    clearTimeout(handshakeTimer);
    clearInterval(freshnessTimer);
  };
}
