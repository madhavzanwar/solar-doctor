// website/nextjs/lib/track.ts
// Pure breadcrumb buffer for the live map. Immutable: returns a new array.
// Drops the oldest point past maxLen and skips negligible jitter so the polyline
// stays smooth and bounded.

export interface LatLon { lat: number; lon: number }

const MIN_MOVE_M = 0.5;

function metersBetween(a: LatLon, b: LatLon): number {
  const R = 6_371_000;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function appendTrackPoint(
  track: LatLon[],
  point: LatLon,
  maxLen: number
): LatLon[] {
  const last = track[track.length - 1];
  if (last && metersBetween(last, point) < MIN_MOVE_M) return track;
  const next = [...track, point];
  return next.length > maxLen ? next.slice(next.length - maxLen) : next;
}
