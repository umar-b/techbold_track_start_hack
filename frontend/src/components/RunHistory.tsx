import { useEffect, useMemo, useState } from "react";
import { Loader2, History } from "lucide-react";
import type { RunSummary, Stats, Ticket } from "../types";
import { api, getErrorMessage } from "../api";
import { formatRelative } from "../lib/format";

type Props = { onOpenTicket: (ticketId: number) => void };

const TERMINAL_RUN = new Set(["finished", "aborted", "escalated"]);

/** Operations view over /api/runs + /api/stats: a status summary and a list of
 * every run this process knows about. Clicking a run opens its ticket (resumes
 * if still active). Read-only. */
export function RunHistory({ onOpenTicket }: Props) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [titles, setTitles] = useState<Map<number, string>>(new Map());
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    // Only the run list is essential; stats + titles are enrichment, so a failure
    // in either must not blank the whole view (e.g. an older backend without /api/stats).
    Promise.all([
      api.listRuns(),
      api.stats().catch(() => null),
      api.listTickets().catch(() => [] as Ticket[]),
    ])
      .then(([r, s, tickets]) => {
        if (!active) return;
        setRuns([...r].sort((a, b) => b.created_at.localeCompare(a.created_at)));
        if (s) setStats(s);
        setTitles(new Map(tickets.map((t) => [t.id, t.title])));
      })
      .catch((e) => { if (active) setError(getErrorMessage(e)); });
    return () => { active = false; };
  }, []);

  const activeCount = useMemo(
    () => (runs ?? []).filter((r) => !TERMINAL_RUN.has(r.status)).length,
    [runs],
  );

  return (
    <section className="panel">
      <div className="panel-head">
        <h1><History size={18} style={{ verticalAlign: "-3px", marginRight: "0.5rem" }} />Run history</h1>
      </div>

      {error && <p className="error">{error}</p>}

      {stats && (
        <div className="stat-strip">
          <Stat label="Total runs" value={stats.total} />
          <Stat label="Active" value={activeCount} accent={activeCount > 0} />
          <Stat label="Live sessions" value={stats.active_sessions} />
        </div>
      )}

      {!runs && !error && (
        <div className="loading-row"><Loader2 size={15} className="spin" /> Loading runs…</div>
      )}

      {runs && runs.length === 0 && (
        <div className="empty-state"><p className="muted">No runs yet. Start one from a ticket.</p></div>
      )}

      {runs && runs.length > 0 && (
        <ul className="ticket-list">
          {runs.map((r) => {
            const active = !TERMINAL_RUN.has(r.status);
            return (
              <li key={r.id}>
                <button type="button" className="ticket-row run-row" onClick={() => onOpenTicket(r.ticket_id)}>
                  <span className="ticket-id">#{r.ticket_id}</span>
                  <span className="ticket-title">
                    {titles.get(r.ticket_id) ?? `Ticket ${r.ticket_id}`}
                    {active && <span className="ticket-live"><span className="conn-dot conn-dot--live" />live</span>}
                  </span>
                  <span className="muted run-steps">{r.steps} step{r.steps === 1 ? "" : "s"}</span>
                  <span className={`pill st-run-${r.status}`}>{r.status.replace(/_/g, " ")}</span>
                  <span className="muted run-time">{formatRelative(r.created_at)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className={`stat${accent ? " stat--accent" : ""}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}
