import type { ActivityDraft, CustomerSystem, Run, Ticket } from "./types";

// The browser only talks to our backend; secrets stay on the backend.
const BASE = (import.meta.env.VITE_API_BASE as string) || "http://localhost:8000";

/** Convert unknown fetch or runtime errors into text the UI can show. */
export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected error";
}

/** Shared fetch helper so all API errors are handled the same way. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${body.slice(0, 200)}`);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

/** Small frontend wrapper around the backend technician workflow API. */
export const api = {
  listTickets: (sort = "date"): Promise<Ticket[]> =>
    request(`/api/tickets?sort=${encodeURIComponent(sort)}`),
  getTicket: (id: number): Promise<{ ticket: Ticket; system: CustomerSystem }> =>
    request(`/api/tickets/${id}`),
  startRun: (ticketId: number): Promise<Run> =>
    request(`/api/runs`, { method: "POST", body: JSON.stringify({ ticket_id: ticketId }) }),
  getRun: (id: string): Promise<Run> => request(`/api/runs/${id}`),
  approve: (id: string): Promise<Run> =>
    request(`/api/runs/${id}/approve`, { method: "POST", body: "{}" }),
  reject: (id: string): Promise<Run> =>
    request(`/api/runs/${id}/reject`, { method: "POST", body: "{}" }),
  abort: (id: string): Promise<Run> =>
    request(`/api/runs/${id}/abort`, { method: "POST", body: "{}" }),
  activityDraft: (id: string): Promise<ActivityDraft> =>
    request(`/api/runs/${id}/activity-draft`),
  submitActivity: (id: string, body: ActivityDraft & { set_done: boolean }): Promise<{ run: Run }> =>
    request(`/api/runs/${id}/submit-activity`, { method: "POST", body: JSON.stringify(body) }),
};
