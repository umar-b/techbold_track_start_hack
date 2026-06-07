import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ArrowLeft, Check, X, Loader2, Terminal, Zap, ShieldAlert, TriangleAlert } from "lucide-react";
import type { CustomerSystem, PlanStep, PlanStepEdit, Step, Ticket } from "../types";
import { useRun } from "../hooks/useRun";
import type { ConnectionState } from "../hooks/useRun";
import { RiskBadge } from "./RiskBadge";
import { CopyButton } from "./CopyButton";
import { formatDuration } from "../lib/format";

type Props = {
  ticket: Ticket;
  system: CustomerSystem;
  onExit: () => void;
  onActivity: (runId: string) => void;
};

export function AgentChatView({ ticket, system, onExit, onActivity }: Props) {
  const sys = system.system;
  const { run, steps, status, plan, error, starting, acting, connection, isAwaitingPlan, isTerminal, approve, reject, abort } =
    useRun(ticket.id);

  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [steps.length, status, isAwaitingPlan]);

  const finished = status === "finished";
  const escalated = status === "escalated";
  const aborted = status === "aborted";
  const working =
    starting ||
    status === "analyzing" ||
    status === "executing" ||
    status === "verifying" ||
    (isAwaitingPlan && !plan); // awaiting approval but the plan event hasn't landed yet

  return (
    <div className="chat-layout">
      <div className="chat-main">
        <div className="chat-messages">
          <div className="chat-msg-status">
            Connecting to {sys.ip}:{sys.port} as {sys.username} — read-only diagnostics first.
          </div>

          {starting && (
            <div className="chat-msg-status">
              Running read-only diagnostics and forming a plan — this can take a moment…
            </div>
          )}

          <AnimatePresence initial={false}>
            {steps.map((step) => (
              <motion.div
                key={step.index}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
              >
                <StepView step={step} />
              </motion.div>
            ))}
          </AnimatePresence>

          {working && <TypingIndicator />}

          {isAwaitingPlan && plan && (
            <motion.div key={`plan-${run?.id ?? ""}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
              <PlanApproval
                rootCause={plan.root_cause}
                steps={plan.steps}
                validation={plan.validation}
                busy={acting}
                onApprove={approve}
                onReject={reject}
              />
            </motion.div>
          )}

          {escalated && (
            <div className="chat-msg-status" style={{ color: "var(--warn)" }}>
              <TriangleAlert size={12} style={{ display: "inline", marginRight: 4, verticalAlign: "-2px" }} />
              Escalated to the technician — the agent could not converge on a safe fix.
            </div>
          )}
          {aborted && <div className="chat-msg-status">Run aborted.</div>}

          {error && <div className="chat-msg-status" style={{ color: "var(--danger)" }}>{error}</div>}

          <div ref={bottomRef} />
        </div>

        {finished && run ? (
          <div className="chat-done-bar">
            <span className="chat-done-text">Incident resolved — activity draft ready</span>
            <button type="button" className="btn btn-gold chat-done-btn" onClick={() => onActivity(run.id)}>
              Review &amp; submit activity
            </button>
          </div>
        ) : (
          <div className="chat-input-bar">
            {!isTerminal && <ConnectionDot state={connection} />}
            <span className="chat-stage-label">
              {starting ? "Starting run…" : status.replace(/_/g, " ")}
            </span>
            {!isTerminal && run && (
              <button
                type="button"
                className="btn btn-danger chat-send-btn"
                aria-label={`Abort run for ticket #${ticket.id}`}
                disabled={acting}
                onClick={abort}
              >
                Abort
              </button>
            )}
          </div>
        )}
      </div>

      <aside className="chat-sidebar">
        <button type="button" className="link" style={{ marginBottom: "0.75rem" }} onClick={onExit}>
          <ArrowLeft size={13} /> All tickets
        </button>

        <div className="chat-side-ticket">
          <div className="chat-side-id">#{ticket.id}</div>
          <div className="chat-side-title">{ticket.title}</div>
          <div className="chat-side-meta">
            <span className={`pill pri-${ticket.priority}`}>{ticket.priority}</span>
            <span className={`pill st-${ticket.status}`}>{ticket.status}</span>
          </div>
          <div className="chat-side-customer">{ticket.customer_name}</div>
        </div>

        <div className="chat-side-divider" />

        <div className="chat-side-system">
          <h2 style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.6rem" }}>
            <Terminal size={11} />
            Customer system
          </h2>
          <dl className="chat-side-dl">
            <dt>Host</dt>
            <dd>{sys.ip}:{sys.port}</dd>
            <dt>User</dt>
            <dd>{sys.username}</dd>
            <dt>OS</dt>
            <dd style={{ fontFamily: "var(--font-body)", fontSize: "0.8125rem", color: "var(--ink-soft)" }}>{sys.os}</dd>
            {sys.notes && (
              <>
                <dt>Notes</dt>
                <dd style={{ fontFamily: "var(--font-body)", fontSize: "0.8rem", color: "var(--ink-soft)" }}>{sys.notes}</dd>
              </>
            )}
          </dl>
        </div>
      </aside>
    </div>
  );
}

function StepView({ step }: { step: Step }) {
  if (step.kind === "finish") {
    return (
      <div className="chat-msg-done">
        <div className="chat-msg-done-icon">
          <Check size={14} />
        </div>
        <p>{step.rationale || "Done."}</p>
      </div>
    );
  }

  const gated = step.risk === "GATED";
  const blocked = step.status === "blocked" || step.risk === "BLOCKED";
  const failed = step.status === "failed";
  const running = step.status === "proposed";
  const stateClass = blocked || failed ? "cmd-block--rejected" : step.status === "executed" ? "cmd-block--done" : "";
  const duration = formatDuration(step.result?.duration_ms);

  return (
    <div className="chat-msg-agent chat-msg-cmd-wrap">
      <div className="chat-avatar chat-avatar--sm">
        <Terminal size={11} />
      </div>
      <div className={`cmd-block ${stateClass}`}>
        <div className="cmd-block-header">
          {blocked ? (
            <span className="badge badge-gated" style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <ShieldAlert size={10} />BLOCKED
            </span>
          ) : gated ? (
            <span className="badge badge-gated" style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <ShieldAlert size={10} />GATED
            </span>
          ) : (
            <span className="badge badge-safe">AUTO</span>
          )}
          <div className="cmd-block-meta">
            {duration && <span className="cmd-duration" title="Execution time">{duration}</span>}
            <CopyButton text={step.command} />
            {running && <Loader2 size={12} className="spin" style={{ color: "var(--muted)" }} />}
            {step.status === "executed" && <Check size={12} style={{ color: "var(--safe)" }} />}
            {(blocked || failed) && <X size={12} style={{ color: "var(--danger)" }} />}
          </div>
        </div>
        <code className="cmd-block-code">{step.command}</code>
        {step.rationale && <p className="cmd-block-rationale">{step.rationale}</p>}
        {step.safety_reason && (
          <p className="cmd-block-rationale" style={{ color: "var(--danger)" }}>{step.safety_reason}</p>
        )}
        {step.result?.stdout && (
          <div className="chat-output" style={{ marginTop: "0.5rem" }}>
            <pre>{step.result.stdout.slice(0, 1200)}</pre>
          </div>
        )}
        {step.result?.stderr && (
          <div className="chat-output" style={{ marginTop: "0.4rem" }}>
            <pre style={{ color: "var(--danger)" }}>{step.result.stderr.slice(0, 400)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

function PlanApproval({
  rootCause, steps, validation, busy, onApprove, onReject,
}: {
  rootCause: string;
  steps: PlanStep[];
  validation: string[];
  busy: boolean;
  onApprove: (editedSteps?: PlanStepEdit[]) => void;
  onReject: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [cmds, setCmds] = useState<string[]>(() => steps.map((s) => s.command));
  // Reset edits only when the plan CONTENT changes (a genuine replan) — keyed on
  // content, not array identity, so an SSE reconnect replaying the same plan does
  // not silently discard in-progress edits.
  const planKey = `${rootCause} ${steps.map((s) => s.command).join(" ")}`;
  useEffect(() => {
    setCmds(steps.map((s) => s.command));
    setEditing(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planKey]);

  const command = (i: number) => cmds[i] ?? steps[i]?.command ?? "";
  const dirty = steps.some((s, i) => command(i) !== s.command);
  const hasEmpty = editing && steps.some((_, i) => !command(i).trim());

  function handleApprove() {
    if (!dirty) return onApprove();
    onApprove(steps.map((s, i) => ({ command: command(i), rationale: s.rationale ?? "", expected: s.expected ?? "" })));
  }

  return (
    <div className="chat-msg-agent chat-msg-cmd-wrap">
      <div className="chat-avatar chat-avatar--sm">
        <Zap size={11} />
      </div>
      <div className="cmd-block cmd-block--pending" style={{ width: "100%" }}>
        <div className="cmd-block-header">
          <span className="badge badge-gated" style={{ display: "flex", alignItems: "center", gap: 3 }}>
            <ShieldAlert size={10} />FIX PLAN{dirty ? " · edited" : ""}
          </span>
          <button
            type="button"
            className="link"
            style={{ marginLeft: "auto", fontSize: "0.75rem" }}
            disabled={busy}
            aria-expanded={editing}
            aria-controls="plan-steps"
            onClick={() => setEditing((e) => !e)}
          >
            {editing ? "Done editing" : "Edit"}
          </button>
        </div>
        <p className="cmd-block-rationale" style={{ marginTop: 0 }}>
          <strong style={{ color: "var(--navy, #1e293b)" }}>Root cause:</strong> {rootCause}
        </p>
        <ol id="plan-steps" style={{ margin: "0.6rem 0 0", paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          {steps.map((st, i) => (
            <li key={i} style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
              {command(i) !== st.command ? (
                <span className="badge badge-none">edited · risk re-checked on run</span>
              ) : (
                <RiskBadge risk={st.risk ?? null} />
              )}
              {editing ? (
                <textarea
                  className="plan-edit"
                  value={command(i)}
                  rows={2}
                  spellCheck={false}
                  aria-label={`Edit command ${i + 1}`}
                  onChange={(e) => setCmds((prev) => {
                    const next = steps.map((s, j) => prev[j] ?? s.command);
                    next[i] = e.target.value;
                    return next;
                  })}
                  style={{
                    fontFamily: "var(--mono)", fontSize: "0.8125rem", width: "100%", resize: "vertical",
                    padding: "0.4rem 0.5rem", borderRadius: "4px", border: "1px solid var(--warn, #d97706)",
                  }}
                />
              ) : (
                <code className="cmd-block-code">{command(i)}</code>
              )}
              {st.expected && <span className="expected">Expected: {st.expected}</span>}
            </li>
          ))}
        </ol>
        {validation.length > 0 && (
          <p className="cmd-block-rationale">Validation: {validation.join("; ")}</p>
        )}
        {dirty && (
          <p className="cmd-block-rationale" style={{ color: "var(--warn, #d97706)" }}>
            Edited commands are still safety-checked before they run.
          </p>
        )}
        <div className="cmd-block-actions">
          <button type="button" className="btn btn-gold cmd-approve-btn"
                  aria-label={dirty ? "Approve the edited fix plan" : "Approve the proposed fix plan"}
                  disabled={busy || hasEmpty} onClick={handleApprove}>
            {busy ? "Running…" : dirty ? "Approve edited plan" : "Approve plan"}
          </button>
          <button type="button" className="btn btn-danger"
                  aria-label="Reject the plan and replan" disabled={busy} onClick={onReject}>
            Reject — replan
          </button>
        </div>
      </div>
    </div>
  );
}

const CONNECTION_LABEL: Record<ConnectionState, string> = {
  connecting: "Connecting to live stream…",
  live: "Live",
  reconnecting: "Reconnecting…",
  closed: "Stream closed",
};

function ConnectionDot({ state }: { state: ConnectionState }) {
  return (
    <span className="conn" title={CONNECTION_LABEL[state]} aria-label={CONNECTION_LABEL[state]} role="status">
      <span className={`conn-dot conn-dot--${state}`} />
      <span className="conn-text">{state === "live" ? "Live" : CONNECTION_LABEL[state]}</span>
    </span>
  );
}

function TypingIndicator() {
  return (
    <div className="chat-msg-agent">
      <div className="chat-avatar">
        <Zap size={12} />
      </div>
      <div className="chat-typing">
        <span className="chat-typing-dot" />
        <span className="chat-typing-dot" />
        <span className="chat-typing-dot" />
      </div>
    </div>
  );
}
