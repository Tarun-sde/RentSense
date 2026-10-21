import type { QueryClient } from "@tanstack/react-query";
import type { DashboardKPIs, EquipmentDetail, EquipmentListItem, TelemetryStreamEvent } from "../types";

export function applyTelemetry(client: QueryClient, event: TelemetryStreamEvent) {
  const update = <T extends EquipmentListItem>(item: T): T => {
    if (item.id !== event.equipment_id || (item.latest_telemetry &&
      Date.parse(item.latest_telemetry.timestamp) >= Date.parse(event.timestamp))) return item;
    return { ...item, status: event.status, utilization_rate: event.utilization_rate,
      latest_telemetry: { ...event } };
  };
  client.setQueryData<EquipmentListItem[]>(["api", "/equipment"], old => old?.map(update));
  client.setQueryData<EquipmentDetail>(["api", `/equipment/${encodeURIComponent(event.equipment_id)}`], old => {
    if (!old) return old;
    const next = update(old);
    return next === old ? old : { ...next,
      recent_telemetry: [next.latest_telemetry!, ...old.recent_telemetry].slice(0, 20) };
  });
  const fleet = client.getQueryData<EquipmentListItem[]>(["api", "/equipment"]);
  if (!fleet) return;
  client.setQueryData<DashboardKPIs>(["api", "/dashboard"], old => {
    if (!old || old.total_equipment !== fleet.length) return old;
    const counts = { ACTIVE: 0, IDLE: 0, DUE_SOON: 0, OVERDUE: 0, UNASSIGNED: 0 };
    const rates: number[] = [];
    for (const item of fleet) {
      if (item.status in counts) counts[item.status as keyof typeof counts]++;
      if (item.latest_telemetry && item.latest_telemetry.engine_hours > 0) rates.push(item.utilization_rate);
    }
    return { ...old, active: counts.ACTIVE, idle: counts.IDLE, due_soon: counts.DUE_SOON,
      overdue: counts.OVERDUE, unassigned: counts.UNASSIGNED, status_counts: counts,
      fleet_utilization_pct: rates.length ? Math.round(rates.reduce((a, b) => a + b, 0) / rates.length * 1000) / 10 : 0 };
  });
}
