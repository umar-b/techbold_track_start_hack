import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Loader2, Server, CircleCheck, ListChecks, Terminal, X } from "lucide-react";
import type { Activity, CustomerSystem, Ticket } from "../types";
import { api, getErrorMessage } from "../api";
import { formatRelative, parseListish } from "../lib/format";
import { CopyButton } from "./CopyButton";

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

// The narrative of the fix stays inline; the step-by-step actions and the raw
// commands are detail that belongs behind a "view detail" affordance, not dumped
// into the ticket header.
const NARRATIVE_FIELDS: { key: keyof Activity; label: string }[] = [
  { key: "summary", label: "Summary" },
  { key: "root_cause", label: "Root cause" },
  { key: "validation_result", label: "Validation" },
];

/** A resolution field that may arrive as prose or as a stringified list →
 * always a clean array of items (single-element when it was prose). */
function toItems(value: string | undefined): string[] {
  if (typeof value !== "string" || !value.trim()) return [];
  return parseListish(value) ?? [value.trim()];
}

function ResolutionPanel({ activity }: { activity: Activity }) {
  const [detailOpen, setDetailOpen] = useState(false);
  const rows = NARRATIVE_FIELDS.filter((f) => {
    const v = activity[f.key];
    return typeof v === "string" && v.trim();
  });
  const actions = toItems(activity.actions_taken);
  const commands = toItems(activity.commands_summary);
  const hasDetail = actions.length > 0 || commands.length > 0;

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
        {rows.map((f) => {
          const value = activity[f.key] as string;
          const list = parseListish(value);
          return (
            <div key={String(f.key)} className="resolution-row">
              <dt>{f.label}</dt>
              {list ? (
                <dd>
                  <ul className="resolution-items">
                    {list.map((item, i) => <li key={i}>{item}</li>)}
                  </ul>
                </dd>
              ) : (
                <dd>{value}</dd>
              )}
            </div>
          );
        })}
      </dl>

      {hasDetail && (
        <div className="resolution-foot">
          <button type="button" className="btn btn-ghost resolution-detail-btn" onClick={() => setDetailOpen(true)}>
            View actions &amp; commands
          </button>
          <span className="resolution-foot-meta">
            {actions.length > 0 && `${actions.length} action${actions.length === 1 ? "" : "s"}`}
            {actions.length > 0 && commands.length > 0 && " · "}
            {commands.length > 0 && `${commands.length} command${commands.length === 1 ? "" : "s"}`}
          </span>
        </div>
      )}

      <ResolutionDetailModal
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        solvedWhen={activity.end_datetime}
        actions={actions}
        commands={commands}
      />
    </div>
  );
}

function ResolutionDetailModal({
  open, onClose, solvedWhen, actions, commands,
}: {
  open: boolean;
  onClose: () => void;
  solvedWhen?: string;
  actions: string[];
  commands: string[];
}) {
  const ref = useRef<HTMLDialogElement>(null);

  // Drive the native <dialog> from React state so it gets the top-layer + focus
  // trap + Escape handling for free, without leaving the stacking context.
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    else if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="res-modal"
      onClose={onClose}
      onClick={(e) => { if (e.target === ref.current) onClose(); }}
    >
      <div className="res-modal-head">
        <span className="resolution-icon"><CircleCheck size={16} /></span>
        <div className="res-modal-titles">
          <h2 className="res-modal-title">Resolution detail</h2>
          {solvedWhen && <span className="res-modal-sub">solved {formatRelative(solvedWhen)}</span>}
        </div>
        <button type="button" className="icon-btn res-modal-close" aria-label="Close detail" onClick={onClose}>
          <X size={16} />
        </button>
      </div>

      <div className="res-modal-body">
        {actions.length > 0 && (
          <section className="res-section">
            <h3 className="res-section-title"><ListChecks size={13} /> Actions taken</h3>
            <ol className="res-actions">
              {actions.map((a, i) => (
                <li key={i}>
                  <span className="res-action-num">{i + 1}</span>
                  <span className="res-action-text">{a}</span>
                </li>
              ))}
            </ol>
          </section>
        )}

        {commands.length > 0 && (
          <section className="res-section">
            <h3 className="res-section-title">
              <Terminal size={13} /> Commands run
              <span className="res-section-count">{commands.length}</span>
            </h3>
            <ul className="res-commands">
              {commands.map((c, i) => (
                <li key={i}>
                  <code>{c}</code>
                  <CopyButton text={c} />
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </dialog>
  );
}
