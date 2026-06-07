import { useEffect, useState } from "react";

/**
 * Seconds elapsed since `startIso`, ticking once per second. When `frozen` is
 * true (a terminal run) it computes the value once and stops the interval, so
 * the timer holds at roughly the moment the run ended. No ref reads in render.
 */
export function useElapsed(startIso: string | undefined, frozen: boolean): number {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!startIso) return;
    const start = new Date(startIso).getTime();
    const tick = () => setElapsed(Math.max(0, (Date.now() - start) / 1000));
    tick();
    if (frozen) return; // capture once, do not keep ticking
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startIso, frozen]);

  return elapsed;
}
