import type { RecoverableInr } from "@/lib/performance";

/**
 * Typed hook for the Performance KPI "Recoverable ₹ / month". The ROI API (DESIGN.md §8.4) is not built yet, so
 * every plant is "unconfigured". When it lands, fetch it here and return `{ state: "ready", inrPerMonth }`.
 */
export function useRecoverableInr(plantId: number | null): RecoverableInr {
  void plantId;
  return { state: "unconfigured" };
}
