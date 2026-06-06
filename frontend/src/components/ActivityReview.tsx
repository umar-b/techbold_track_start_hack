import { useEffect, useState } from "react";
import type { ActivityDraft } from "../types";
import { api, getErrorMessage } from "../api";

type Props = { runId: string; onDone: () => void };

// These are the exact ERP activity fields the technician reviews.
const FIELDS: { key: keyof ActivityDraft; label: string; rows: number }[] = [
  { key: "summary", label: "Summary", rows: 2 },
  { key: "root_cause", label: "Root cause (technical, not symptom)", rows: 2 },
  { key: "actions_taken", label: "Actions taken", rows: 3 },
  { key: "commands_summary", label: "Commands summary (no secrets)", rows: 3 },
  { key: "validation_result", label: "Validation result", rows: 2 },
];

/** Lets the technician review and submit the generated ERP activity. */
export function ActivityReview({ runId, onDone }: Props) {
  const [draft, setDraft] = useState<ActivityDraft | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    // The backend redacts secrets before sending the draft, but the user can edit it.
    let active = true;
    api.activityDraft(runId)
      .then((d) => { if (active) setDraft(d); })
      .catch((e) => { if (active) setError(getErrorMessage(e)); });
    return () => { active = false; };
  }, [runId]);

  /** Submit the reviewed text and mark the ticket done in Phoenix. */
  async function handleSubmit() {
    if (!draft) return;
    setSubmitting(true);
    setError("");
    try {
      await api.submitActivity(runId, { ...draft, set_done: true });
      setDone(true);
    } catch (e) {
      setError(getErrorMessage(e));
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <section className="panel">
        <h1>Activity submitted ✓</h1>
        <p className="muted">The activity is in the ERP and the ticket is marked DONE.</p>
        <button type="button" className="btn btn-primary" onClick={onDone}>Back to tickets</button>
      </section>
    );
  }
  if (error && !draft) return <section className="panel"><p className="error">{error}</p></section>;
  if (!draft) return <section className="panel"><p className="muted">Drafting activity…</p></section>;

  return (
    <section className="panel">
      <h1>Review activity</h1>
      <p className="muted">Edit before submitting to the ERP. Secrets are redacted automatically.</p>
      <div className="form">
        {FIELDS.map((f) => (
          <label key={f.key} className="field">
            <span>{f.label}</span>
            <textarea
              value={draft[f.key]}
              rows={f.rows}
              onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
            />
          </label>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="button" className="btn btn-primary" disabled={submitting} onClick={handleSubmit}>
          {submitting ? "Submitting…" : "Submit to ERP & mark DONE"}
        </button>
      </div>
    </section>
  );
}
