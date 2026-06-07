import { useState } from "react";
import { AnimatePresence, motion, MotionConfig } from "motion/react";
import { Ticket as TicketIcon, History, Brain } from "lucide-react";
import type { CustomerSystem, Ticket } from "./types";
import { TicketList } from "./components/TicketList";
import { TicketDetail } from "./components/TicketDetail";
import { ActivityReview } from "./components/ActivityReview";
import { AgentChatView } from "./components/AgentChatView";
import { RunHistory } from "./components/RunHistory";
import { MemoryBrowser } from "./components/MemoryBrowser";
import { Toaster } from "./components/Toaster";
import { HeaderIdentity } from "./components/HeaderIdentity";

type ViewName = "list" | "detail" | "chat" | "activity" | "runs" | "memory";
type View =
  | { name: "list" }
  | { name: "detail"; ticketId: number }
  | { name: "chat"; ticket: Ticket; system: CustomerSystem }
  | { name: "activity"; runId?: string }
  | { name: "runs" }
  | { name: "memory" };

// Top-level sections (list/runs/memory) share depth 0; ticket flow nests deeper.
const DEPTH: Record<ViewName, number> = {
  list: 0,
  runs: 0,
  memory: 0,
  detail: 1,
  chat: 2,
  activity: 3,
};

// Which nav tab is highlighted for a given view.
const SECTION: Record<ViewName, "tickets" | "runs" | "memory"> = {
  list: "tickets",
  detail: "tickets",
  chat: "tickets",
  activity: "tickets",
  runs: "runs",
  memory: "memory",
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
  const isChat = view.name === "chat";
  const section = SECTION[view.name];

  return (
    // reducedMotion="user" makes every motion/react animation honour the OS
    // prefers-reduced-motion setting (transforms collapse, opacity stays) —
    // PRODUCT.md requires reduced motion for all state-transition animations,
    // and the global CSS rule only covers CSS animations, not motion's JS ones.
    <MotionConfig reducedMotion="user">
    <div style={{ overflowX: "hidden" }}>
      <Toaster />
      <header className="app-header">
        <div className="brand">
          <span className="brand-name">techbold</span>
          <span className="brand-dot">·</span>
          <span className="brand-product">Service Desk Autopilot</span>
        </div>
        <nav className="app-nav" aria-label="Primary">
          <button type="button" className={`nav-tab${section === "tickets" ? " is-active" : ""}`}
                  aria-current={section === "tickets"} onClick={() => navigate({ name: "list" })}>
            <TicketIcon size={13} />Tickets
          </button>
          <button type="button" className={`nav-tab${section === "runs" ? " is-active" : ""}`}
                  aria-current={section === "runs"} onClick={() => navigate({ name: "runs" })}>
            <History size={13} />Runs
          </button>
          <button type="button" className={`nav-tab${section === "memory" ? " is-active" : ""}`}
                  aria-current={section === "memory"} onClick={() => navigate({ name: "memory" })}>
            <Brain size={13} />Memory
          </button>
        </nav>
        <HeaderIdentity />
      </header>

      <AnimatePresence mode="wait" custom={dir}>
        <motion.div
          key={view.name}
          custom={dir}
          variants={variants}
          initial="enter"
          animate="center"
          exit="exit"
        >
          {isChat && view.name === "chat" ? (
            <AgentChatView
              ticket={view.ticket}
              system={view.system}
              onExit={() => navigate({ name: "list" })}
              onActivity={(runId) => navigate({ name: "activity", runId })}
            />
          ) : (
            <main className="app-main">
              {view.name === "list" && (
                <TicketList
                  onOpen={(ticketId) => navigate({ name: "detail", ticketId })}
                />
              )}
              {view.name === "detail" && (
                <TicketDetail
                  ticketId={view.ticketId}
                  onBack={() => navigate({ name: "list" })}
                  onStartChat={(ticket, system) => navigate({ name: "chat", ticket, system })}
                />
              )}
              {view.name === "runs" && (
                <RunHistory onOpenTicket={(ticketId) => navigate({ name: "detail", ticketId })} />
              )}
              {view.name === "memory" && <MemoryBrowser />}
              {view.name === "activity" && (
                <ActivityReview
                  runId={view.runId}
                  onDone={() => navigate({ name: "list" })}
                />
              )}
            </main>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
    </MotionConfig>
  );
}
