import type { NextConfig } from "next";

// NEXT_PUBLIC_STUDIO_OPS_TOKEN is a dev-only convenience (systems/apiAuth.ts):
// running `next dev` against a real backend outside the Tauri shell has no
// `invoke("get_api_token")` to call, so the token is read from this env var
// instead. It's baked into the JS bundle at build time, in plain text, for
// anyone to read — the packaged desktop app must never ship a build with it
// set, since that would mean the shared API token sits in every user's
// install of the app. Fail the production build loudly instead of shipping
// that silently.
if (process.env.NODE_ENV === "production" && process.env.NEXT_PUBLIC_STUDIO_OPS_TOKEN) {
  throw new Error(
    "NEXT_PUBLIC_STUDIO_OPS_TOKEN is set during a production build. This env var is a " +
      "dev-only fallback (see frontend/src/systems/apiAuth.ts) — a production/Tauri build " +
      "gets the token via the `get_api_token` Tauri command instead, and must not bake it " +
      "into the shipped JS bundle. Unset NEXT_PUBLIC_STUDIO_OPS_TOKEN before building.",
  );
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: 'export',
};

export default nextConfig;
