"use client";
import { createContext, useContext } from "react";
export type ConnectionState = "LIVE" | "STALE" | "RECONNECTING" | "POLLING" | "OFFLINE";
export const TelemetryContext = createContext<{ connectionState: ConnectionState; lastEventTime: Date | null }>({
  connectionState: "OFFLINE", lastEventTime: null,
});
export const useTelemetryStream = () => useContext(TelemetryContext);
