import { useEffect, useState } from "react";
import { ArrowLeft, Loader2, Server } from "lucide-react";
import type { CustomerSystem, Ticket } from "../types";
import { api, getErrorMessage } from "../api";

type Props = {
  ticketId: number;
  onBack: () => void;
  onStartChat: (ticket: Ticket, system: CustomerSystem) => void;
};

export function TicketDetail({ ticketId, onBack, onStartChat }: Props) {
  const [data, setData] = useState<{ ticket: Ticket; system: CustomerSystem } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.getTicket(ticketId)
      .then((d) => { if (active) setData(d); })
      .catch((e) => { if (active) setError(getErrorMessage(e)); });
    return () => { active = false; };
  }, [ticketId]);

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
        </aside>
      </div>
    </section>
  );
}
