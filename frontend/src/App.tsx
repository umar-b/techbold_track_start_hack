import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { Run } from "./types";
import { TicketList } from "./components/TicketList";
import { TicketDetail } from "./components/TicketDetail";
import { RunView } from "./components/RunView";
import { ActivityReview } from "./components/ActivityReview";

type ViewName = "list" | "detail" | "run" | "activity";
type View =
  | { name: "list" }
  | { name: "detail"; ticketId: number }
  | { name: "run"; run: Run }
  | { name: "activity"; runId: string };

const DEPTH: Record<ViewName, number> = {
  list: 0,
  detail: 1,
  run: 2,
  activity: 3,
};

const variants = {
  enter: (dir: number) => ({
    x: dir > 0 ? 32 : -32,
    opacity: 0,
  }),
  center: {
    x: 0,
    opacity: 1,
    transition: { duration: 0.2, ease: "easeOut" as const },
  },
  exit: (dir: number) => ({
    x: dir > 0 ? -32 : 32,
    opacity: 0,
    transition: { duration: 0.15, ease: "easeIn" as const },
  }),
};

export default function App() {
  const [view, setView] = useState<View>({ name: "list" });
  const [prevDepth, setPrevDepth] = useState(0);

  function navigate(next: View) {
    setPrevDepth(DEPTH[view.name]);
    setView(next);
  }

  const dir = DEPTH[view.name] - prevDepth;

  return (
    <div>
      <header className="app-header">
        <div className="brand">
          <span className="brand-name">techbold</span>
          <span className="brand-dot">·</span>
          <span className="brand-product">Service Desk Autopilot</span>
        </div>
      </header>

      <main className="app-main">
        <AnimatePresence mode="wait" custom={dir}>
          <motion.div
            key={view.name}
            custom={dir}
            variants={variants}
            initial="enter"
            animate="center"
            exit="exit"
          >
            {view.name === "list" && (
              <TicketList
                onOpen={(ticketId) => navigate({ name: "detail", ticketId })}
              />
            )}
            {view.name === "detail" && (
              <TicketDetail
                ticketId={view.ticketId}
                onBack={() => navigate({ name: "list" })}
                onStarted={(run) => navigate({ name: "run", run })}
              />
            )}
            {view.name === "run" && (
              <RunView
                initialRun={view.run}
                onExit={() => navigate({ name: "list" })}
                onActivity={(runId) => navigate({ name: "activity", runId })}
              />
            )}
            {view.name === "activity" && (
              <ActivityReview
                runId={view.runId}
                onDone={() => navigate({ name: "list" })}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
