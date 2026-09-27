"use client";

// Single source of truth for the shared backend API token (see
// backend/app/core/auth.py) — every REST call needs it as X-API-Key, every
// WebSocket needs it as a ?token= query param.
//
// Where the token comes from depends on how this frontend is running:
//   - Packaged/dev Tauri window: the Rust side owns the file
//     (~/.studio-ops/api-token) and exposes it back to the webview only
//     through the `get_api_token` command (src-tauri/src/lib.rs) — the
//     renderer's JS never reads the file directly.
//   - Plain browser dev session (`next dev`, no Tauri wrapper): there is no
//     invoke bridge, so the token instead comes from
//     NEXT_PUBLIC_STUDIO_OPS_TOKEN, baked in at build time. This is a dev-only
//     convenience, not a backend feature — there is deliberately no
//     "give me the token" HTTP endpoint, since an unauthenticated endpoint
//     that hands out the auth token would defeat the whole point of having one.
//
// Cached in a module-level variable (not localStorage/sessionStorage) so the
// token never touches persistent browser storage.
let cached: string | null = null;
let inflight: Promise<string> | null = null;

declare global {
  interface Window {
    __TAURI__?: { core?: { invoke: <T>(cmd: string, args?: Record<string, unknown>) => Promise<T> } };
  }
}

async function fetchToken(): Promise<string> {
  if (typeof window !== "undefined" && window.__TAURI__?.core) {
    try {
      return await window.__TAURI__.core.invoke<string>("get_api_token");
    } catch {
      return "";
    }
  }
  return process.env.NEXT_PUBLIC_STUDIO_OPS_TOKEN ?? "";
}

export async function getApiToken(): Promise<string> {
  if (cached !== null) return cached;
  if (!inflight) {
    inflight = fetchToken().then((t) => {
      cached = t;
      return t;
    });
  }
  return inflight;
}

/** Drop-in replacement for `fetch` against the studio-ops backend: awaits
 * the token once (cached after) and attaches it as X-API-Key. */
export async function authedFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = await getApiToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("X-API-Key", token);
  return fetch(input, { ...init, headers });
}

/** Appends the token to a WS URL as `?token=`/`&token=`. Awaited once by the
 * URL-factory passed into connectWithRetry (see reconnectingWebSocket.ts) —
 * resolved on every (re)connect attempt, not just the first, so a retry
 * that outlives the initial token fetch still picks it up. */
export async function wsUrlWithToken(url: string): Promise<string> {
  const token = await getApiToken();
  if (!token) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}
