import { useEffect, useState } from "react";
import type { Ticket } from "../types";
import { api, getErrorMessage } from "../api";

type Props = { onOpen: (ticketId: number) => void };

/** Shows assigned tickets and lets the technician choose which one to inspect. */
export function TicketList({ onOpen }: Props) {
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [error, setError] = useState("");
  const [sort, setSort] = useState("date");

  useEffect(() => {
    // Ignore late responses when the sort changes or the component unmounts.
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
        <h1>Open tickets</h1>
        <label className="sort">
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="date">date</option>
            <option value="priority">priority</option>
            <option value="status">status</option>
          </select>
        </label>
      </div>
      {error && <p className="error">Could not load tickets: {error}</p>}
      {!tickets && !error && <p className="muted">Loading…</p>}
      {tickets && tickets.length === 0 && <p className="muted">No tickets assigned.</p>}
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
