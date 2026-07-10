// 8-directional A* over the office navigation grid — ported in spirit from
// claude-office's astar.ts (binary-heap priority queue over a tile grid),
// theme-agnostic. Deferred in Phase 2 (placeholder-Graphics visualization
// took priority); built now because the real office background has actual
// furniture agents need to walk around instead of through.

import { getWalkableGrid, stageToCell, cellToStage, GRID_W, GRID_H } from "./navigationGrid";

interface Node {
  gx: number;
  gy: number;
  g: number;
  f: number;
  parent: Node | null;
}

const NEIGHBORS: [number, number, number][] = [
  [1, 0, 1],
  [-1, 0, 1],
  [0, 1, 1],
  [0, -1, 1],
  [1, 1, Math.SQRT2],
  [1, -1, Math.SQRT2],
  [-1, 1, Math.SQRT2],
  [-1, -1, Math.SQRT2],
];

function heuristic(ax: number, ay: number, bx: number, by: number): number {
  return Math.hypot(ax - bx, ay - by);
}

/** Returns a path of stage-space waypoints from (startX, startY) to
 * (endX, endY), routed around furniture. Returns null if unreachable
 * (shouldn't happen with the current obstacle map, but callers should
 * fall back to a direct line rather than crash if it does). */
export function findPath(
  startX: number,
  startY: number,
  endX: number,
  endY: number,
): { x: number; y: number }[] | null {
  const grid = getWalkableGrid();
  const [sx, sy] = stageToCell(startX, startY);
  const [ex, ey] = stageToCell(endX, endY);

  if (!grid[sy]?.[sx] || !grid[ey]?.[ex]) return null;
  if (sx === ex && sy === ey) return [{ x: endX, y: endY }];

  const open: Node[] = [{ gx: sx, gy: sy, g: 0, f: heuristic(sx, sy, ex, ey), parent: null }];
  const closed = new Set<string>();
  const key = (x: number, y: number) => `${x},${y}`;
  const bestG = new Map<string, number>([[key(sx, sy), 0]]);

  let iterations = 0;
  const maxIterations = GRID_W * GRID_H;

  while (open.length > 0 && iterations++ < maxIterations) {
    open.sort((a, b) => a.f - b.f);
    const current = open.shift()!;
    const ck = key(current.gx, current.gy);
    if (closed.has(ck)) continue;
    closed.add(ck);

    if (current.gx === ex && current.gy === ey) {
      const waypoints: { x: number; y: number }[] = [];
      let node: Node | null = current;
      while (node) {
        waypoints.unshift(cellToStage(node.gx, node.gy));
        node = node.parent;
      }
      waypoints.push({ x: endX, y: endY });
      return simplifyPath(waypoints);
    }

    for (const [dx, dy, cost] of NEIGHBORS) {
      const nx = current.gx + dx;
      const ny = current.gy + dy;
      if (!grid[ny]?.[nx]) continue;
      // Prevent cutting diagonally through a blocked corner pair.
      if (dx !== 0 && dy !== 0 && (!grid[current.gy]?.[nx] || !grid[ny]?.[current.gx])) continue;

      const nk = key(nx, ny);
      const g = current.g + cost;
      if (closed.has(nk) && (bestG.get(nk) ?? Infinity) <= g) continue;
      if ((bestG.get(nk) ?? Infinity) <= g) continue;

      bestG.set(nk, g);
      open.push({ gx: nx, gy: ny, g, f: g + heuristic(nx, ny, ex, ey), parent: current });
    }
  }
  return null;
}

/** Drops collinear-ish intermediate waypoints so movement doesn't visibly
 * stair-step along the grid — keeps only direction-change points. */
function simplifyPath(points: { x: number; y: number }[]): { x: number; y: number }[] {
  if (points.length <= 2) return points;
  const out = [points[0]];
  for (let i = 1; i < points.length - 1; i++) {
    const prev = out[out.length - 1];
    const cur = points[i];
    const next = points[i + 1];
    const d1x = cur.x - prev.x;
    const d1y = cur.y - prev.y;
    const d2x = next.x - cur.x;
    const d2y = next.y - cur.y;
    const cross = d1x * d2y - d1y * d2x;
    if (Math.abs(cross) > 0.01) out.push(cur);
  }
  out.push(points[points.length - 1]);
  return out;
}
