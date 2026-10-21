"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ConnectionState, TelemetryContext } from "@/lib/useTelemetryStream";
import { connectTelemetry } from "@/lib/telemetry-connection";
import { applyTelemetry } from "@/lib/telemetry-cache";

export function TelemetryProvider({ children }: { children: React.ReactNode }) {
  const client = useQueryClient();
  const enabled = usePathname() !== "/login";
  const [connectionState, setConnectionState] = useState<ConnectionState>("OFFLINE");
  const [lastEventTime, setLastEventTime] = useState<Date | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let lastIntelligenceRefresh = 0;
    return connectTelemetry({
      onState: setConnectionState,
      onEvent: event => {
        setLastEventTime(new Date(event.timestamp));
        // Do not let an older in-flight REST snapshot overwrite this packet.
        void client.cancelQueries({ predicate: q => q.queryKey[0] === "api" &&
          String(q.queryKey[1]).startsWith("/equipment") && q.state.data !== undefined })
          .then(() => applyTelemetry(client, event));
        // Refresh derived alert counts occasionally, never once per fleet packet.
        if (Date.now() - lastIntelligenceRefresh > 30_000) {
          lastIntelligenceRefresh = Date.now();
          void client.invalidateQueries({ predicate: q => q.queryKey[0] === "api" &&
            /\/(dashboard|alerts|recommendations|anomalies)/.test(String(q.queryKey[1])) });
        }
      },
      refresh: () => client.refetchQueries({ type: "active", predicate: q => q.queryKey[0] === "api" &&
        !/^\/(sites|operators|chat|forecasts)/.test(String(q.queryKey[1])) }, { cancelRefetch: false, throwOnError: true }),
    });
  }, [client, enabled]);
  return <TelemetryContext.Provider value={{ connectionState: enabled ? connectionState : "OFFLINE", lastEventTime }}>
    {children}
  </TelemetryContext.Provider>;
}
