/** Formatting helpers shared across the workspace. Pure, no React. */

/**
 * Human-readable command duration. Sub-second stays in ms (`142 ms`); a second
 * or more switches to seconds with one decimal (`1.4 s`). Null/negative → "".
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || ms < 0) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** Compact relative time ("just now", "5m ago", "3h ago", "2d ago"); falls back
 * to the locale date past a week, or the raw string if it isn't a valid date. */
export function formatRelative(iso: string | undefined): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  const min = Math.floor(diff / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Date(t).toLocaleDateString();
}

/**
 * Some resolution fields arrive from the ERP as the *string form* of a list
 * (`"['systemctl restart nginx', 'systemctl status nginx']"`), which would
 * otherwise render with its brackets and quotes showing. Detect that shape and
 * recover the items so the UI can show a clean list; return null when the value
 * is ordinary prose. Tolerant of both JSON (double-quoted) and Python-repr
 * (single-quoted) arrays, and of commas inside the items themselves.
 */
export function parseListish(value: string): string[] | null {
  const s = value.trim();
  if (!(s.startsWith("[") && s.endsWith("]"))) return null;
  try {
    const parsed = JSON.parse(s);
    if (Array.isArray(parsed)) {
      const items = parsed.map((v) => String(v).trim()).filter(Boolean);
      return items.length ? items : null;
    }
  } catch {
    /* not valid JSON — fall through to quoted-literal extraction */
  }
  const items: string[] = [];
  const re = /'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    const raw = m[1] ?? m[2] ?? "";
    const unescaped = raw.replace(/\\(['"\\])/g, "$1").trim();
    if (unescaped) items.push(unescaped);
  }
  return items.length ? items : null;
}

/** Elapsed wall-clock as `m:ss` (or `h:mm:ss` past an hour). Negative → "0:00". */
export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  const mm = hrs > 0 ? String(mins).padStart(2, "0") : String(mins);
  const ss = String(secs).padStart(2, "0");
  return hrs > 0 ? `${hrs}:${mm}:${ss}` : `${mm}:${ss}`;
}
