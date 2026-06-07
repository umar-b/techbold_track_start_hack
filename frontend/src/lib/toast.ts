/**
 * Minimal dependency-free toast store. A module singleton with a
 * useSyncExternalStore-compatible subscribe/snapshot pair, so the <Toaster/>
 * stays in sync with concurrent rendering without a context provider.
 */
export type ToastKind = "success" | "error" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

const EMPTY: Toast[] = [];
let toasts: Toast[] = EMPTY;
let nextId = 1;
const listeners = new Set<() => void>();

function emit(): void {
  for (const l of listeners) l();
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function getToasts(): Toast[] {
  return toasts;
}

export function dismissToast(id: number): void {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

const DEFAULT_TTL = 4000;

function push(kind: ToastKind, message: string, ttl = DEFAULT_TTL): number {
  const id = nextId++;
  toasts = [...toasts, { id, kind, message }];
  emit();
  if (ttl > 0) setTimeout(() => dismissToast(id), ttl);
  return id;
}

export const toast = {
  success: (message: string, ttl?: number) => push("success", message, ttl),
  error: (message: string, ttl?: number) => push("error", message, ttl),
  info: (message: string, ttl?: number) => push("info", message, ttl),
};
