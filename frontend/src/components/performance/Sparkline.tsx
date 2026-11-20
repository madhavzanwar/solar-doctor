import { sparklinePoints } from "@/lib/performance";

/** Tiny inline trend line. Decorative: the number next to it carries the meaning. */
export default function Sparkline({ values, width = 84, height = 22 }: { values: Array<number | null>; width?: number; height?: number }) {
  const pts = sparklinePoints(values, width, height);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" data-testid="sparkline">
      {pts ? <polyline points={pts} fill="none" stroke="var(--field)" strokeWidth="1.5" strokeLinejoin="round" /> : <line x1="2" x2={width - 2} y1={height / 2} y2={height / 2} stroke="var(--line)" strokeDasharray="2 3" />}
    </svg>
  );
}
