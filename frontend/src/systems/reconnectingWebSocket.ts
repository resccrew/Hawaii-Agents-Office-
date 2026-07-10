"use client";

// Bugfix: none of the three WS call sites (observation, chat, task board)
// ever retried a dropped connection — a backend restart, network blip, or
// laptop sleep left the UI silently stuck on "disconnected" until the user
// manually re-clicked Connect (and the chat/task channels had no manual
// reconnect trigger at all). This wraps `new WebSocket` with exponential
// backoff and stops retrying only when the caller's own `close()` is
// called (an intentional disconnect, e.g. switching sessions) — not on
// every dropped connection, which is exactly the case this fixes.

const INITIAL_DELAY_MS = 500;
const MAX_DELAY_MS = 10000;

export interface ReconnectingSocketHandlers {
  onOpen?: () => void;
  onClose?: () => void;
  onMessage: (event: MessageEvent) => void;
}

export function connectWithRetry(url: string, handlers: ReconnectingSocketHandlers): () => void {
  let ws: WebSocket | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let delay = INITIAL_DELAY_MS;
  let stopped = false;

  const open = () => {
    if (stopped) return;
    ws = new WebSocket(url);

    ws.onopen = () => {
      delay = INITIAL_DELAY_MS; // reset backoff on a successful connection
      handlers.onOpen?.();
    };

    ws.onmessage = handlers.onMessage;

    ws.onclose = () => {
      handlers.onClose?.();
      if (stopped) return;
      retryTimer = setTimeout(open, delay);
      delay = Math.min(delay * 2, MAX_DELAY_MS);
    };

    ws.onerror = () => {
      ws?.close();
    };
  };

  open();

  return () => {
    stopped = true;
    if (retryTimer) clearTimeout(retryTimer);
    ws?.close();
  };
}
