import type { Risk } from "../types";

type Props = { risk: Risk | string };

export function RiskBadge({ risk }: Props) {
  const value = (risk ?? "").toString().toUpperCase();
  const variant =
    value === "SAFE" ? "badge-safe"
    : value === "GATED" ? "badge-gated"
    : value === "BLOCKED" ? "badge-blocked"
    : "badge-none";
  return <span className={`badge ${variant}`}>{value || "—"}</span>;
}
