import { obstaclesInStageSpace, WALKABLE_BOUNDS, STAGE_WIDTH, STAGE_HEIGHT } from "./obstacles";

export const CELL_SIZE = 20;
export const GRID_W = Math.ceil(STAGE_WIDTH / CELL_SIZE);
export const GRID_H = Math.ceil(STAGE_HEIGHT / CELL_SIZE);

let cachedGrid: boolean[][] | null = null;

/** true = walkable. Built once from the static obstacle map and cached —
 * furniture doesn't move at runtime, so there's no reason to rebuild per
 * pathfinding call. */
export function getWalkableGrid(): boolean[][] {
  if (cachedGrid) return cachedGrid;

  const obstacles = obstaclesInStageSpace();
  const grid: boolean[][] = [];
  for (let gy = 0; gy < GRID_H; gy++) {
    const row: boolean[] = [];
    for (let gx = 0; gx < GRID_W; gx++) {
      const cx = gx * CELL_SIZE + CELL_SIZE / 2;
      const cy = gy * CELL_SIZE + CELL_SIZE / 2;
      const inBounds =
        cx >= WALKABLE_BOUNDS.x &&
        cx <= WALKABLE_BOUNDS.x + WALKABLE_BOUNDS.w &&
        cy >= WALKABLE_BOUNDS.y &&
        cy <= WALKABLE_BOUNDS.y + WALKABLE_BOUNDS.h;
      const blocked = obstacles.some(
        (r) => cx >= r.x && cx <= r.x + r.w && cy >= r.y && cy <= r.y + r.h,
      );
      row.push(inBounds && !blocked);
    }
    grid.push(row);
  }
  cachedGrid = grid;
  return grid;
}

export function stageToCell(x: number, y: number): [number, number] {
  return [Math.floor(x / CELL_SIZE), Math.floor(y / CELL_SIZE)];
}

export function cellToStage(gx: number, gy: number): { x: number; y: number } {
  return { x: gx * CELL_SIZE + CELL_SIZE / 2, y: gy * CELL_SIZE + CELL_SIZE / 2 };
}

/** Nearest walkable cell to (gx, gy) — used to snap a desk/spawn target
 * that lands just inside furniture padding onto open floor. */
export function nearestWalkable(gx: number, gy: number): [number, number] {
  const grid = getWalkableGrid();
  if (grid[gy]?.[gx]) return [gx, gy];
  for (let radius = 1; radius < 15; radius++) {
    for (let dy = -radius; dy <= radius; dy++) {
      for (let dx = -radius; dx <= radius; dx++) {
        const nx = gx + dx;
        const ny = gy + dy;
        if (grid[ny]?.[nx]) return [nx, ny];
      }
    }
  }
  return [gx, gy];
}
