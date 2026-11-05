/** Marker the seed/import writes at the end of `location` for the PVDAQ single-axis-tracker plant. */
export const TRACKER_MARKER = "[single-axis tracker, fixed-tilt baseline invalid]";

export function isTrackerPlant(plant: { location?: string | null } | null | undefined): boolean {
  return !!plant?.location && plant.location.includes("[single-axis tracker");
}
