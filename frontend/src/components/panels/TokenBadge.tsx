"use client";

import { useEffect } from "react";
import {
  useAgentTokensStore,
  selectAgentTokens,
  startAgentTokensPolling,
} from "@/stores/agentTokensStore";

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

// Compact cost/usage badge for an agent-card in SidePanel's roster — real
// numbers accumulated backend-side from every hook event's
// input_tokens/output_tokens/cache_*_tokens (see events.py, agent_registry.py),
// not an estimate. Icon + total in/out at a glance; hover/focus for the
// cache-hit split via a native title tooltip.
export function TokenBadge({ agentId }: { agentId: string }) {
  useEffect(() => startAgentTokensPolling(), []);
  const stats = useAgentTokensStore(selectAgentTokens(agentId));

  if (!stats) return null;
  const { inputTokens, outputTokens, cacheReadTokens, cacheCreationTokens } = stats;
  const total = inputTokens + outputTokens + cacheReadTokens + cacheCreationTokens;
  if (total === 0) return null;

  const cacheTotal = cacheReadTokens + cacheCreationTokens;
  const cacheHitPct = cacheTotal > 0 ? Math.round((cacheReadTokens / cacheTotal) * 100) : null;

  const tooltip =
    `${inputTokens.toLocaleString()} input / ${outputTokens.toLocaleString()} output tokens\n` +
    `${cacheReadTokens.toLocaleString()} cache-read / ${cacheCreationTokens.toLocaleString()} cache-created` +
    (cacheHitPct !== null ? ` (${cacheHitPct}% cache-hit)` : "");

  return (
    <span className="token-badge" title={tooltip}>
      <span aria-hidden="true">🪙</span>
      <span className="sr-only">token usage: </span>
      {fmt(inputTokens)} in / {fmt(outputTokens)} out
    </span>
  );
}
