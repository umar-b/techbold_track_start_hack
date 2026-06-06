import { useEffect, useState } from "react";
import type { CustomerSystem, Run, Ticket } from "../types";
import { api, getErrorMessage } from "../api";

type Props = {
  ticketId: number;
  onBack: () => void;
  onStarted: (run: Run) => void;
};

export function TicketDetail({ ticketId, onBack, onStarted }: Props) {
  const [data, setData] = useState<{ ticket: Ticket; system: CustomerSystem } | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    let active = true;
    api.getTicket(ticketId)
      .then((d) => { if (active) setData(d); })
      .catch((e) => { if (active) setError(getErrorMessage(e)); });
    return () => { active = false; };
  }, [ticketId]);

  async function handleStart() {
    setStarting(true);
    setError("");
    try {
      onStarted(await api.startRun(ticketId));
    } catch (e) {
      setError(getErrorMessage(e));
      setStarting(false);
    }
  }

  if (error && !data) {
    return (
      <section className="panel">
        <button type="button" className="link" onClick={onBack}>← all tickets</button>
        <p className="error">{error}</p>
      </section>
    );
  }
  if (!data) return <section className="panel"><p className="muted">Loading…</p></section>;

  const { ticket, system } = data;
  const sys = system.system;
  return (
    <section className="panel">
      <button type="button" className="link" onClick={onBack}>← all tickets</button>
      <div className="detail-grid">
        <article>
          <h1>#{ticket.id} {ticket.title}</h1>
          <div className="meta-row">
            <span className={`pill pri-${ticket.priority}`}>{ticket.priority}</span>
            <span className={`pill st-${ticket.status}`}>{ticket.status}</span>
            <span className="muted">{ticket.customer_name}</span>
          </div>
          <pre className="report">{ticket.description}</pre>
        </article>
        <aside className="system-card">
          <h2>Customer system</h2>
          <dl>
            <dt>Host</dt><dd className="mono">{sys.ip}:{sys.port}</dd>
            <dt>User</dt><dd className="mono">{sys.username}</dd>
            <dt>OS</dt><dd>{sys.os}</dd>
            {sys.notes && (<><dt>Notes</dt><dd className="muted">{sys.notes}</dd></>)}
          </dl>
          {error && <p className="error">{error}</p>}
          <button type="button" className="btn btn-primary" disabled={starting} onClick={handleStart}>
            {starting ? "Connecting…" : "Connect & diagnose"}
          </button>
          <p className="hint">The agent runs read-only diagnostics, then proposes a fix plan for your approval. Nothing changes without you.</p>
        </aside>
      </div>
    </section>
  );
}
