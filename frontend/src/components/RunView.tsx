import { useEffect, useRef, useState } from "react";
import type { Run } from "../types";
import { api, getErrorMessage } from "../api";
import { RiskBadge } from "./RiskBadge";

type Props = {
  initialRun: Run;
  onExit: () => void;
  onActivity: (runId: string, ticketId: number) => void;
};

const TERMINAL = ["finished", "aborted", "escalated"];

/** Shows live run progress and the technician approval controls. */
export function RunView({ initialRun, onExit, onActivity }: Props) {
  const [run, setRun] = useState<Run>(initialRun);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const mounted = useRef(true);

  useEffect(() => () => { mounted.current = false; }, []);

  /** Run an approve/reject/abort action and poll while the backend is busy. */
  // Poll only while an action is in flight, so a long execute streams progress
  // without idle polling at gates (the run advances synchronously server-side).
  async function act(fn: () => Promise<Run>) {
    setBusy(true);
    setError("");
    const poll = setInterval(() => {
      api.getRun(run.id).then((r) => { if (mounted.current) setRun(r); }).catch(() => {});
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

  // Terminal runs no longer need the abort button.
  const isTerminal = TERMINAL.includes(run.status);

  return (
    <section className="run">
      <div className="run-log">
        <div className="panel-head">
          <h1>Run {run.id.slice(0, 8)}</h1>
          <span className={`pill st-run-${run.status}`}>{run.status.replace(/_/g, " ")}</span>
        </div>
        {run.steps.length === 0 && <p className="muted">Starting…</p>}
        <ol className="steps">
          {run.steps.map((s) => (
            <li key={s.index} className={`step step-${s.status}`}>
              <div className="step-head">
                <span className="step-kind">{s.kind}</span>
                <RiskBadge risk={s.risk} />
                <span className="step-status">{s.status}</span>
              </div>
              {s.command && <code className="cmd">{s.command}</code>}
              {s.rationale && <p className="rationale">{s.rationale}</p>}
              {s.safety_reason && <p className="error">⛔ {s.safety_reason}</p>}
              {s.result?.stdout && <pre className="out">{s.result.stdout.slice(0, 1200)}</pre>}
              {s.result?.stderr && <pre className="out out-err">{s.result.stderr.slice(0, 400)}</pre>}
            </li>
          ))}
        </ol>
      </div>

      <aside className="run-side">
        <div className="stage">Stage: <strong>{run.status.replace(/_/g, " ")}</strong></div>
        {error && <p className="error">{error}</p>}

        {run.status === "awaiting_plan_approval" && run.plan && (
          <div className="approval">
            <h2>Proposed fix plan</h2>
            <p className="root-cause"><strong>Root cause:</strong> {run.plan.root_cause}</p>
            <ol className="plan-steps">
              {run.plan.steps.map((st, i) => (
                <li key={i}>
                  <RiskBadge risk={st.risk ?? null} />
                  <code className="cmd">{st.command}</code>
                  {st.expected && <span className="expected">→ {st.expected}</span>}
                </li>
              ))}
            </ol>
            {run.plan.validation.length > 0 && (
              <p className="muted">Validation: {run.plan.validation.join("; ")}</p>
            )}
            <div className="actions">
              {/* Approval is the gate that lets GATED commands run on the VM. */}
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => act(() => api.approve(run.id))}>Approve &amp; run</button>
              {/* Rejecting keeps control with the technician and asks for a new plan. */}
              <button type="button" className="btn" disabled={busy} onClick={() => act(() => api.reject(run.id))}>Reject — replan</button>
            </div>
          </div>
        )}

        {run.status === "awaiting_approval" && (
          <div className="approval">
            <h2>Approve command</h2>
            <p className="muted">A command needs your approval before it runs.</p>
            <div className="actions">
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => act(() => api.approve(run.id))}>Approve</button>
              <button type="button" className="btn" disabled={busy} onClick={() => act(() => api.reject(run.id))}>Reject</button>
            </div>
          </div>
        )}

        {/* After validation, the final step is reviewing the ERP activity text. */}
        {run.status === "finished" && (
          <button type="button" className="btn btn-primary" onClick={() => onActivity(run.id, run.ticket_id)}>
            Review &amp; submit activity →
          </button>
        )}

        <div className="side-foot">
          {/* Abort lets the technician stop before the backend runs more commands. */}
          {!isTerminal && (
            <button type="button" className="btn btn-danger" disabled={busy} onClick={() => act(() => api.abort(run.id))}>Abort run</button>
          )}
          <button type="button" className="link" onClick={onExit}>Back to tickets</button>
        </div>
      </aside>
    </section>
  );
}
