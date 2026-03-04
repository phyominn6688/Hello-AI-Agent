import type { Alert, ItineraryDay, Message, SSEEvent, Trip } from "../types";
import { getAuthHeaders } from "./auth";

const API_URL = import.meta.env.VITE_API_URL ?? "";

async function authJson(): Promise<Record<string, string>> {
  return {
    "Content-Type": "application/json",
    ...(await getAuthHeaders()),
  };
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { headers: await authJson() });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: await authJson(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

// ── Trips ──────────────────────────────────────────────────────────────────────

export const listTrips = () => get<Trip[]>("/api/v1/trips");

export const createTrip = (body: {
  title: string;
  budget_per_person?: number;
  currency?: string;
  start_date?: string;
  end_date?: string;
}) => post<Trip>("/api/v1/trips", body);

export const getTrip = (id: number) => get<Trip>(`/api/v1/trips/${id}`);

// ── Conversation ───────────────────────────────────────────────────────────────

export const getConversation = (tripId: number) =>
  get<{ messages: Message[] }>(`/api/v1/trips/${tripId}/conversation`);

// ── Chat (SSE streaming) ───────────────────────────────────────────────────────

export async function* streamChat(
  tripId: number,
  message: string
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${API_URL}/api/v1/trips/${tripId}/chat`, {
    method: "POST",
    headers: await authJson(),
    body: JSON.stringify({ message }),
  });

  if (!res.ok) throw new Error(`Chat failed: ${res.status}`);

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const jsonStr = line.slice(6).trim();
        if (jsonStr) {
          try {
            yield JSON.parse(jsonStr) as SSEEvent;
          } catch {
            // skip malformed
          }
        }
      }
    }
  }
}

// ── Itinerary ──────────────────────────────────────────────────────────────────

export const getItinerary = (tripId: number) =>
  get<ItineraryDay[]>(`/api/v1/trips/${tripId}/itinerary`);

export const getAlerts = (tripId: number) =>
  get<Alert[]>(`/api/v1/trips/${tripId}/alerts`);

export const markAlertRead = (tripId: number, alertId: number) =>
  post(`/api/v1/trips/${tripId}/alerts/${alertId}/read`, {});
