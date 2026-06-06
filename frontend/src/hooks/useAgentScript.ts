import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import type { ActivityDraft, Ticket } from '../types';

export type RiskLevel = 'SAFE' | 'GATED';
export type CmdStatus = 'running' | 'done' | 'pending' | 'approved' | 'rejected';
export type MsgKind = 'text' | 'command' | 'output' | 'status' | 'done';

export interface ChatMsg {
  id: string;
  role: 'agent' | 'system' | 'user';
  kind: MsgKind;
  text: string;
  command?: string;
  risk?: RiskLevel;
  cmdStatus?: CmdStatus;
  rationale?: string;
  ts: Date;
}

export interface PendingApproval {
  msgId: string;
  command: string;
  rationale: string;
}

type Action =
  | { type: 'ADD'; msg: ChatMsg }
  | { type: 'UPDATE'; id: string; patch: Partial<ChatMsg> };

function reducer(state: ChatMsg[], action: Action): ChatMsg[] {
  switch (action.type) {
    case 'ADD': return [...state, action.msg];
    case 'UPDATE': return state.map(m => m.id === action.id ? { ...m, ...action.patch } : m);
    default: return state;
  }
}

type PhaseEvent =
  | { delay: number; type: 'typing'; on: boolean }
  | { delay: number; type: 'status'; text: string }
  | { delay: number; type: 'agent'; text: string }
  | { delay: number; type: 'output'; text: string }
  | { delay: number; type: 'cmd_auto'; command: string; stdout: string }
  | { delay: number; type: 'cmd_gated'; command: string; rationale: string }
  | { delay: number; type: 'done'; text: string };

function buildScript(ticketId: number, ip: string, username: string): PhaseEvent[][] {
  if (ticketId === 7001) {
    return [
      // Phase 0: diagnostics + propose config fix
      [
        { delay: 400, type: 'status', text: `Connecting to ${ip}:22 as ${username}…` },
        { delay: 900, type: 'typing', on: true },
        { delay: 1700, type: 'typing', on: false },
        { delay: 0, type: 'agent', text: 'SSH connection established. Starting read-only diagnostics.' },
        {
          delay: 700, type: 'cmd_auto', command: 'systemctl status nginx',
          stdout: '● nginx.service - A high performance web server\n   Loaded: loaded (/lib/systemd/system/nginx.service; enabled)\n   Active: inactive (dead) since Fri 2026-06-06 09:41:17 UTC; 23min ago\n  Process: 12847 ExecStartPre=/usr/sbin/nginx -t (code=exited, status=1/FAILURE)',
        },
        { delay: 1000, type: 'typing', on: true },
        { delay: 1900, type: 'typing', on: false },
        { delay: 0, type: 'agent', text: 'Nginx service is stopped. Checking system logs to understand the cause.' },
        {
          delay: 600, type: 'cmd_auto',
          command: "journalctl -u nginx --since '30 minutes ago' | tail -20",
          stdout: 'Jun 06 09:41:17 vm-prod nginx[12847]: nginx: [emerg] invalid parameter "proxy_pass http://localhost:3001" in /etc/nginx/sites-enabled/app.conf:42\nJun 06 09:41:17 vm-prod systemd[1]: nginx.service: Control process exited, code=exited, status=1/FAILURE\nJun 06 09:41:17 vm-prod systemd[1]: Failed to start A high performance web server.',
        },
        { delay: 800, type: 'typing', on: true },
        { delay: 2100, type: 'typing', on: false },
        { delay: 0, type: 'agent', text: 'Root cause identified. The Nginx config references port 3001 for the Node.js upstream, but the application is running on port 3000. Verifying with nginx -t before proposing a fix.' },
        {
          delay: 600, type: 'cmd_auto', command: 'nginx -t',
          stdout: 'nginx: [emerg] invalid parameter "proxy_pass http://localhost:3001" in /etc/nginx/sites-enabled/app.conf:42\nnginx: configuration file /etc/nginx/nginx.conf test failed',
        },
        { delay: 700, type: 'typing', on: true },
        { delay: 1400, type: 'typing', on: false },
        { delay: 0, type: 'agent', text: 'Confirmed. Proposing a targeted fix to correct the proxy_pass port.' },
        {
          delay: 400, type: 'cmd_gated',
          command: "sed -i 's|proxy_pass http://localhost:3001;|proxy_pass http://localhost:3000;|' /etc/nginx/sites-enabled/app.conf",
          rationale: 'Updates the proxy_pass directive from port 3001 to 3000. No other settings are modified. Fully reversible — swap the ports back to undo.',
        },
      ],
      // Phase 1: after config fix — propose restart
      [
        { delay: 300, type: 'output', text: '(sed succeeded — no output)' },
        { delay: 500, type: 'typing', on: true },
        { delay: 1200, type: 'typing', on: false },
        { delay: 0, type: 'agent', text: 'Config updated. Now restarting Nginx to apply the change.' },
        {
          delay: 400, type: 'cmd_gated',
          command: 'systemctl restart nginx',
          rationale: 'Restarts the Nginx service to load the corrected configuration. The service was already stopped, so this creates no additional downtime.',
        },
      ],
      // Phase 2: validate + done
      [
        { delay: 300, type: 'output', text: '(nginx restarted successfully)' },
        { delay: 500, type: 'typing', on: true },
        { delay: 1100, type: 'typing', on: false },
        { delay: 0, type: 'agent', text: 'Validating that the service is active and serving traffic.' },
        { delay: 500, type: 'cmd_auto', command: 'systemctl is-active nginx', stdout: 'active' },
        {
          delay: 600, type: 'cmd_auto', command: 'curl -sI http://localhost | head -5',
          stdout: 'HTTP/1.1 200 OK\nServer: nginx/1.18.0 (Ubuntu)\nDate: Fri, 06 Jun 2026 10:04:33 GMT\nContent-Type: text/html; charset=UTF-8\nContent-Length: 612',
        },
        { delay: 800, type: 'typing', on: true },
        { delay: 1700, type: 'typing', on: false },
        {
          delay: 0, type: 'done',
          text: "Fix validated. Nginx is active and returning HTTP 200. The customer's web application is accessible. Activity draft is ready for your review.",
        },
      ],
    ];
  }

  // Generic script for other tickets
  return [
    [
      { delay: 400, type: 'status', text: `Connecting to ${ip}:22 as ${username}…` },
      { delay: 800, type: 'typing', on: true },
      { delay: 1600, type: 'typing', on: false },
      { delay: 0, type: 'agent', text: 'SSH connection established. Running read-only diagnostics.' },
      {
        delay: 700, type: 'cmd_auto', command: 'uptime && df -h / && free -h',
        stdout: ' 10:04:33 up 14 days,  2:31,  1 user,  load average: 0.12, 0.08, 0.05\nFilesystem      Size  Used Avail Use% Mounted on\n/dev/sda1        50G   38G   12G  77% /\n               total        used        free\nMem:           7.7Gi       2.1Gi       5.6Gi',
      },
      { delay: 700, type: 'typing', on: true },
      { delay: 2000, type: 'typing', on: false },
      { delay: 0, type: 'agent', text: 'System is online. Analysing the reported issue in detail.' },
      {
        delay: 500, type: 'cmd_gated', command: 'journalctl -p err -n 50 --no-pager',
        rationale: 'Reads the last 50 error-level log entries to identify the root cause. Read-only operation.',
      },
    ],
    [
      {
        delay: 600, type: 'cmd_auto', command: 'systemctl --failed',
        stdout: '  UNIT                  LOAD   ACTIVE SUB    DESCRIPTION\n0 loaded units listed.',
      },
      { delay: 700, type: 'typing', on: true },
      { delay: 1800, type: 'typing', on: false },
      { delay: 0, type: 'done', text: 'Diagnostics complete. No critical failures detected. Activity draft is ready for your review.' },
    ],
  ];
}

export function buildMockActivityDraft(ticket: Ticket): ActivityDraft {
  if (ticket.id === 7001) {
    return {
      summary: 'Restored Nginx web server — corrected proxy_pass port mismatch in Nginx configuration.',
      root_cause: 'The Nginx reverse proxy configuration at /etc/nginx/sites-enabled/app.conf referenced port 3001 for the Node.js upstream. The Node.js application was running on port 3000, causing Nginx to fail startup with an "invalid parameter" error.',
      actions_taken:
        '1. Connected to vm-prod via SSH\n2. Confirmed nginx.service was inactive (dead)\n3. Inspected journalctl logs — identified invalid proxy_pass parameter on line 42\n4. Confirmed syntax error with nginx -t\n5. Corrected proxy_pass port from 3001 to 3000 via sed\n6. Restarted nginx service\n7. Validated service active and HTTP 200 response',
      commands_summary:
        'systemctl status nginx\njournalctl -u nginx --since \'30 minutes ago\' | tail -20\nnginx -t\nsed -i \'s|proxy_pass http://localhost:3001;|proxy_pass http://localhost:3000;|\' /etc/nginx/sites-enabled/app.conf\nsystemctl restart nginx\nsystemctl is-active nginx\ncurl -sI http://localhost | head -5',
      validation_result:
        'systemctl is-active nginx → active\ncurl -sI http://localhost → HTTP/1.1 200 OK\nCustomer\'s web application is accessible.',
    };
  }
  return {
    summary: 'Completed system diagnostics and resolved reported issue.',
    root_cause: 'Identified via remote diagnostic session. See commands summary for details.',
    actions_taken: 'Connected via SSH, ran read-only diagnostics, identified and resolved the issue.',
    commands_summary: 'uptime && df -h / && free -h\njournalctl -p err -n 50 --no-pager\nsystemctl --failed',
    validation_result: 'No critical failures detected. System operating normally.',
  };
}

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

export function useAgentScript(ticketId: number, ip: string, username: string) {
  const [msgs, dispatch] = useReducer(reducer, []);
  const [isTyping, setIsTyping] = useState(false);
  const [pending, setPending] = useState<PendingApproval | null>(null);
  const [agentDone, setAgentDone] = useState(false);

  const phaseRef = useRef(0);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const cancelRef = useRef(false);

  const addMsg = useCallback((msg: Omit<ChatMsg, 'id' | 'ts'>): string => {
    const id = uid();
    dispatch({ type: 'ADD', msg: { ...msg, id, ts: new Date() } });
    return id;
  }, []);

  const updateMsg = useCallback((id: string, patch: Partial<ChatMsg>) => {
    dispatch({ type: 'UPDATE', id, patch });
  }, []);

  function clearTimers() {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  }

  const runPhase = useCallback((phaseIdx: number) => {
    const script = buildScript(ticketId, ip, username);
    const phase = script[phaseIdx];
    if (!phase) return;

    let cumDelay = 0;

    for (const ev of phase) {
      cumDelay += ev.delay;
      const at = cumDelay;

      const t = setTimeout(() => {
        if (cancelRef.current) return;

        if (ev.type === 'typing') { setIsTyping(ev.on); return; }
        if (ev.type === 'status') { addMsg({ role: 'system', kind: 'status', text: ev.text }); return; }
        if (ev.type === 'agent') { addMsg({ role: 'agent', kind: 'text', text: ev.text }); return; }
        if (ev.type === 'output') { addMsg({ role: 'system', kind: 'output', text: ev.text }); return; }

        if (ev.type === 'cmd_auto') {
          const id = addMsg({
            role: 'agent', kind: 'command', text: ev.command,
            command: ev.command, risk: 'SAFE', cmdStatus: 'running',
          });
          setTimeout(() => {
            if (cancelRef.current) return;
            updateMsg(id, { cmdStatus: 'done' });
            addMsg({ role: 'system', kind: 'output', text: ev.stdout });
          }, 700);
          return;
        }

        if (ev.type === 'cmd_gated') {
          setIsTyping(false);
          const id = addMsg({
            role: 'agent', kind: 'command', text: ev.command,
            command: ev.command, risk: 'GATED', cmdStatus: 'pending', rationale: ev.rationale,
          });
          setPending({ msgId: id, command: ev.command, rationale: ev.rationale });
          return;
        }

        if (ev.type === 'done') {
          addMsg({ role: 'agent', kind: 'done', text: ev.text });
          setAgentDone(true);
        }
      }, at);

      timersRef.current.push(t);
      if (ev.type === 'cmd_gated') break;
    }
  }, [ticketId, ip, username, addMsg, updateMsg]);

  useEffect(() => {
    cancelRef.current = false;
    runPhase(0);
    return () => {
      cancelRef.current = true;
      clearTimers();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runPhase]);

  function approve() {
    if (!pending) return;
    updateMsg(pending.msgId, { cmdStatus: 'approved' });
    setPending(null);
    phaseRef.current += 1;
    clearTimers();
    setTimeout(() => { if (!cancelRef.current) runPhase(phaseRef.current); }, 200);
  }

  function reject() {
    if (!pending) return;
    updateMsg(pending.msgId, { cmdStatus: 'rejected' });
    addMsg({ role: 'system', kind: 'status', text: 'Command rejected by technician. Agent stopped.' });
    setPending(null);
  }

  function sendUserMsg(text: string) {
    addMsg({ role: 'user', kind: 'text', text });
  }

  return { msgs, isTyping, pending, agentDone, approve, reject, sendUserMsg };
}
