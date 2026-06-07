import { useCallback, useEffect, useRef, useState } from "react";
import type { PlanStepEdit, Run, Step } from "../types";
import { api, getErrorMessage, BASE } from "../api";
import { toast } from "../lib/toast";

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
  // Remembers which ticket we've already started/resumed for. Keying on the id
  // (not a bare boolean) fires once per StrictMode double-mount AND re-fires if
  // the same mounted component is handed a different ticketId.
  const startedForRef = useRef<number | null>(null);
  const esRef = useRef<EventSource | null>(null);

  // Start or RESUME the run once. If this ticket already has a live run (the
  // technician navigated away and back), adopt it instead of starting a second
  // one — the backend allows only one active run per ticket and would 409.
  // Otherwise POST /api/runs, which returns once analysis has converged
  // (awaiting_plan_approval) or terminated.
  useEffect(() => {
    mounted.current = true;
    if (startedForRef.current !== ticketId) {
      startedForRef.current = ticketId;
      setRun(null);       // a new ticket: drop any stale run before (re)loading
      setError("");
      setStarting(true);
      api
        .listRuns()
        .then((runs) => {
          const active = runs.find((r) => r.ticket_id === ticketId && !TERMINAL.includes(r.status));
          return active ? api.getRun(active.id) : api.startRun(ticketId);
        })
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
          if (mounted.current) setConnection("closed");
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

  const action = useCallback(async (fn: () => Promise<Run>, successMsg?: string) => {
    setActing(true);
    setError("");
    try {
      const r = await fn();
      if (successMsg) toast.success(successMsg);
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
      const msg = getErrorMessage(e);
      // Guard both: a stale action that rejects after unmount shouldn't surface
      // an out-of-context error toast for a run the technician already left.
      if (mounted.current) {
        setError(msg);
        toast.error(msg);
      }
    } finally {
      if (mounted.current) setActing(false);
    }
  }, []);

  const approve = useCallback((editedSteps?: PlanStepEdit[]) => {
    if (run) void action(() => api.approve(run.id, editedSteps),
      editedSteps?.length ? "Edited plan approved — applying the fix" : "Plan approved — applying the fix");
  }, [run, action]);

  const reject = useCallback((feedback?: string) => {
    if (run) void action(() => api.reject(run.id, feedback),
      feedback && feedback.trim()
        ? "Sent to the agent — revising the plan with your notes"
        : "Plan rejected — the agent is replanning");
  }, [run, action]);

  const abort = useCallback(() => {
    if (run) void action(() => api.abort(run.id), "Run aborted");
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
