import { useEffect, useState } from "react";
import { Loader2, Brain, Link2 } from "lucide-react";
import type { MemoryNote } from "../types";
import { api, getErrorMessage } from "../api";
import { formatRelative } from "../lib/format";

/** Read-only view of the shared markdown-graph memory (ADR-0001): one card per
 * resolved incident, with tags, root cause, and links to related notes. */
export function MemoryBrowser() {
  const [notes, setNotes] = useState<MemoryNote[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.memoryNotes()
      .then((d) => { if (active) setNotes(d.notes); })
      .catch((e) => { if (active) setError(getErrorMessage(e)); });
    return () => { active = false; };
  }, []);

  return (
    <section className="panel">
      <div className="panel-head">
        <h1><Brain size={18} style={{ verticalAlign: "-3px", marginRight: "0.5rem" }} />Memory</h1>
        {notes && <span className="muted">{notes.length} resolved incident{notes.length === 1 ? "" : "s"}</span>}
      </div>
      <p className="muted" style={{ marginBottom: "1.25rem" }}>
        Every resolved incident leaves one sanitized note. New runs retrieve related notes as
        hypotheses to verify — never as actions to apply.
      </p>

      {error && <p className="error">{error}</p>}

      {!notes && !error && (
        <div className="loading-row"><Loader2 size={15} className="spin" /> Loading memory…</div>
      )}

      {notes && notes.length === 0 && (
        <div className="empty-state">
          <p className="muted">No memory yet. Notes accrue as incidents are resolved and submitted.</p>
        </div>
      )}

      {notes && notes.length > 0 && (
        <ul className="mem-list">
          {notes.map((n) => (
            <li key={n.id} className="mem-card">
              <div className="mem-card-head">
                <span className="mem-title">{n.title || n.id}</span>
                {n.created_at && <span className="muted mem-time">{formatRelative(n.created_at)}</span>}
              </div>
              {n.root_cause && <p className="mem-root">{n.root_cause}</p>}
              <div className="mem-tags">
                {n.os && <span className="tag mem-os">{n.os}</span>}
                {n.tags.map((t) => <span key={t} className="tag">{t}</span>)}
              </div>
              {n.links && n.links.length > 0 && (
                <div className="mem-links">
                  <Link2 size={11} />
                  {n.links.map((l) => <span key={l} className="mem-link">{l}</span>)}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
