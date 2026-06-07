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
