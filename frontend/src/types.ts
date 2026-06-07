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

export interface ActivityDraft {
  summary: string;
  root_cause: string;
  actions_taken: string;
  commands_summary: string;
  validation_result: string;
}
