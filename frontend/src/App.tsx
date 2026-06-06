import { useState } from "react";
import type { Run } from "./types";
import { TicketList } from "./components/TicketList";
import { TicketDetail } from "./components/TicketDetail";
import { RunView } from "./components/RunView";
import { ActivityReview } from "./components/ActivityReview";

type View =
  | { name: "list" }
  | { name: "detail"; ticketId: number }
  | { name: "run"; run: Run }
  | { name: "activity"; runId: string };

export default function App() {
  const [view, setView] = useState<View>({ name: "list" });

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          Service Desk <strong>Autopilot</strong>
        </div>
        <span className="brand-sub">techbold · technician console</span>
      </header>
      <main className="app-main">
        {view.name === "list" && (
          <TicketList onOpen={(ticketId) => setView({ name: "detail", ticketId })} />
        )}
        {view.name === "detail" && (
          <TicketDetail
            ticketId={view.ticketId}
            onBack={() => setView({ name: "list" })}
            onStarted={(run) => setView({ name: "run", run })}
          />
        )}
        {view.name === "run" && (
          <RunView
            initialRun={view.run}
            onExit={() => setView({ name: "list" })}
            onActivity={(runId) => setView({ name: "activity", runId })}
          />
        )}
        {view.name === "activity" && (
          <ActivityReview runId={view.runId} onDone={() => setView({ name: "list" })} />
        )}
      </main>
    </div>
  );
}
