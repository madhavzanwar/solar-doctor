"use client";

import type { GridPanel, ParkGrid } from "@/lib/api";
import { severityKey } from "@/lib/map";

/**
 * Panel grid, ported from legacy/axalon-nextjs/components/Platform/ParkMapGrid.tsx (MIT) and restyled to the
 * DESIGN.md severity tokens. Cells are real buttons so the grid is keyboard and screen-reader reachable.
 */
export default function ParkMapGrid({ grid, selectedPanelId, onSelect }: { grid: ParkGrid; selectedPanelId: string | null; onSelect: (p: GridPanel) => void }) {
  const byKey = new Map(grid.panels.map((p) => [`${p.row}|${p.col}`, p]));
  const rows = Math.max(grid.rows, ...grid.panels.map((p) => p.row + 1), 1);
  const cols = Math.max(grid.cols, ...grid.panels.map((p) => p.col + 1), 1);
  return (
    <div role="grid" aria-label={`Panel grid for park ${grid.park_id}, ${rows} rows by ${cols} columns`} className="sd-grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(18px, 1fr))` }}>
      {Array.from({ length: rows * cols }, (_, i) => {
        const r = Math.floor(i / cols);
        const c = i % cols;
        const p = byKey.get(`${r}|${c}`);
        const key = severityKey(p?.worst_severity);
        return (
          <button
            key={i}
            type="button"
            role="gridcell"
            disabled={!p}
            data-testid={p ? `panel-${p.panel_id}` : undefined}
            aria-selected={p ? p.panel_id === selectedPanelId : undefined}
            aria-label={p ? `Panel ${p.panel_id}, ${p.detection_count} detections, worst ${p.worst_severity ?? "none"}` : `No detection at row ${r + 1}, column ${c + 1}`}
            className={`sd-cell${key ? ` sd-pin-${key}` : ""}${p?.panel_id === selectedPanelId ? " sd-pin-selected" : ""}`}
            onClick={p ? () => onSelect(p) : undefined}
          />
        );
      })}
    </div>
  );
}
