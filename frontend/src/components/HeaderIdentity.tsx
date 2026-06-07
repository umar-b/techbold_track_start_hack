import { useEffect, useState } from "react";
import { UserRound } from "lucide-react";
import type { Me } from "../types";
import { api } from "../api";

/**
 * Shows the signed-in technician (and team) on the right of the app header.
 * Fetches /api/me once and renders nothing on failure — identity is a nicety,
 * never a blocker, so an ERP hiccup must not break the header.
 */
export function HeaderIdentity() {
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    let active = true;
    api.me().then((m) => { if (active) setMe(m); }).catch(() => { /* identity is optional */ });
    return () => { active = false; };
  }, []);

  if (!me) return null;
  const name = [me.firstname, me.lastname].filter(Boolean).join(" ");
  if (!name && !me.teamname) return null;

  return (
    <div className="header-identity">
      <UserRound size={14} />
      <span className="header-identity-name">{name || me.teamname}</span>
      {name && me.teamname && <span className="header-identity-team">{me.teamname}</span>}
    </div>
  );
}
