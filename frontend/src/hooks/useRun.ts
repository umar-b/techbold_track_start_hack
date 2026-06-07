import { useCallback, useEffect, useRef, useState } from "react";
import type { PlanStepEdit, Run, Step } from "../types";
import { api, getErrorMessage, BASE } from "../api";

const TERMINAL = ["finished", "aborted", "escalated"];

/** Health of the live event stream, surfaced to the UI as a status dot. */
export type ConnectionState = "connecting" | "live" | "reconnecting" | "closed";

type SseMessage =
  | { type: "step"; step: Step }
  | { type: "status"; status: string }
  | { type: "plan"; plan: Run["plan"] };

function mergeStep(run: Run, step: Step): Run {
  const steps = [...run.steps];
  const i = steps.findIndex((s) => s.index === step.index);
  if (i >= 0) steps[i] = step;
  else steps.push(step);
  return { ...run, steps };
}

/**
 * Owns one real Run against the backend: starts it, streams step/status events
 * over SSE (live progress during the blocking execute phase), and exposes the
 * plan-level approval actions. The single adapter onto the small Run interface
 * (start / approve / reject / abort) — replaces the scripted mock.
 */
export function useRun(ticketId: number) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(true);
  const [acting, setActing] = useState(false);
  const [connection, setConnection] = useState<ConnectionState>("connecting");

  const mounted = useRef(true);
  const startedRef = useRef(false); // fire the start POST once, even under StrictMode double-mount
  const esRef = useRef<EventSource | null>(null);

  // Start the run once. POST /api/runs returns the run when analysis has
  // converged (awaiting_plan_approval) or terminated (finished/escalated).
  useEffect(() => {
    mounted.current = true;
    if (!startedRef.current) {
      startedRef.current = true;
      setStarting(true);
      api
        .startRun(ticketId)
        .then((r) => { if (mounted.current) setRun(r); })
        .catch((e) => { if (mounted.current) setError(getErrorMessage(e)); })
        .finally(() => { if (mounted.current) setStarting(false); });
    }
    return () => { mounted.current = false; };
  }, [ticketId]);

  // Open the SSE stream once a run id exists. It stays open across the approve
  // POST so fix/validate steps stream in as they execute. The browser auto-
  // reconnects on transient drops; we close on a terminal status or unmount.
  const runId = run?.id;
  useEffect(() => {
    if (!runId) return;
    // run.status here is the status from the render where the id first appeared.
    if (run && TERMINAL.includes(run.status)) return;
    const es = new EventSource(`${BASE}/api/runs/${runId}/events`);
    esRef.current = es;
    setConnection("connecting");
    es.onopen = () => { if (mounted.current) setConnection("live"); };
    // The browser auto-reconnects on a transient drop (readyState CONNECTING);
    // a CLOSED state means it gave up. Reflect both rather than killing the stream.
    es.onerror = () => {
      if (!mounted.current) return;
      setConnection(es.readyState === EventSource.CLOSED ? "closed" : "reconnecting");
    };
    es.onmessage = (ev: MessageEvent<string>) => {
      if (!mounted.current) return;
      let msg: SseMessage;
      try {
        msg = JSON.parse(ev.data) as SseMessage;
      } catch {
        return;
      }
      if (msg.type === "step") {
        setRun((prev) => (prev ? mergeStep(prev, msg.step) : prev));
      } else if (msg.type === "plan") {
        // The proposed plan is not carried by step events; the backend pushes it here.
        setRun((prev) => (prev ? { ...prev, plan: msg.plan } : prev));
      } else if (msg.type === "status") {
        setRun((prev) => (prev ? { ...prev, status: msg.status as Run["status"] } : prev));
        if (TERMINAL.includes(msg.status)) {
          es.close();
          setConnection("closed");
          if (esRef.current === es) esRef.current = null;
        }
      }
    };
    // No es.close() on error: let the browser's built-in EventSource reconnect
    // handle transient drops rather than killing the stream permanently.
    return () => {
      es.close();
      if (esRef.current === es) esRef.current = null;
    };
    // Keyed on runId only; the terminal-at-open check reads run.status once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const action = useCallback(async (fn: () => Promise<Run>) => {
    setActing(true);
    setError("");
    try {
      const r = await fn();
      if (!mounted.current) return;
      // The POST returns immediately (async backend); SSE owns steps/plan, so only adopt
      // the authoritative status here — never clobber SSE-streamed steps with the snapshot.
      setRun((prev) => {
        if (!prev) return r;
        if (TERMINAL.includes(prev.status)) return prev; // SSE may already be terminal
        return { ...prev, status: r.status };
      });
      if (TERMINAL.includes(r.status)) {
        esRef.current?.close();
        esRef.current = null;
        setConnection("closed");
      }
    } catch (e) {
      if (mounted.current) setError(getErrorMessage(e));
    } finally {
      if (mounted.current) setActing(false);
    }
  }, []);

  const approve = useCallback((editedSteps?: PlanStepEdit[]) => {
    if (run) void action(() => api.approve(run.id, editedSteps));
  }, [run, action]);

  const reject = useCallback(() => {
    if (run) void action(() => api.reject(run.id));
  }, [run, action]);

  const abort = useCallback(() => {
    if (run) void action(() => api.abort(run.id));
  }, [run, action]);

  return {
    run,
    steps: run?.steps ?? [],
    status: run?.status ?? "created",
    plan: run?.plan ?? null,
    error,
    starting,
    acting,
    connection,
    isAwaitingPlan: run?.status === "awaiting_plan_approval",
    isTerminal: !!run && TERMINAL.includes(run.status),
    approve,
    reject,
    abort,
  };
}
