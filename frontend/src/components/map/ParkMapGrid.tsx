"use client";

import { useRef, useState } from "react";
import type { GridPanel, ParkGrid } from "@/lib/api";
import { severityKey } from "@/lib/map";

/**
 * Panel grid, ported from legacy/axalon-nextjs/components/Platform/ParkMapGrid.tsx (MIT) and restyled to the
 * DESIGN.md severity tokens. A labelled group of toggle buttons with a roving tabindex: one tab stop for the whole
 * grid, arrow keys move between cells, Home/End jump to the row ends.
 */
export default function ParkMapGrid({ grid, selectedPanelId, onSelect }: { grid: ParkGrid; selectedPanelId: string | null; onSelect: (p: GridPanel) => void }) {
  const byKey = new Map(grid.panels.map((p) => [`${p.row}|${p.col}`, p]));
  const rows = Math.max(grid.rows, ...grid.panels.map((p) => p.row + 1), 1);
  const cols = Math.max(grid.cols, ...grid.panels.map((p) => p.col + 1), 1);
  const sel = grid.panels.find((p) => p.panel_id === selectedPanelId);
  const first = grid.panels[0];
  const [active, setActive] = useState<[number, number]>([sel?.row ?? first?.row ?? 0, sel?.col ?? first?.col ?? 0]);
  const root = useRef<HTMLDivElement>(null);

  const move = (r: number, c: number) => {
    const nr = Math.min(rows - 1, Math.max(0, r));
    const nc = Math.min(cols - 1, Math.max(0, c));
    setActive([nr, nc]);
    root.current?.querySelector<HTMLButtonElement>(`[data-cell="${nr}-${nc}"]`)?.focus();
  };

  const onKey = (e: React.KeyboardEvent, r: number, c: number) => {
    const to: Record<string, [number, number]> = {
      ArrowRight: [r, c + 1],
      ArrowLeft: [r, c - 1],
      ArrowDown: [r + 1, c],
      ArrowUp: [r - 1, c],
      Home: [r, 0],
      End: [r, cols - 1],
    };
    if (!to[e.key]) return;
    e.preventDefault();
    move(...to[e.key]);
  };

  return (
    <div
      ref={root}
      role="group"
      aria-label={`Panel grid for park ${grid.park_id}, ${rows} rows by ${cols} columns. Use arrow keys to move, Enter to select.`}
      className="sd-grid"
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(18px, 1fr))` }}
    >
      {Array.from({ length: rows * cols }, (_, i) => {
        const r = Math.floor(i / cols);
        const c = i % cols;
        const p = byKey.get(`${r}|${c}`);
        const key = severityKey(p?.worst_severity);
        const isActive = active[0] === r && active[1] === c;
        return (
          <button
            key={i}
            type="button"
            data-cell={`${r}-${c}`}
            data-testid={p ? `panel-${p.panel_id}` : undefined}
            tabIndex={isActive ? 0 : -1}
            aria-pressed={p ? p.panel_id === selectedPanelId : undefined}
            aria-disabled={p ? undefined : true}
            aria-label={p ? `Panel ${p.panel_id}, ${p.detection_count} detections, worst ${p.worst_severity ?? "none"}` : `No detection at row ${r + 1}, column ${c + 1}`}
            className={`sd-cell${key ? ` sd-pin-${key}` : ""}${p?.panel_id === selectedPanelId ? " sd-pin-selected" : ""}`}
            onClick={p ? () => onSelect(p) : undefined}
            onFocus={() => setActive([r, c])}
            onKeyDown={(e) => onKey(e, r, c)}
          />
        );
      })}
    </div>
  );
}
