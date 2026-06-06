export type TicketStatus = "OPEN" | "PENDING" | "DONE";
export type Risk = "SAFE" | "GATED" | "BLOCKED" | null;

/** Ticket summary shown in the list and detail views. */
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

/** SSH target and operating system details for the affected VM. */
export interface SystemInfo {
  ip: string;
  port: number;
  username: string;
  os: string;
  notes?: string;
}

/** Phoenix response that links a ticket to a customer system. */
export interface CustomerSystem {
  ticket_id: number;
  customer_id: number;
  system: SystemInfo;
}

/** Output from one command after the backend redacts it. */
export interface StepResult {
  stdout: string;
  stderr: string;
  exit_code: number | null;
  duration_ms: number | null;
}

/** One visible item in the run log. */
export interface Step {
  index: number;
  kind: string;
  command: string;
  rationale: string;
  risk: Risk;
  expected: string;
  status: string;
  result: StepResult | null;
  safety_reason: string;
}

/** One command in the fix plan the technician approves. */
export interface PlanStep {
  command: string;
  rationale?: string;
  expected?: string;
  risk?: string;
}

/** Proposed root cause, fix commands, and validation checks. */
export interface Plan {
  root_cause: string;
  steps: PlanStep[];
  validation: string[];
}

/** Current backend state for one troubleshooting run. */
export interface Run {
  id: string;
  ticket_id: number;
  status: string;
  steps: Step[];
  plan: Plan | null;
  created_at: string;
}

/** Editable activity fields that get submitted back to Phoenix ERP. */
export interface ActivityDraft {
  summary: string;
  root_cause: string;
  actions_taken: string;
  commands_summary: string;
  validation_result: string;
}
