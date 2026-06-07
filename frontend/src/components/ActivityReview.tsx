import { useEffect, useState } from "react";
import { CircleCheck, Loader2, Check, X } from "lucide-react";
import type { ActivityDraft, Run } from "../types";
import { api, getErrorMessage } from "../api";
import { toast } from "../lib/toast";
import { formatDuration } from "../lib/format";

type Props = { runId?: string; prefillDraft?: ActivityDraft; onDone: () => void };

const FIELDS: { key: keyof ActivityDraft; label: string; rows: number; hint?: string }[] = [
  { key: "summary", label: "Summary", rows: 2, hint: "One sentence: what was restored." },
  { key: "root_cause", label: "Root cause", rows: 2, hint: "Technical root cause, not the symptom." },
  { key: "actions_taken", label: "Actions taken", rows: 3, hint: "Diagnosis and fix steps in order." },
  { key: "commands_summary", label: "Commands summary", rows: 3, hint: "Relevant commands — no secrets or credentials." },
  { key: "validation_result", label: "Validation result", rows: 2, hint: "Concrete proof the customer benefit is restored." },
];

export function ActivityReview({ runId, prefillDraft, onDone }: Props) {
  const [draft, setDraft] = useState<ActivityDraft | null>(prefillDraft ?? null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (prefillDraft || !runId) return;
    let active = true;
    api.activityDraft(runId)
      .then((d) => { if (active) setDraft(d); })
      .catch((e) => { if (active) setError(getErrorMessage(e)); });
    return () => { active = false; };
  }, [runId, prefillDraft]);

  // Pull the run so the technician can see what the agent actually did while writing
  // the activity. Best-effort context — a failure here must not block documenting.
  useEffect(() => {
    if (!runId) return;
    let active = true;
    api.getRun(runId).then((r) => { if (active) setRun(r); }).catch(() => { /* optional context */ });
    return () => { active = false; };
  }, [runId]);

  const ranSteps = (run?.steps ?? []).filter(
    (s) => ["diagnose", "fix", "validate"].includes(s.kind) && s.command,
  );

  async function handleSubmit() {
    if (!draft) return;
    setSubmitting(true);
    setError("");
    try {
      if (runId) {
        await api.submitActivity(runId, { ...draft, set_done: true });
      }
      toast.success("Activity logged to ERP — ticket marked DONE");
      setDone(true);
    } catch (e) {
      const msg = getErrorMessage(e);
      setError(msg);
      toast.error(msg);
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <section className="panel">
        <div className="done-banner">
          <div className="done-icon">
            <CircleCheck size={20} />
          </div>
          <div>
            <h1>Activity submitted</h1>
            <p className="muted" style={{ marginTop: "0.25rem" }}>
              Activity logged to ERP. Ticket marked DONE.
            </p>
          </div>
        </div>
        <div style={{ marginTop: "1.5rem" }}>
          <button type="button" className="btn btn-primary" style={{ width: "auto" }} onClick={onDone}>
            Back to tickets
          </button>
        </div>
      </section>
    );
  }

  if (error && !draft) {
    return (
      <section className="panel">
        <p className="error">{error}</p>
      </section>
    );
  }

  if (!draft) {
    return (
      <section className="panel">
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", color: "var(--muted)", fontSize: "0.875rem" }}>
          <Loader2 size={15} className="spin" />
          Drafting activity…
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <h1>Review activity</h1>
      <p className="muted">
        Edit before submitting to the ERP. Secrets are redacted automatically.
      </p>

      {ranSteps.length > 0 && (
        <details className="ran-timeline" open>
          <summary>What the agent did <span className="muted">({ranSteps.length} command{ranSteps.length === 1 ? "" : "s"})</span></summary>
          <ol className="ran-list">
            {ranSteps.map((s) => {
              const ok = s.status === "executed";
              const dur = formatDuration(s.result?.duration_ms);
              return (
                <li key={s.index} className="ran-step">
                  <span className={`ran-icon ${ok ? "ran-ok" : "ran-bad"}`}>
                    {ok ? <Check size={11} /> : <X size={11} />}
                  </span>
                  <code className="ran-cmd">{s.command}</code>
                  <span className="ran-kind">{s.kind}</span>
                  {dur && <span className="ran-dur">{dur}</span>}
                </li>
              );
            })}
          </ol>
        </details>
      )}

      <div className="form">
        {FIELDS.map((f) => (
          <label key={f.key} className="field">
            <span>{f.label}</span>
            <textarea
              value={draft[f.key]}
              rows={f.rows}
              onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
            />
            {f.hint && <span style={{ fontSize: "0.75rem", color: "var(--muted)", textTransform: "none", letterSpacing: 0, fontWeight: 400 }}>{f.hint}</span>}
          </label>
        ))}
      </div>

      {error && <p className="error" style={{ marginBottom: "0.75rem" }}>{error}</p>}

      <div className="submit-foot">
        <button
          type="button"
          className="btn btn-gold"
          style={{ width: "auto" }}
          disabled={submitting}
          onClick={handleSubmit}
        >
          {submitting ? (
            <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Loader2 size={13} className="spin" /> Submitting…
            </span>
          ) : "Submit to ERP & mark DONE"}
        </button>
      </div>
    </section>
  );
}
