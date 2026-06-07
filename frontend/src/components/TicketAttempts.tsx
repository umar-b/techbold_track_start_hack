import { useEffect, useState } from "react";
import {
  History, ChevronDown, ChevronRight, Check, X, Minus, CircleCheck, Brain, Clock,
} from "lucide-react";
import type { RunRecord, Step } from "../types";
import { api } from "../api";
import { formatRelative, formatDuration } from "../lib/format";
import { RiskBadge } from "./RiskBadge";
import { CopyButton } from "./CopyButton";

type Props = { ticketId: number; reloadKey?: string | number };

const OUTCOME_LABEL: Record<string, string> = {
  finished: "Resolved",
  escalated: "Escalated",
  aborted: "Aborted",
};

/**
 * Every persisted attempt for a ticket — resolved, escalated, or aborted — with
 * its full step log. Reads the durable run corpus (GET /api/tickets/{id}/runs),
 * which survives a restart, so a technician can review step-by-step what the agent
 * did, including the attempts that did not succeed. Renders nothing when there is
 * no history, so it never adds noise to a fresh ticket.
 */
export function TicketAttempts({ ticketId, reloadKey }: Props) {
  const [runs, setRuns] = useState<RunRecord[] | null>(null);

  useEffect(() => {
    let active = true;
    setRuns(null);
    api.ticketRuns(ticketId)
      .then((d) => { if (active) setRuns(d.runs); })
      .catch(() => { if (active) setRuns([]); }); // history is supplementary — never block the view
    return () => { active = false; };
  }, [ticketId, reloadKey]);

  if (!runs || runs.length === 0) return null;

  return (
    <section className="attempts" aria-label="Past attempts">
      <h2 className="attempts-head">
        <History size={12} />
        Attempts
        <span className="attempts-count">{runs.length}</span>
      </h2>
      <ul className="attempts-list">
        {runs.map((run, i) => <AttemptItem key={run.id} run={run} defaultOpen={i === 0} />)}
      </ul>
    </section>
  );
}

function AttemptItem({ run, defaultOpen }: { run: RunRecord; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const { counts } = run;
  const steps = run.steps.filter((s) => s.kind !== "finish");
  const finish = run.steps.find((s) => s.kind === "finish");

  return (
    <li className={`attempt attempt--${run.outcome}`}>
      <button
        type="button"
        className="attempt-head"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span className={`pill st-run-${run.outcome}`}>{OUTCOME_LABEL[run.outcome] ?? run.outcome}</span>
        <span className="attempt-counts">
          {counts.steps} step{counts.steps === 1 ? "" : "s"}
          {counts.fixes > 0 && (
            <> · {counts.fixes_executed}/{counts.fixes} fix{counts.fixes === 1 ? "" : "es"} applied</>
          )}
        </span>
        {run.memory_count > 0 && (
          <span className="attempt-seed" title={`Seeded by ${run.memory_count} past incident(s)`}>
            <Brain size={11} />{run.memory_count}
          </span>
        )}
        <span className="attempt-when"><Clock size={11} />{formatRelative(run.ended_at)}</span>
      </button>

      {open && (
        <div className="attempt-body">
          {finish && (
            <div className={`attempt-finish${run.outcome === "finished" ? " is-ok" : " is-warn"}`}>
              {run.outcome === "finished" ? <CircleCheck size={13} /> : <Minus size={13} />}
              <span>{finish.rationale || OUTCOME_LABEL[run.outcome]}</span>
            </div>
          )}
          {steps.length === 0 ? (
            <p className="attempt-empty">No commands were run in this attempt.</p>
          ) : (
            <ol className="attempt-steps">
              {steps.map((step) => <StepRow key={step.index} step={step} />)}
            </ol>
          )}
        </div>
      )}
    </li>
  );
}

function StatusIcon({ status }: { status: Step["status"] }) {
  if (status === "executed") return <Check size={12} style={{ color: "var(--safe)" }} aria-label="succeeded" />;
  if (status === "failed" || status === "blocked")
    return <X size={12} style={{ color: "var(--danger)" }} aria-label={status} />;
  return <Minus size={12} style={{ color: "var(--muted)" }} aria-label={status} />;
}

function StepRow({ step }: { step: Step }) {
  const [showOut, setShowOut] = useState(false);
  const res = step.result;
  const stdout = res?.stdout ?? "";
  const stderr = res?.stderr ?? "";
  const hasOutput = !!(stdout || stderr);
  const duration = formatDuration(res?.duration_ms);
  const skipped = step.status === "rejected";

  return (
    <li className={`attempt-step${skipped ? " attempt-step--skipped" : ""}`}>
      <div className="attempt-step-head">
        <span className="attempt-kind">{step.kind}</span>
        <StatusIcon status={step.status} />
        {step.risk && <RiskBadge risk={step.risk} />}
        {skipped && <span className="attempt-skip-tag">not run</span>}
        <div className="attempt-step-meta">
          {duration && <span className="cmd-duration" title="Execution time">{duration}</span>}
          <CopyButton text={step.command} />
        </div>
      </div>
      <code className="cmd-block-code">{step.command}</code>
      {step.rationale && <p className="attempt-rationale">{step.rationale}</p>}
      {step.safety_reason && (
        <p className="attempt-rationale attempt-rationale--danger">{step.safety_reason}</p>
      )}
      {hasOutput && (
        <div className="cmd-output-wrap">
          <button
            type="button"
            className="cmd-output-toggle"
            aria-expanded={showOut}
            onClick={() => setShowOut((o) => !o)}
          >
            {showOut ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
            {showOut ? "Hide output" : "Show output"}
            {stderr && !showOut && <span className="cmd-output-flag">stderr</span>}
          </button>
          {showOut && (
            <>
              {stdout && <pre className="out">{stdout.slice(0, 2000)}</pre>}
              {stderr && <pre className="out out-err">{stderr.slice(0, 800)}</pre>}
            </>
          )}
        </div>
      )}
    </li>
  );
}
