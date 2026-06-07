import { useEffect, useState } from "react";
import { ScrollText, ChevronDown, ChevronRight, Download } from "lucide-react";
import type { AuditEntry } from "../types";
import { api, getErrorMessage } from "../api";

type Props = {
  runId: string;
  /** Bumping this (e.g. the run status) refetches while the panel is open. */
  refreshKey: string;
};

/**
 * Collapsible view of a run's append-only, already-redacted audit trail
 * (PRODUCT.md principle 5: "Audit is always present"). Fetches lazily on
 * expand and refetches when refreshKey changes, so it never polls in the
 * background.
 */
export function AuditTrail({ runId, refreshKey }: Props) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    let active = true;
    api.auditTrail(runId)
      .then((d) => { if (active) setEntries(d.entries); })
      .catch((e) => { if (active) setError(getErrorMessage(e)); });
    return () => { active = false; };
  }, [open, runId, refreshKey]);

  function downloadJson() {
    if (!entries) return;
    const blob = new Blob([JSON.stringify({ run_id: runId, entries }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-${runId}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="audit">
      <button type="button" className="audit-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <ScrollText size={12} />
        <span>Audit trail</span>
        {entries && <span className="audit-count">{entries.length}</span>}
      </button>
      {open && (
        <div className="audit-body">
          {entries && entries.length > 0 && (
            <button type="button" className="link audit-download" onClick={downloadJson}>
              <Download size={11} /> Download JSON
            </button>
          )}
          {error && <p className="error">{error}</p>}
          {!entries && !error && <p className="muted">Loading…</p>}
          {entries && entries.length === 0 && <p className="muted">No events yet.</p>}
          {entries && entries.length > 0 && (
            <ol className="audit-list">
              {entries.map((e, i) => <AuditRow key={i} entry={e} />)}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

function AuditRow({ entry }: { entry: AuditEntry }) {
  const { ts, event, ...rest } = entry;
  let time = ts;
  try {
    time = new Date(ts).toLocaleTimeString();
  } catch {
    /* keep the raw value if it isn't a parseable date */
  }
  const detail = Object.entries(rest)
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join("  ");
  return (
    <li className="audit-row">
      <span className="audit-time mono">{time}</span>
      <span className="audit-event">{event}</span>
      {detail && <span className="audit-detail">{detail}</span>}
    </li>
  );
}
