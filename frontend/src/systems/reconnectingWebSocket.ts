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

// A plain disposer for every existing caller (observation/chat/task board:
// call it, forget it) that also carries a `.send` — the terminal channel is
// the first caller that needs to push data back over the *same* socket
// instead of via REST, so this needed to grow a send path rather than stay
// receive-only. Attaching it to the disposer function (not changing the
// return type to an object) keeps every existing `useRef<() => void>` call
// site compiling unchanged — TS only checks the call signature matches for
// a non-literal assignment, extra properties on the source are fine.
export interface ReconnectingSocket {
  (): void;
  send: (data: string | ArrayBufferLike | Blob | ArrayBufferView) => void;
}

// A plain string for callers that don't need auth, or a factory resolved
// fresh on every (re)connect attempt — needed because the auth token (see
// apiAuth.ts) may not be available yet on the very first connect (Tauri's
// invoke bridge is async); resolving it per-attempt means a retry after the
// token becomes available picks it up, instead of a closure permanently
// capturing whatever the URL was (or wasn't) at the first call.
type UrlSource = string | (() => string | Promise<string>);

export function connectWithRetry(
  url: UrlSource,
  handlers: ReconnectingSocketHandlers,
  opts?: { binaryType?: BinaryType },
): ReconnectingSocket {
  let ws: WebSocket | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let delay = INITIAL_DELAY_MS;
  let stopped = false;

  const open = () => {
    if (stopped) return;
    Promise.resolve(typeof url === "function" ? url() : url).then((resolvedUrl) => {
      if (stopped) return;
      ws = new WebSocket(resolvedUrl);
      if (opts?.binaryType) ws.binaryType = opts.binaryType;

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
    });
  };

  open();

  const close = (() => {
    stopped = true;
    if (retryTimer) clearTimeout(retryTimer);
    ws?.close();
  }) as ReconnectingSocket;

  close.send = (data) => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(data);
  };

  return close;
}
