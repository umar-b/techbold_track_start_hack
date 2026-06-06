import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ArrowLeft, Check, X, Loader2, Send, Terminal, Zap, ShieldAlert } from 'lucide-react';
import type { ActivityDraft, CustomerSystem, Ticket } from '../types';
import { useAgentScript, buildMockActivityDraft, type ChatMsg, type PendingApproval } from '../hooks/useAgentScript';

type Props = {
  ticket: Ticket;
  system: CustomerSystem;
  onExit: () => void;
  onActivity: (prefill: ActivityDraft) => void;
};

export function AgentChatView({ ticket, system, onExit, onActivity }: Props) {
  const sys = system.system;
  const { msgs, isTyping, pending, agentDone, approve, reject, sendUserMsg } = useAgentScript(
    ticket.id, sys.ip, sys.username,
  );
  const [inputVal, setInputVal] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [msgs.length, isTyping]);

  function handleSend() {
    const text = inputVal.trim();
    if (!text) return;
    sendUserMsg(text);
    setInputVal('');
  }

  function handleActivity() {
    onActivity(buildMockActivityDraft(ticket));
  }

  return (
    <div className="chat-layout">
      {/* Main chat column */}
      <div className="chat-main">
        <div className="chat-messages">
          <AnimatePresence initial={false}>
            {msgs.map((msg) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, ease: 'easeOut' }}
              >
                <MsgBubble msg={msg} onApprove={approve} onReject={reject} pending={pending} />
              </motion.div>
            ))}
          </AnimatePresence>

          {isTyping && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>

        {agentDone ? (
          <div className="chat-done-bar">
            <span className="chat-done-text">Incident resolved — activity draft ready</span>
            <button type="button" className="btn btn-gold chat-done-btn" onClick={handleActivity}>
              Review &amp; submit activity
            </button>
          </div>
        ) : (
          <div className="chat-input-bar">
            <input
              className="chat-input"
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder={pending ? 'Approve or reject the command above first…' : 'Add a note or instruction…'}
              disabled={!!pending}
            />
            <button
              type="button"
              className="btn btn-primary chat-send-btn"
              onClick={handleSend}
              disabled={!!pending || !inputVal.trim()}
            >
              <Send size={13} />
            </button>
          </div>
        )}
      </div>

      {/* Right sidebar: ticket info */}
      <aside className="chat-sidebar">
        <button type="button" className="link" style={{ marginBottom: '0.75rem' }} onClick={onExit}>
          <ArrowLeft size={13} /> All tickets
        </button>

        <div className="chat-side-ticket">
          <div className="chat-side-id">#{ticket.id}</div>
          <div className="chat-side-title">{ticket.title}</div>
          <div className="chat-side-meta">
            <span className={`pill pri-${ticket.priority}`}>{ticket.priority}</span>
            <span className={`pill st-${ticket.status}`}>{ticket.status}</span>
          </div>
          <div className="chat-side-customer">{ticket.customer_name}</div>
        </div>

        <div className="chat-side-divider" />

        <div className="chat-side-system">
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.6rem' }}>
            <Terminal size={11} />
            Customer system
          </h2>
          <dl className="chat-side-dl">
            <dt>Host</dt>
            <dd>{sys.ip}:{sys.port}</dd>
            <dt>User</dt>
            <dd>{sys.username}</dd>
            <dt>OS</dt>
            <dd style={{ fontFamily: 'var(--font-body)', fontSize: '0.8125rem', color: 'var(--ink-soft)' }}>{sys.os}</dd>
            {sys.notes && (
              <>
                <dt>Notes</dt>
                <dd style={{ fontFamily: 'var(--font-body)', fontSize: '0.8rem', color: 'var(--ink-soft)' }}>{sys.notes}</dd>
              </>
            )}
          </dl>
        </div>
      </aside>
    </div>
  );
}

function MsgBubble({
  msg, onApprove, onReject, pending,
}: {
  msg: ChatMsg;
  onApprove: () => void;
  onReject: () => void;
  pending: PendingApproval | null;
}) {
  if (msg.kind === 'status') {
    return <div className="chat-msg-status">{msg.text}</div>;
  }

  if (msg.role === 'user') {
    return (
      <div className="chat-msg-user-wrap">
        <div className="chat-bubble-user">{msg.text}</div>
      </div>
    );
  }

  if (msg.kind === 'output') {
    return (
      <div className="chat-output">
        <pre>{msg.text}</pre>
      </div>
    );
  }

  if (msg.kind === 'done') {
    return (
      <div className="chat-msg-done">
        <div className="chat-msg-done-icon">
          <Check size={14} />
        </div>
        <p>{msg.text}</p>
      </div>
    );
  }

  if (msg.kind === 'command') {
    return (
      <CmdBlock
        msg={msg}
        onApprove={onApprove}
        onReject={onReject}
        isPending={pending?.msgId === msg.id}
      />
    );
  }

  return (
    <div className="chat-msg-agent">
      <div className="chat-avatar">
        <Zap size={12} />
      </div>
      <div className="chat-bubble">{msg.text}</div>
    </div>
  );
}

function CmdBlock({
  msg, onApprove, onReject, isPending,
}: {
  msg: ChatMsg;
  onApprove: () => void;
  onReject: () => void;
  isPending: boolean;
}) {
  const status = msg.cmdStatus ?? 'running';
  const isGated = msg.risk === 'GATED';

  const statusClass =
    status === 'approved' || status === 'done' ? 'cmd-block--done'
    : status === 'rejected' ? 'cmd-block--rejected'
    : status === 'pending' ? 'cmd-block--pending'
    : '';

  return (
    <div className="chat-msg-agent chat-msg-cmd-wrap">
      <div className="chat-avatar chat-avatar--sm">
        <Terminal size={11} />
      </div>
      <div className={`cmd-block ${statusClass}`}>
        <div className="cmd-block-header">
          {isGated ? (
            <span className="badge badge-gated" style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <ShieldAlert size={10} />GATED
            </span>
          ) : (
            <span className="badge badge-safe">AUTO</span>
          )}
          {status === 'running' && <Loader2 size={12} className="spin" style={{ marginLeft: 'auto', color: 'var(--muted)' }} />}
          {(status === 'done' || status === 'approved') && <Check size={12} style={{ marginLeft: 'auto', color: 'var(--safe)' }} />}
          {status === 'rejected' && <X size={12} style={{ marginLeft: 'auto', color: 'var(--danger)' }} />}
        </div>
        <code className="cmd-block-code">{msg.command}</code>
        {msg.rationale && status === 'pending' && (
          <p className="cmd-block-rationale">{msg.rationale}</p>
        )}
        {isPending && status === 'pending' && (
          <div className="cmd-block-actions">
            <button type="button" className="btn btn-gold cmd-approve-btn" onClick={onApprove}>
              Approve
            </button>
            <button type="button" className="btn btn-danger" onClick={onReject}>
              Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="chat-msg-agent">
      <div className="chat-avatar">
        <Zap size={12} />
      </div>
      <div className="chat-typing">
        <span className="chat-typing-dot" />
        <span className="chat-typing-dot" />
        <span className="chat-typing-dot" />
      </div>
    </div>
  );
}
