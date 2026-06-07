import { useEffect, useState } from "react";
import { ArrowLeft, Loader2, Server, CircleCheck } from "lucide-react";
import type { Activity, CustomerSystem, Ticket } from "../types";
import { api, getErrorMessage } from "../api";
import { formatRelative } from "../lib/format";

type Props = {
  ticketId: number;
  onBack: () => void;
  onStartChat: (ticket: Ticket, system: CustomerSystem) => void;
};

export function TicketDetail({ ticketId, onBack, onStartChat }: Props) {
  const [data, setData] = useState<{ ticket: Ticket; system: CustomerSystem } | null>(null);
  const [activity, setActivity] = useState<Activity | null>(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    setError("");
    api.getTicket(ticketId)
      .then((d) => { if (active) setData(d); })
      .catch((e) => { if (active) setError(getErrorMessage(e)); });
    return () => { active = false; };
  }, [ticketId, reloadKey]);

  // Show the latest resolution when a solved ticket is reopened. Best-effort —
  // a failure here must not block the ticket view.
  useEffect(() => {
    let active = true;
    setActivity(null);
    api.ticketActivities(ticketId)
      .then((d) => { if (active) setActivity(d.activities[0] ?? null); })
      .catch(() => { /* no resolution to show */ });
    return () => { active = false; };
  }, [ticketId, reloadKey]);

  function handleStart() {
    if (!data) return;
    onStartChat(data.ticket, data.system);
  }

  if (error && !data) {
    return (
      <section className="panel">
        <button type="button" className="link" onClick={onBack}>
          <ArrowLeft size={13} /> All tickets
        </button>
        <p className="error">{error}</p>
        <button type="button" className="btn btn-ghost" style={{ width: "auto", marginTop: "0.75rem" }}
                onClick={() => setReloadKey((k) => k + 1)}>
          Retry
        </button>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="panel">
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", color: "var(--muted)", fontSize: "0.875rem" }}>
          <Loader2 size={15} className="spin" />
          Loading ticket…
        </div>
      </section>
    );
  }

  const { ticket, system } = data;
  const sys = system.system;

  return (
    <section className="panel">
      <button type="button" className="link" onClick={onBack}>
        <ArrowLeft size={13} /> All tickets
      </button>

      {activity && <ResolutionPanel activity={activity} />}

      <div className="detail-grid">
        <article>
          <h1>
            <span style={{ color: "var(--muted)", fontWeight: 700, fontSize: "1rem", fontFamily: "var(--mono)", marginRight: "0.5rem" }}>
              #{ticket.id}
            </span>
            {ticket.title}
          </h1>
          <div className="meta-row">
            <span className={`pill pri-${ticket.priority}`}>{ticket.priority}</span>
            <span className={`pill st-${ticket.status}`}>{ticket.status}</span>
            <span className="muted">{ticket.customer_name}</span>
            {ticket.tags?.map((tag) => <span key={tag} className="tag">{tag}</span>)}
          </div>
          <pre className="report">{ticket.description}</pre>
        </article>

        <aside className="system-card">
          <h2 style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Server size={12} />
            Customer system
          </h2>
          <dl>
            <dt>Host</dt>
            <dd>{sys.ip}:{sys.port}</dd>
            <dt>User</dt>
            <dd>{sys.username}</dd>
            <dt>OS</dt>
            <dd style={{ fontFamily: "var(--font-body)", fontSize: "0.875rem", color: "var(--ink-soft)" }}>{sys.os}</dd>
            {sys.notes && (
              <>
                <dt>Notes</dt>
                <dd style={{ fontFamily: "var(--font-body)", fontSize: "0.8125rem", color: "var(--ink-soft)" }}>{sys.notes}</dd>
              </>
            )}
          </dl>

          {error && <p className="error" style={{ marginBottom: "0.75rem" }}>{error}</p>}

          {ticket.status === "DONE" ? (
            <p className="hint" style={{ marginTop: 0 }}>
              This ticket is resolved — the resolution is shown above.
            </p>
          ) : (
            <>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleStart}
              >
                Connect &amp; diagnose
              </button>

              <p className="hint">
                The agent runs read-only diagnostics, then proposes a fix plan for your approval. Nothing changes without you.
              </p>
            </>
          )}
        </aside>
      </div>
    </section>
  );
}

const RESOLUTION_FIELDS: { key: keyof Activity; label: string }[] = [
  { key: "summary", label: "Summary" },
  { key: "root_cause", label: "Root cause" },
  { key: "actions_taken", label: "Actions taken" },
  { key: "commands_summary", label: "Commands" },
  { key: "validation_result", label: "Validation" },
];

function ResolutionPanel({ activity }: { activity: Activity }) {
  const rows = RESOLUTION_FIELDS.filter((f) => {
    const v = activity[f.key];
    return typeof v === "string" && v.trim();
  });
  const mono = new Set<keyof Activity>(["commands_summary"]);
  return (
    <div className="resolution">
      <div className="resolution-head">
        <span className="resolution-icon"><CircleCheck size={15} /></span>
        <span className="resolution-title">Resolution</span>
        {activity.end_datetime && (
          <span className="muted resolution-when">solved {formatRelative(activity.end_datetime)}</span>
        )}
      </div>
      <dl className="resolution-dl">
        {rows.map((f) => (
          <div key={String(f.key)} className="resolution-row">
            <dt>{f.label}</dt>
            <dd className={mono.has(f.key) ? "mono" : undefined}>{activity[f.key] as string}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
