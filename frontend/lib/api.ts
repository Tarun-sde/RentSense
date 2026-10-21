import { invalidateOperationalData, getQueryClient, apiQuery } from "./query-client";
import {
  DashboardKPIs,
  EquipmentListItem,
  EquipmentDetail,
  CheckoutPayload,
  CheckoutResponse,
  CheckinPayload,
  CheckinResponse,
  Site,
  Operator,
} from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

export async function fetchDashboardKPIs(): Promise<DashboardKPIs> {
  return getQueryClient().fetchQuery(apiQuery<DashboardKPIs>(`/dashboard`));
}

export async function fetchEquipmentList(params?: {
  search?: string;
  status?: string;
  site_id?: string;
  type?: string;
}): Promise<EquipmentListItem[]> {
  const query = new URLSearchParams();
  if (params?.search) query.append("search", params.search);
  if (params?.status) query.append("status", params.status);
  if (params?.site_id) query.append("site_id", params.site_id);
  if (params?.type) query.append("type", params.type);

  const url = `/equipment${query.toString() ? `?${query.toString()}` : ""}`;
  return getQueryClient().fetchQuery(apiQuery<EquipmentListItem[]>(url));
}

export async function fetchEquipmentDetail(id: string): Promise<EquipmentDetail> {
  return getQueryClient().fetchQuery(apiQuery<EquipmentDetail>(`/equipment/${encodeURIComponent(id)}`));
}

export async function fetchSites(): Promise<Site[]> {
  return getQueryClient().fetchQuery(apiQuery<Site[]>(`/sites`));
}

export async function fetchOperators(): Promise<Operator[]> {
  return getQueryClient().fetchQuery(apiQuery<Operator[]>(`/operators`));
}

export async function checkoutEquipment(payload: CheckoutPayload): Promise<CheckoutResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/rentals/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Checkout failed: ${res.status} ${res.statusText}`);
  }
  await invalidateOperationalData();
  return res.json();
}

export async function checkinEquipment(payload: CheckinPayload): Promise<CheckinResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/rentals/checkin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Check-in failed: ${res.status} ${res.statusText}`);
  }
  await invalidateOperationalData();
  return res.json();
}

export async function fetchAlerts(params?: {
  severity?: string;
  status?: string;
  equipment_id?: string;
  type?: string;
}): Promise<import("@/types").Alert[]> {
  const query = new URLSearchParams();
  if (params?.severity) query.append("severity", params.severity);
  if (params?.status) query.append("status", params.status);
  if (params?.equipment_id) query.append("equipment_id", params.equipment_id);
  if (params?.type) query.append("type", params.type);

  const url = `/alerts${query.toString() ? `?${query.toString()}` : ""}`;
  return getQueryClient().fetchQuery(apiQuery<import("@/types").Alert[]>(url));
}

export async function fetchAnomalies(params?: {
  equipment_id?: string;
  severity?: string;
  type?: string;
}): Promise<import("@/types").Anomaly[]> {
  const query = new URLSearchParams();
  if (params?.equipment_id) query.append("equipment_id", params.equipment_id);
  if (params?.severity) query.append("severity", params.severity);
  if (params?.type) query.append("type", params.type);

  const url = `/anomalies${query.toString() ? `?${query.toString()}` : ""}`;
  return getQueryClient().fetchQuery(apiQuery<import("@/types").Anomaly[]>(url));
}

export async function fetchEquipmentAnomalies(id: string): Promise<import("@/types").Anomaly[]> {
  return getQueryClient().fetchQuery(apiQuery<import("@/types").Anomaly[]>(`/equipment/${encodeURIComponent(id)}/anomalies`));
}

export async function fetchForecasts(params?: {
  site_id?: string;
  equipment_type?: string;
  horizon_weeks?: number;
}): Promise<import("@/types").Forecast[]> {
  const query = new URLSearchParams();
  if (params?.site_id) query.append("site_id", params.site_id);
  if (params?.equipment_type) query.append("equipment_type", params.equipment_type);
  if (params?.horizon_weeks) query.append("horizon_weeks", params.horizon_weeks.toString());

  const url = `/forecasts${query.toString() ? `?${query.toString()}` : ""}`;
  return getQueryClient().fetchQuery(apiQuery<import("@/types").Forecast[]>(url));
}

export async function fetchForecastSummary(params?: {
  site_id?: string;
  horizon_weeks?: number;
}): Promise<import("@/types").ForecastSummary> {
  const query = new URLSearchParams();
  if (params?.site_id) query.append("site_id", params.site_id);
  if (params?.horizon_weeks) query.append("horizon_weeks", params.horizon_weeks.toString());

  const url = `/forecasts/summary${query.toString() ? `?${query.toString()}` : ""}`;
  return getQueryClient().fetchQuery(apiQuery<import("@/types").ForecastSummary>(url));
}

export async function fetchRecommendations(params?: {
  equipment_id?: string;
  priority?: string;
  status?: string;
  recommendation_type?: string;
}): Promise<import("@/types").Recommendation[]> {
  const query = new URLSearchParams();
  if (params?.equipment_id) query.append("equipment_id", params.equipment_id);
  if (params?.priority) query.append("priority", params.priority);
  if (params?.status) query.append("status", params.status);
  if (params?.recommendation_type) query.append("recommendation_type", params.recommendation_type);

  const url = `/recommendations${query.toString() ? `?${query.toString()}` : ""}`;
  return getQueryClient().fetchQuery(apiQuery<import("@/types").Recommendation[]>(url));
}

export async function fetchEquipmentRecommendations(id: string): Promise<import("@/types").Recommendation[]> {
  return getQueryClient().fetchQuery(apiQuery<import("@/types").Recommendation[]>(`/recommendations/equipment/${encodeURIComponent(id)}`));
}

export async function triggerActionFromRecommendation(
  recId: number,
  data?: {
    action_type?: string;
    notes?: string;
    actor?: string;
    payload?: Record<string, unknown>;
  }
): Promise<import("@/types").Action> {
  const res = await fetch(`${API_BASE_URL}/api/v1/recommendations/${recId}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data || {}),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to trigger action: ${res.status}`);
  }
  await invalidateOperationalData();
  return res.json();
}

export async function fetchActions(params?: {
  status?: string;
  equipment_id?: string;
  action_type?: string;
  priority?: string;
}): Promise<import("@/types").Action[]> {
  const query = new URLSearchParams();
  if (params?.status) query.append("status", params.status);
  if (params?.equipment_id) query.append("equipment_id", params.equipment_id);
  if (params?.action_type) query.append("action_type", params.action_type);
  if (params?.priority) query.append("priority", params.priority);

  const url = `/actions${query.toString() ? `?${query.toString()}` : ""}`;
  return getQueryClient().fetchQuery(apiQuery<import("@/types").Action[]>(url));
}

export async function fetchActionDetail(id: number): Promise<import("@/types").Action> {
  return getQueryClient().fetchQuery(apiQuery<import("@/types").Action>(`/actions/${id}`));
}

export async function createAction(data: {
  equipment_id: string;
  action_type: string;
  recommendation_id?: number;
  alert_id?: number;
  priority?: string;
  notes?: string;
  actor?: string;
  payload?: Record<string, unknown>;
}): Promise<import("@/types").Action> {
  const res = await fetch(`${API_BASE_URL}/api/v1/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create action: ${res.status}`);
  }
  await invalidateOperationalData();
  return res.json();
}

export async function completeAction(
  id: number,
  data?: {
    notes?: string;
    actor?: string;
    payload?: Record<string, unknown>;
  }
): Promise<import("@/types").Action> {
  const res = await fetch(`${API_BASE_URL}/api/v1/actions/${id}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data || {}),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to complete action: ${res.status}`);
  }
  await invalidateOperationalData();
  return res.json();
}

export async function cancelAction(
  id: number,
  data?: {
    reason?: string;
    actor?: string;
  }
): Promise<import("@/types").Action> {
  const res = await fetch(`${API_BASE_URL}/api/v1/actions/${id}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data || {}),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to cancel action: ${res.status}`);
  }
  await invalidateOperationalData();
  return res.json();
}

export async function resolveAlert(
  id: number,
  data?: {
    resolution_notes?: string;
    actor?: string;
  }
): Promise<import("@/types").Alert> {
  const res = await fetch(`${API_BASE_URL}/api/v1/alerts/${id}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data || {}),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to resolve alert: ${res.status}`);
  }
  await invalidateOperationalData();
  return res.json();
}

export async function fetchImpactSummary(params?: { site_id?: string }): Promise<import("@/types").ImpactSummary> {
  const query = new URLSearchParams();
  if (params?.site_id) query.append("site_id", params.site_id);

  const url = `/impact${query.toString() ? `?${query.toString()}` : ""}`;
  return getQueryClient().fetchQuery(apiQuery<import("@/types").ImpactSummary>(url));
}

export async function fetchActionImpactDetail(actionId: number): Promise<import("@/types").ImpactDetail> {
  return getQueryClient().fetchQuery(apiQuery<import("@/types").ImpactDetail>(`/actions/${actionId}/impact`));
}

export async function createEquipment(payload: {
  id: string;
  type: string;
  dealer: string;
  daily_rate: number;
  model?: string;
  serial?: string;
}): Promise<import("@/types").EquipmentDetail> {
  const res = await fetch(`${API_BASE_URL}/api/v1/equipment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || `Failed to create equipment: ${res.status}`);
  }
  await invalidateOperationalData();
  return res.json();
}

export interface ChatMessageHistoryItem {
  role: "user" | "assistant" | "model";
  content: string;
}

export interface ChatResponse {
  reply: string;
  is_configured: boolean;
  grounded: boolean;
  model?: string;
  timestamp: string;
}

export async function sendChatMessage(
  message: string,
  history?: ChatMessageHistoryItem[]
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || `Chat request failed: ${res.status}`);
  }
  return res.json();
}

export async function streamChatMessage(
  message: string,
  history: ChatMessageHistoryItem[] | undefined,
  callbacks: {
    onChunk: (text: string) => void;
    onStage?: (stageText: string) => void;
    onDone: (meta: { is_configured: boolean; grounded: boolean; model?: string }) => void;
    onError: (errMessage: string) => void;
  }
): Promise<void> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      callbacks.onError(err.detail || err.message || `Streaming request failed: ${res.status}`);
      return;
    }

    if (!res.body) {
      callbacks.onError("No streaming response body received.");
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("data: ")) {
          try {
            const data = JSON.parse(trimmed.slice(6));
            if (data.type === "stage" && callbacks.onStage) {
              callbacks.onStage(data.text);
            } else if (data.type === "chunk") {
              callbacks.onChunk(data.text);
            } else if (data.type === "done") {
              callbacks.onDone({
                is_configured: data.is_configured ?? true,
                grounded: data.grounded ?? true,
                model: data.model,
              });
            } else if (data.type === "error") {
              callbacks.onError(data.reply || "Gemini service encountered an issue.");
            }
          } catch {
            // Ignore unparsed stream chunks
          }
        }
      }
    }
  } catch (err: unknown) {
    const errMsg = err instanceof Error ? err.message : "Failed to connect to streaming chat.";
    callbacks.onError(errMsg);
  }
}

export async function fetchChatStatus(): Promise<{ is_configured: boolean; model: string }> {
  return getQueryClient().fetchQuery(apiQuery<{ is_configured: boolean; model: string }>(`/chat/status`));
}
