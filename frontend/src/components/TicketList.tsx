import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import type { Ticket } from "../types";
import { api, getErrorMessage } from "../api";

type Props = { onOpen: (ticketId: number) => void };

export function TicketList({ onOpen }: Props) {
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [error, setError] = useState("");
  const [sort, setSort] = useState("date");

  useEffect(() => {
    let active = true;
    setTickets(null);
    setError("");
    api.listTickets(sort)
      .then((data) => { if (active) setTickets(data); })
      .catch((e) => { if (active) setError(getErrorMessage(e)); });
    return () => { active = false; };
  }, [sort]);

  return (
    <section className="panel">
      <div className="panel-head">
        <h1>Assigned tickets</h1>
        <label className="sort">
          Sort by
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="date">date</option>
            <option value="priority">priority</option>
            <option value="status">status</option>
          </select>
        </label>
      </div>

      {error && <p className="error">Could not load tickets: {error}</p>}

      {!tickets && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", color: "var(--muted)", fontSize: "0.875rem" }}>
          <Loader2 size={15} className="spin" />
          Loading tickets…
        </div>
      )}

      {tickets && tickets.length === 0 && (
        <div style={{ padding: "2rem 0", textAlign: "center" }}>
          <p className="muted">No tickets currently assigned.</p>
        </div>
      )}

      <ul className="ticket-list">
        {tickets?.map((t) => (
          <li key={t.id}>
            <button type="button" className="ticket-row" onClick={() => onOpen(t.id)}>
              <span className="ticket-id">#{t.id}</span>
              <span className="ticket-title">{t.title}</span>
              <span className="ticket-customer">{t.customer_name}</span>
              <span className={`pill pri-${t.priority}`}>{t.priority}</span>
              <span className={`pill st-${t.status}`}>{t.status}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
