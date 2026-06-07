import type { Activity, ActivityDraft, AuditEntry, CustomerSystem, Me, MemoryNote, PlanStepEdit, Run, RunRecord, RunSummary, Stats, Ticket } from "./types";

export const BASE = (import.meta.env.VITE_API_BASE as string) || "http://localhost:8000";

export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected error";
}

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

// ---------------------------------------------------------------------------
// Mock data — used when VITE_MOCK_MODE=true or when backend is unreachable
// ---------------------------------------------------------------------------

const MOCK_TICKETS: Ticket[] = [
  {
    id: 7001,
    title: "Nginx not responding — web app down",
    description: "Customer reports the web application at https://app.acme-gmbh.at is returning a 502 Bad Gateway error since approximately 09:45 this morning. Nginx appears to have stopped. Customers cannot access the application.",
    priority: "high",
    status: "OPEN",
    customer_name: "Acme GmbH",
    created_at: "2026-06-06T09:52:00Z",
    tags: ["nginx", "web", "outage"],
  },
  {
    id: 7002,
    title: "Disk usage above 90% — risk of data loss",
    description: "Automated monitoring flagged /dev/sda1 at 91% capacity on the production database server. Log rotation may have failed. Immediate attention required to prevent service disruption.",
    priority: "high",
    status: "OPEN",
    customer_name: "Müller & Partner KG",
    created_at: "2026-06-06T08:10:00Z",
    tags: ["disk", "storage", "database"],
  },
  {
    id: 6998,
    title: "Scheduled backup job failing since Tuesday",
    description: "The nightly backup job has failed three times consecutively since 2026-06-03. Exit code 1, no further output. Backup destination is a mounted NFS share. Last successful backup was Monday 02:00.",
    priority: "medium",
    status: "PENDING",
    customer_name: "Hotel Bergblick GmbH",
    created_at: "2026-06-05T07:30:00Z",
    tags: ["backup", "cron", "nfs"],
  },
];

const MOCK_SYSTEM: CustomerSystem = {
  ticket_id: 7001,
  customer_id: 201,
  system: {
    ip: "10.42.17.83",
    port: 22,
    username: "azureuser",
    os: "Ubuntu 22.04 LTS",
    notes: "Azure VM — Standard_B2s. Nginx reverse proxy in front of Node.js app on :3000.",
  },
};

const MOCK_SYSTEMS: Record<number, CustomerSystem> = {
  7001: MOCK_SYSTEM,
  7002: {
    ticket_id: 7002,
    customer_id: 202,
    system: {
      ip: "10.11.4.56",
      port: 22,
      username: "dbadmin",
      os: "Debian 12 (Bookworm)",
      notes: "On-prem PostgreSQL 15 server. Managed by techbold since 2024.",
    },
  },
  6998: {
    ticket_id: 6998,
    customer_id: 203,
    system: {
      ip: "192.168.1.20",
      port: 22,
      username: "backup-user",
      os: "Ubuntu 20.04 LTS",
    },
  },
};

const MOCK_DELAY = (ms = 120) => new Promise((r) => setTimeout(r, ms));

const mockApi = {
  listTickets: async (): Promise<Ticket[]> => {
    await MOCK_DELAY();
    return MOCK_TICKETS;
  },
  getTicket: async (id: number): Promise<{ ticket: Ticket; system: CustomerSystem }> => {
    await MOCK_DELAY();
    const ticket = MOCK_TICKETS.find((t) => t.id === id);
    if (!ticket) throw new Error(`Ticket ${id} not found`);
    const system = MOCK_SYSTEMS[id] ?? { ...MOCK_SYSTEM, ticket_id: id };
    return { ticket, system };
  },
};

// ---------------------------------------------------------------------------
// Decide which API to use
//
// MOCK_MODE is an EXPLICIT opt-in (VITE_MOCK_MODE=true) for offline UI work. We
// do NOT silently fall back to mocks on a failed request — a real backend error
// must surface, not masquerade as a working demo.
// ---------------------------------------------------------------------------

const MOCK_MODE = import.meta.env.VITE_MOCK_MODE === "true";

export const api = {
  me: (): Promise<Me> =>
    MOCK_MODE ? Promise.resolve({ firstname: "Alex", lastname: "Berger", teamname: "Team Extrameile" })
              : request(`/api/me`),
  listTickets: (sort = "date"): Promise<Ticket[]> =>
    MOCK_MODE ? mockApi.listTickets() : request(`/api/tickets?sort=${encodeURIComponent(sort)}`),
  getTicket: (id: number): Promise<{ ticket: Ticket; system: CustomerSystem }> =>
    MOCK_MODE ? mockApi.getTicket(id) : request(`/api/tickets/${id}`),
  ticketActivities: (id: number): Promise<{ ticket_id: number; activities: Activity[] }> =>
    MOCK_MODE ? Promise.resolve({ ticket_id: id, activities: [] }) : request(`/api/tickets/${id}/activities`),
  ticketRuns: (id: number): Promise<{ ticket_id: number; runs: RunRecord[] }> =>
    MOCK_MODE ? Promise.resolve({ ticket_id: id, runs: [] }) : request(`/api/tickets/${id}/runs`),
  startRun: (ticketId: number): Promise<Run> =>
    request(`/api/runs`, { method: "POST", body: JSON.stringify({ ticket_id: ticketId }) }),
  listRuns: (): Promise<RunSummary[]> =>
    MOCK_MODE ? Promise.resolve([]) : request(`/api/runs`),
  stats: (): Promise<Stats> =>
    MOCK_MODE ? Promise.resolve({ total: 0, by_status: {}, active_sessions: 0 }) : request(`/api/stats`),
  memoryNotes: (): Promise<{ notes: MemoryNote[] }> =>
    MOCK_MODE ? Promise.resolve({ notes: [] }) : request(`/api/memory`),
  getRun: (id: string): Promise<Run> => request(`/api/runs/${id}`),
  approve: (id: string, steps?: PlanStepEdit[]): Promise<Run> =>
    request(`/api/runs/${id}/approve`, {
      method: "POST",
      body: JSON.stringify(steps && steps.length ? { steps } : {}),
    }),
  reject: (id: string, feedback?: string): Promise<Run> =>
    request(`/api/runs/${id}/reject`, {
      method: "POST",
      body: JSON.stringify(feedback && feedback.trim() ? { feedback: feedback.trim() } : {}),
    }),
  abort: (id: string): Promise<Run> =>
    request(`/api/runs/${id}/abort`, { method: "POST", body: "{}" }),
  activityDraft: (id: string): Promise<ActivityDraft> =>
    request(`/api/runs/${id}/activity-draft`),
  auditTrail: (id: string): Promise<{ run_id: string; entries: AuditEntry[] }> =>
    request(`/api/runs/${id}/audit`),
  submitActivity: (id: string, body: ActivityDraft & { set_done: boolean }): Promise<{ run: Run }> =>
    request(`/api/runs/${id}/submit-activity`, { method: "POST", body: JSON.stringify(body) }),
};
