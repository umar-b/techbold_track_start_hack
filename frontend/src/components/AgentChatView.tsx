import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ArrowLeft, Check, X, Loader2, Terminal, Zap, ShieldAlert, TriangleAlert, Clock, ChevronDown, ChevronRight, Send, Brain } from "lucide-react";
import type { CustomerSystem, PlanStep, PlanStepEdit, Step, Ticket } from "../types";
import { useRun } from "../hooks/useRun";
import type { ConnectionState } from "../hooks/useRun";
import { RiskBadge } from "./RiskBadge";
import { CopyButton } from "./CopyButton";
import { AuditTrail } from "./AuditTrail";
import { useElapsed } from "../hooks/useElapsed";
import { formatDuration, formatElapsed } from "../lib/format";

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
  const elapsed = useElapsed(run?.created_at, isTerminal);

  // Keyboard shortcuts: A approve · R reject (while awaiting a plan) · Esc abort.
  // Approve/reject click the real buttons so an edited plan is approved exactly as
  // the click path would; typing in an input/textarea (e.g. editing a command) is
  // ignored, as are modified chords.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      const k = e.key.toLowerCase();
      if (isAwaitingPlan && plan && (k === "a" || k === "r")) {
        e.preventDefault();
        const sel = k === "a" ? '[data-shortcut="approve"]' : '[data-shortcut="reject"]';
        document.querySelector<HTMLButtonElement>(sel)?.click();
      } else if (e.key === "Escape" && run && !isTerminal && !acting) {
        e.preventDefault();
        abort();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isAwaitingPlan, plan, run, isTerminal, acting, abort]);
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

          {run && (run.memory_count ?? 0) > 0 && (
            <div className="chat-seed" title="Past incidents seeded the agent's hypotheses">
              <Brain size={12} />
              Seeded by {run.memory_count} past incident{run.memory_count === 1 ? "" : "s"} — verified against live evidence.
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
                mode={plan.mode}
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
                title="Abort (Esc)"
                disabled={acting}
                onClick={abort}
              >
                Abort <kbd style={{ marginLeft: "0.4rem" }}>Esc</kbd>
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
          {run && (
            <div className="chat-side-elapsed" title={isTerminal ? "Total run time" : "Elapsed"}>
              <Clock size={11} />
              <span className="mono">{formatElapsed(elapsed)}</span>
              {!isTerminal && <span className="chat-side-elapsed-label">elapsed</span>}
            </div>
          )}
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

        {run && (
          <>
            <div className="chat-side-divider" />
            <AuditTrail runId={run.id} refreshKey={`${status}:${steps.length}`} />
          </>
        )}
      </aside>
    </div>
  );
}

function StepView({ step }: { step: Step }) {
  const [showOutput, setShowOutput] = useState(false);
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
  const stdout = step.result?.stdout ?? "";
  const stderr = step.result?.stderr ?? "";
  const hasOutput = !!(stdout || stderr);

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
        {hasOutput && (
          <div className="cmd-output-wrap">
            <button
              type="button"
              className="cmd-output-toggle"
              aria-expanded={showOutput}
              onClick={() => setShowOutput((o) => !o)}
            >
              {showOutput ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
              {showOutput ? "Hide output" : "Show output"}
              {failed && !showOutput && <span className="cmd-output-flag">error</span>}
            </button>
            {showOutput && (
              <>
                {stdout && (
                  <div className="chat-output" style={{ marginTop: "0.4rem" }}>
                    <pre>{stdout.slice(0, 2000)}</pre>
                  </div>
                )}
                {stderr && (
                  <div className="chat-output" style={{ marginTop: "0.4rem" }}>
                    <pre style={{ color: "var(--danger)" }}>{stderr.slice(0, 800)}</pre>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function PlanApproval({
  rootCause, steps, validation, mode, busy, onApprove, onReject,
}: {
  rootCause: string;
  steps: PlanStep[];
  validation: string[];
  mode?: "fix" | "diagnostic";
  busy: boolean;
  onApprove: (editedSteps?: PlanStepEdit[]) => void;
  onReject: (feedback?: string) => void;
}) {
  const isDiagnostic = mode === "diagnostic";
  const [editing, setEditing] = useState(false);
  const [cmds, setCmds] = useState<string[]>(() => steps.map((s) => s.command));
  const [discussOpen, setDiscussOpen] = useState(false);
  const [note, setNote] = useState("");
  // Reset edits only when the plan CONTENT changes (a genuine replan) — keyed on
  // content, not array identity, so an SSE reconnect replaying the same plan does
  // not silently discard in-progress edits.
  const planKey = `${rootCause} ${steps.map((s) => s.command).join(" ")}`;
  useEffect(() => {
    setCmds(steps.map((s) => s.command));
    setEditing(false);
    setDiscussOpen(false);
    setNote("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planKey]);

  const command = (i: number) => cmds[i] ?? steps[i]?.command ?? "";
  const dirty = steps.some((s, i) => command(i) !== s.command);
  const hasEmpty = editing && steps.some((_, i) => !command(i).trim());

  function handleApprove() {
    if (!dirty) return onApprove();
    onApprove(steps.map((s, i) => ({ command: command(i), rationale: s.rationale ?? "", expected: s.expected ?? "" })));
  }

  function handleSendNote() {
    const text = note.trim();
    if (text) onReject(text); // replan, steered by the technician's note
  }

  return (
    <div className="chat-msg-agent chat-msg-cmd-wrap" style={{ maxWidth: "100%" }}>
      <div className="chat-avatar chat-avatar--sm">
        <Zap size={11} />
      </div>
      <div className="plan-card">
        <div className="plan-head">
          <span className="badge badge-gated plan-badge">
            <ShieldAlert size={11} />{isDiagnostic ? "DIAGNOSTIC" : "FIX PLAN"}{dirty ? " · edited" : ""}
          </span>
          <span className="plan-title">
            {isDiagnostic
              ? "The agent needs to run this to gather evidence — approve?"
              : "Proposed fix — your approval required"}
          </span>
          <button
            type="button"
            className="link plan-edit-toggle"
            disabled={busy}
            aria-expanded={editing}
            aria-controls="plan-steps"
            onClick={() => setEditing((e) => !e)}
          >
            {editing ? "Done editing" : "Edit commands"}
          </button>
        </div>

        {!isDiagnostic && (
          <div className="plan-rootcause">
            <span className="plan-rootcause-label">Root cause</span>
            <p>{rootCause || "—"}</p>
          </div>
        )}

        <ol id="plan-steps" className="plan-steps2">
          {steps.map((st, i) => (
            <li key={i} className="plan-step">
              <span className="plan-step-num">{i + 1}</span>
              <div className="plan-step-body">
                <div className="plan-step-meta">
                  {command(i) !== st.command ? (
                    <span className="badge badge-none">edited · risk re-checked on run</span>
                  ) : (
                    <RiskBadge risk={st.risk ?? null} />
                  )}
                </div>
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
                  />
                ) : (
                  <code className="cmd-block-code">{command(i)}</code>
                )}
                {st.rationale && <span className="cmd-block-rationale" style={{ margin: 0, padding: 0 }}>{st.rationale}</span>}
                {st.expected && <span className="expected">Expected: {st.expected}</span>}
              </div>
            </li>
          ))}
        </ol>

        {validation.length > 0 && (
          <div className="plan-validation">
            <span className="plan-validation-label">Validation</span>
            <ul>
              {validation.map((v, i) => <li key={i}><code>{v}</code></li>)}
            </ul>
          </div>
        )}

        {dirty && (
          <p className="plan-note">Edited commands are still safety-checked before they run.</p>
        )}

        {!isDiagnostic && (
        <div className="plan-discuss">
          <button
            type="button"
            className="plan-discuss-toggle"
            aria-expanded={discussOpen}
            disabled={busy}
            onClick={() => setDiscussOpen((o) => !o)}
          >
            {discussOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Discuss / request changes
          </button>
          {discussOpen && (
            <div className="plan-discuss-area">
              <textarea
                className="plan-discuss-input"
                rows={2}
                placeholder="e.g. Reload instead of restart, and check the config first…"
                aria-label="Ask the agent to adjust the plan"
                value={note}
                disabled={busy}
                onChange={(e) => setNote(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); handleSendNote(); }
                }}
              />
              <div className="plan-discuss-foot">
                <span className="muted" style={{ fontSize: "0.72rem" }}>The agent revises the plan with your notes (⌘/Ctrl+↵).</span>
                <button type="button" className="btn btn-ghost plan-send" disabled={busy || !note.trim()} onClick={handleSendNote}>
                  <Send size={12} /> Send &amp; revise
                </button>
              </div>
            </div>
          )}
        </div>
        )}

        <div className="cmd-block-actions plan-actions">
          <button type="button" className="btn btn-gold cmd-approve-btn" data-shortcut="approve"
                  aria-label={dirty ? "Approve the edited command(s)" : (isDiagnostic ? "Approve and run the diagnostic" : "Approve the proposed fix plan")}
                  disabled={busy || hasEmpty} onClick={handleApprove}>
            {busy ? "Running…" : isDiagnostic ? (dirty ? "Run edited command" : "Approve & run") : (dirty ? "Approve edited plan" : "Approve plan")}
          </button>
          <button type="button" className="btn btn-danger" data-shortcut="reject"
                  aria-label={isDiagnostic ? "Skip this diagnostic" : "Reject the plan and replan"} disabled={busy} onClick={() => onReject()}>
            {isDiagnostic ? "Skip" : "Reject — replan"}
          </button>
          {!editing && !discussOpen && (
            <span className="kbd-hint">
              <kbd>A</kbd> approve · <kbd>R</kbd> reject
            </span>
          )}
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
