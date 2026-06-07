import { useEffect, useMemo, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import type { RunSummary, Ticket } from "../types";
import { api, getErrorMessage } from "../api";

type Props = { onOpen: (ticketId: number) => void };

const STATUS_OPTIONS = ["all", "OPEN", "PENDING", "DONE"] as const;
const PRIORITY_OPTIONS = ["all", "high", "medium", "low"] as const;
const TERMINAL_RUN = new Set(["finished", "aborted", "escalated"]);

export function TicketList({ onOpen }: Props) {
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [error, setError] = useState("");
  const [sort, setSort] = useState("date");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_OPTIONS)[number]>("all");
  const [priorityFilter, setPriorityFilter] = useState<(typeof PRIORITY_OPTIONS)[number]>("all");
  const [reloadKey, setReloadKey] = useState(0);
  const [runs, setRuns] = useState<RunSummary[]>([]);

  useEffect(() => {
    let active = true;
    setTickets(null);
    setError("");
    api.listTickets(sort)
      .then((data) => { if (active) setTickets(data); })
      .catch((e) => { if (active) setError(getErrorMessage(e)); });
    return () => { active = false; };
  }, [sort, reloadKey]);

  // Which tickets have a live run — shown as an "in progress" marker. Best-effort:
  // a failure here must never break the ticket list, so the error is swallowed.
  useEffect(() => {
    let active = true;
    api.listRuns().then((r) => { if (active) setRuns(r); }).catch(() => { /* optional */ });
    return () => { active = false; };
  }, [reloadKey]);

  const activeByTicket = useMemo(() => {
    const m = new Map<number, string>();
    for (const r of runs) if (!TERMINAL_RUN.has(r.status)) m.set(r.ticket_id, r.status);
    return m;
  }, [runs]);

  // Filtering is client-side over the already-fetched list — sort stays server-side.
  const filtered = useMemo(() => {
    if (!tickets) return null;
    const q = query.trim().toLowerCase();
    return tickets.filter((t) => {
      if (statusFilter !== "all" && t.status !== statusFilter) return false;
      if (priorityFilter !== "all" && t.priority !== priorityFilter) return false;
      if (!q) return true;
      return (
        String(t.id).includes(q) ||
        t.title.toLowerCase().includes(q) ||
        t.customer_name.toLowerCase().includes(q)
      );
    });
  }, [tickets, query, statusFilter, priorityFilter]);

  const total = tickets?.length ?? 0;
  const shown = filtered?.length ?? 0;
  const isFiltering = query.trim() !== "" || statusFilter !== "all" || priorityFilter !== "all";

  function clearFilters() {
    setQuery("");
    setStatusFilter("all");
    setPriorityFilter("all");
  }

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

      <div className="ticket-toolbar">
        <div className="search">
          <Search size={14} className="search-icon" />
          <input
            type="search"
            className="search-input"
            placeholder="Search id, title or customer…"
            aria-label="Search tickets"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button type="button" className="icon-btn search-clear" aria-label="Clear search" onClick={() => setQuery("")}>
              <X size={13} />
            </button>
          )}
        </div>
        <label className="sort">
          Status
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}>
            {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s === "all" ? "all" : s}</option>)}
          </select>
        </label>
        <label className="sort">
          Priority
          <select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value as typeof priorityFilter)}>
            {PRIORITY_OPTIONS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
      </div>

      {error && (
        <div>
          <p className="error">Could not load tickets: {error}</p>
          <button type="button" className="btn btn-ghost" style={{ width: "auto", marginTop: "0.5rem" }}
                  onClick={() => setReloadKey((k) => k + 1)}>
            Retry
          </button>
        </div>
      )}

      {!tickets && !error && (
        <div className="loading-row">
          <Loader2 size={15} className="spin" />
          Loading tickets…
        </div>
      )}

      {tickets && total === 0 && (
        <div className="empty-state">
          <p className="muted">No tickets currently assigned.</p>
        </div>
      )}

      {tickets && total > 0 && (
        <>
          {isFiltering && (
            <div className="result-count">
              {shown} of {total} {total === 1 ? "ticket" : "tickets"}
              <button type="button" className="link result-clear" onClick={clearFilters}>Clear filters</button>
            </div>
          )}

          {shown === 0 ? (
            <div className="empty-state">
              <p className="muted">No tickets match these filters.</p>
              <button type="button" className="btn btn-ghost" style={{ width: "auto", marginTop: "0.75rem" }} onClick={clearFilters}>
                Clear filters
              </button>
            </div>
          ) : (
            <ul className="ticket-list">
              {filtered?.map((t) => (
                <li key={t.id}>
                  <button type="button" className="ticket-row" onClick={() => onOpen(t.id)}>
                    <span className="ticket-id">#{t.id}</span>
                    <span className="ticket-title">
                      {t.title}
                      {activeByTicket.has(t.id) && (
                        <span className="ticket-live" title={`Run ${activeByTicket.get(t.id)}`}>
                          <span className="conn-dot conn-dot--live" />in progress
                        </span>
                      )}
                    </span>
                    <span className="ticket-customer">{t.customer_name}</span>
                    <span className={`pill pri-${t.priority}`}>{t.priority}</span>
                    <span className={`pill st-${t.status}`}>{t.status}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
