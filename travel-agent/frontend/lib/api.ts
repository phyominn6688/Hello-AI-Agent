import type { ChatMessage, ItineraryDay, SSEEvent, Trip } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function authHeaders(): Promise<HeadersInit> {
  // In dev (mock-auth), read token from localStorage
  // In prod, Amplify Auth.currentSession() returns the Cognito JWT
  if (typeof window === "undefined") return {};
  try {
    const { fetchAuthSession } = await import("aws-amplify/auth");
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    if (token) return { Authorization: `Bearer ${token}` };
  } catch {
    // Fall back to localStorage mock token (dev)
  }
  const mockToken = localStorage.getItem("mock_token") || "";
  return mockToken ? { Authorization: `Bearer ${mockToken}` } : {};
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
  });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return res.json();
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${path} → ${res.status}`);
  return res.json();
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

export const updateTrip = (id: number, body: Partial<Trip>) =>
  patch<Trip>(`/api/v1/trips/${id}`, body);

// ── Conversation ───────────────────────────────────────────────────────────────

export const getConversation = (tripId: number) =>
  get<{ messages: ChatMessage[] }>(`/api/v1/trips/${tripId}/conversation`);

// ── Chat (SSE streaming) ───────────────────────────────────────────────────────

export async function* streamChat(
  tripId: number,
  message: string
): AsyncGenerator<SSEEvent> {
  const headers = {
    "Content-Type": "application/json",
    ...(await authHeaders()),
  };

  const res = await fetch(`${API_URL}/api/v1/trips/${tripId}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    throw new Error(`Chat request failed: ${res.status}`);
  }

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
            // Skip malformed events
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
  get<import("@/types").Alert[]>(`/api/v1/trips/${tripId}/alerts`);

export const markAlertRead = (tripId: number, alertId: number) =>
  post(`/api/v1/trips/${tripId}/alerts/${alertId}/read`, {});
