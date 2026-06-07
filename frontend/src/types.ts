export type TicketStatus = "OPEN" | "PENDING" | "DONE";
export type Risk = "SAFE" | "GATED" | "BLOCKED" | null;

export type RunStatus =
  | "created"
  | "analyzing"
  | "awaiting_plan_approval"
  | "executing"
  | "verifying"
  | "finished"
  | "escalated"
  | "aborted";

export type StepStatus =
  | "proposed"
  | "executed"
  | "failed"
  | "blocked"
  | "rejected"
  | "done";

export interface Ticket {
  id: number;
  title: string;
  description: string;
  priority: string;
  status: TicketStatus;
  customer_name: string;
  created_at?: string | null;
  tags?: string[];
}

export interface SystemInfo {
  ip: string;
  port: number;
  username: string;
  os: string;
  notes?: string;
}

export interface CustomerSystem {
  ticket_id: number;
  customer_id: number;
  system: SystemInfo;
}

export interface StepResult {
  stdout: string;
  stderr: string;
  exit_code: number | null;
  duration_ms: number | null;
}

export interface Step {
  index: number;
  kind: string;
  command: string;
  rationale: string;
  risk: Risk;
  expected: string;
  status: StepStatus;
  result: StepResult | null;
  safety_reason: string;
}

export interface PlanStep {
  command: string;
  rationale?: string;
  expected?: string;
  risk?: string;
}

// What the technician sends when approving (optionally edited) — matches the
// backend ApproveIn.steps / PlanStepIn shape.
export interface PlanStepEdit {
  command: string;
  rationale?: string;
  expected?: string;
}

export interface Plan {
  root_cause: string;
  steps: PlanStep[];
  validation: string[];
}

export interface Run {
  id: string;
  ticket_id: number;
  status: RunStatus;
  steps: Step[];
  plan: Plan | null;
  created_at: string;
  memory_count?: number;
}

export interface MemoryNote {
  id: string;
  title: string;
  tags: string[];
  os?: string;
  created_at?: string;
  links?: string[];
  root_cause: string;
}

export interface Stats {
  total: number;
  by_status: Record<string, number>;
  active_sessions: number;
}

export interface Me {
  firstname?: string;
  lastname?: string;
  teamname?: string;
}

export interface AuditEntry {
  ts: string;
  event: string;
  [field: string]: unknown;
}

export interface RunSummary {
  id: string;
  ticket_id: number;
  status: RunStatus;
  steps: number;
  created_at: string;
}

// A persisted, durable snapshot of a terminated run (GET /api/tickets/{id}/runs,
// /api/runs/{id}/record) — the full step log of every attempt, resolved or not.
export interface RunRecordCounts {
  steps: number;
  fixes: number;
  fixes_executed: number;
  fixes_failed: number;
}

export interface RunRecord {
  id: string;
  ticket_id: number;
  status: RunStatus;
  outcome: RunStatus;
  created_at: string;
  ended_at: string;
  memory_count: number;
  counts: RunRecordCounts;
  steps: Step[];
}

export interface ActivityDraft {
  summary: string;
  root_cause: string;
  actions_taken: string;
  commands_summary: string;
  validation_result: string;
}

// A submitted activity as mirrored locally (what solved a ticket).
export interface Activity {
  id?: number | null;
  ticket_id: number;
  start_datetime?: string;
  end_datetime?: string;
  description?: string;
  summary?: string;
  root_cause?: string;
  actions_taken?: string;
  commands_summary?: string;
  validation_result?: string;
}
