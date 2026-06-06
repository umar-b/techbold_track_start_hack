import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ArrowLeft, CircleCheck, CircleX, Loader2, TriangleAlert } from "lucide-react";
import type { Run } from "../types";
import { api, getErrorMessage } from "../api";
import { RiskBadge } from "./RiskBadge";

type Props = {
  initialRun: Run;
  onExit: () => void;
  onActivity: (runId: string, ticketId: number) => void;
};

const TERMINAL = ["finished", "aborted", "escalated"];

function StatusIcon({ status }: { status: string }) {
  if (status === "executed") return <CircleCheck size={14} style={{ color: "var(--safe)" }} />;
  if (status === "failed" || status === "blocked") return <CircleX size={14} style={{ color: "var(--danger)" }} />;
  if (status === "awaiting_approval") return <TriangleAlert size={14} style={{ color: "var(--warn)" }} />;
  if (status === "running") return <Loader2 size={14} className="spin" style={{ color: "var(--navy-mid)" }} />;
  return null;
}

export function RunView({ initialRun, onExit, onActivity }: Props) {
  const [run, setRun] = useState<Run>(initialRun);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const mounted = useRef(true);
  const logRef = useRef<HTMLOListElement>(null);

  useEffect(() => () => { mounted.current = false; }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [run.steps.length]);

  async function act(fn: () => Promise<Run>) {
    setBusy(true);
    setError("");
    const poll = setInterval(() => {
      api.getRun(run.id)
        .then((r) => { if (mounted.current) setRun(r); })
        .catch(() => {});
    }, 1000);
    try {
      const updated = await fn();
      if (mounted.current) setRun(updated);
    } catch (e) {
      if (mounted.current) setError(getErrorMessage(e));
    } finally {
      clearInterval(poll);
      if (mounted.current) setBusy(false);
    }
  }

  const isTerminal = TERMINAL.includes(run.status);
  const awaitingStep = run.steps.find((s) => s.status === "awaiting_approval");

  return (
    <section className="run">
      <div className="run-log">
        <div className="panel-head">
          <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            <h1 style={{ fontSize: "1.25rem" }}>Run {run.id.slice(0, 8)}</h1>
            <span style={{ fontSize: "0.75rem", color: "var(--muted)", fontFamily: "var(--mono)" }}>
              ticket #{run.ticket_id}
            </span>
          </div>
          <span className={`pill st-run-${run.status}`}>
            {run.status.replace(/_/g, " ")}
          </span>
        </div>

        {run.steps.length === 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", color: "var(--muted)", fontSize: "0.875rem" }}>
            <Loader2 size={15} className="spin" />
            Connecting and running diagnostics…
          </div>
        )}

        <ol className="steps" ref={logRef}>
          {run.steps.map((s) => (
            <li key={s.index} className={`step step-${s.status}`}>
              <div className="step-head">
                <span className="step-kind">{s.kind}</span>
                <RiskBadge risk={s.risk} />
                <StatusIcon status={s.status} />
                <span className="step-status">{s.status.replace(/_/g, " ")}</span>
              </div>
              {s.command && <code className="cmd">{s.command}</code>}
              {s.rationale && <p className="rationale">{s.rationale}</p>}
              {s.safety_reason && (
                <p className="error" style={{ marginTop: "0.4rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                  <CircleX size={13} /> {s.safety_reason}
                </p>
              )}
              {s.result?.stdout && (
                <pre className="out">{s.result.stdout.slice(0, 1200)}</pre>
              )}
              {s.result?.stderr && (
                <pre className="out out-err">{s.result.stderr.slice(0, 400)}</pre>
              )}
            </li>
          ))}
        </ol>
      </div>

      <aside className="run-side">
        <div className="stage">
          Stage: <strong>{run.status.replace(/_/g, " ")}</strong>
        </div>

        {error && <p className="error">{error}</p>}

        <AnimatePresence mode="wait">
          {run.status === "awaiting_plan_approval" && run.plan && (
            <motion.div
              key="plan-approval"
              className="approval"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.2, ease: [0, 0, 0.2, 1] } }}
              exit={{ opacity: 0, y: -8, transition: { duration: 0.15 } }}
            >
              <h2>Proposed fix plan</h2>
              <div className="approval-card">
                <p className="root-cause">
                  <strong style={{ color: "var(--navy)" }}>Root cause:</strong>{" "}
                  {run.plan.root_cause}
                </p>
                <ol className="plan-steps" style={{ marginTop: "0.85rem", paddingLeft: "1rem" }}>
                  {run.plan.steps.map((st, i) => (
                    <li key={i} style={{ display: "flex", flexDirection: "column", gap: "0.3rem", marginBottom: "0.5rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                        <RiskBadge risk={st.risk ?? null} />
                      </div>
                      <code className="cmd">{st.command}</code>
                      {st.expected && <span className="expected">Expected: {st.expected}</span>}
                    </li>
                  ))}
                </ol>
                {run.plan.validation.length > 0 && (
                  <p className="muted" style={{ marginTop: "0.5rem" }}>
                    Validation: {run.plan.validation.join("; ")}
                  </p>
                )}
              </div>
              <div className="actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ flex: 1, width: "auto" }}
                  disabled={busy}
                  onClick={() => act(() => api.approve(run.id))}
                >
                  {busy ? "Running…" : "Approve plan"}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ flex: 1 }}
                  disabled={busy}
                  onClick={() => act(() => api.reject(run.id))}
                >
                  Reject — replan
                </button>
              </div>
            </motion.div>
          )}

          {run.status === "awaiting_approval" && (
            <motion.div
              key="step-approval"
              className="approval"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.2, ease: [0, 0, 0.2, 1] } }}
              exit={{ opacity: 0, y: -8, transition: { duration: 0.15 } }}
            >
              <h2>Review command</h2>
              <div className="approval-card">
                {awaitingStep ? (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.6rem" }}>
                      <RiskBadge risk={awaitingStep.risk} />
                      <span style={{ fontSize: "0.75rem", color: "var(--warn)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                        Requires approval
                      </span>
                    </div>
                    <code className="cmd">{awaitingStep.command}</code>
                    {awaitingStep.rationale && (
                      <p className="rationale">{awaitingStep.rationale}</p>
                    )}
                  </>
                ) : (
                  <p className="muted">A command is waiting for your approval before it runs.</p>
                )}
              </div>
              <div className="actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ flex: 1, width: "auto" }}
                  disabled={busy}
                  onClick={() => act(() => api.approve(run.id))}
                >
                  {busy ? "Running…" : "Approve"}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ flex: 1 }}
                  disabled={busy}
                  onClick={() => act(() => api.reject(run.id))}
                >
                  Reject
                </button>
              </div>
            </motion.div>
          )}

          {run.status === "finished" && (
            <motion.div
              key="finished"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, transition: { duration: 0.2 } }}
            >
              <button
                type="button"
                className="btn btn-gold"
                style={{ width: "100%" }}
                onClick={() => onActivity(run.id, run.ticket_id)}
              >
                Review &amp; submit activity →
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="side-foot">
          {!isTerminal && (
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={() => act(() => api.abort(run.id))}
            >
              Abort run
            </button>
          )}
          <button type="button" className="link" onClick={onExit}>
            <ArrowLeft size={13} />
            All tickets
          </button>
        </div>
      </aside>
    </section>
  );
}
