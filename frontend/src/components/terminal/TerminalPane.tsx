"use client";

import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { getHttpBase, getWsBase } from "@/systems/backendUrl";
import { connectWithRetry } from "@/systems/reconnectingWebSocket";

interface Props {
  paneId: string;
}

// One PTY-backed terminal pane — mounts an xterm.js instance, streams raw
// bytes to/from /ws/terminal/{paneId}. Unlike ChatWindow, there's no
// message list to render: xterm owns the whole surface, we just pipe bytes
// through it in both directions.
//
// Bugfix: this used to treat the WS's own `onClose` as "the PTY process
// exited" and auto-deleted the pane — but `onClose` fires on ANY transport
// close, including React StrictMode's dev-mode double-effect (mount →
// cleanup → mount) and ordinary unmounts, so navigating away (or just dev
// mode) killed the backend process out from under a still-alive pane. A
// closed WS means "disconnected, will reconnect" (connectWithRetry already
// handles that) — it says nothing about whether the process itself is
// still running. There's no such signal from the transport layer, so
// ending a pane is a manual action only (see the close button next to the
// terminal view in page.tsx) until a real exit signal is added.
export function TerminalPane({ paneId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const term = new Terminal({
      convertEol: true,
      fontFamily: "var(--font-mono, monospace)",
      fontSize: 13,
      theme: { background: "#0e0819" },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    fit.fit();
    termRef.current = term;

    // Binary, not JSON — the WS payload is raw PTY bytes in both
    // directions, so the browser's default `binaryType: "blob"` needs an
    // async hop through Blob.arrayBuffer() before xterm can write it.
    const socket = connectWithRetry(
      `${getWsBase()}/ws/terminal/${paneId}`,
      {
        onMessage: (event: MessageEvent) => {
          if (event.data instanceof Blob) {
            void event.data.arrayBuffer().then((buf) => term.write(new Uint8Array(buf)));
          } else if (event.data instanceof ArrayBuffer) {
            term.write(new Uint8Array(event.data));
          }
        },
      },
      { binaryType: "arraybuffer" },
    );

    const dataDisposable = term.onData((data: string) => {
      socket.send(new TextEncoder().encode(data));
    });

    const resizeObserver = new ResizeObserver(() => {
      fit.fit();
      const { rows, cols } = term;
      void fetch(`${getHttpBase()}/api/v1/terminal/${paneId}/resize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows, cols }),
      }).catch(() => {});
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      dataDisposable.dispose();
      socket();
      term.dispose();
      termRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- paneId is the only thing that should re-run this
  }, [paneId]);

  return <div ref={containerRef} className="terminal-pane" />;
}
