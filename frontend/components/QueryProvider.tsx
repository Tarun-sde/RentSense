"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { getQueryClient } from "@/lib/query-client";
import { TelemetryProvider } from "./TelemetryProvider";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={getQueryClient()}><TelemetryProvider>{children}</TelemetryProvider></QueryClientProvider>;
}
