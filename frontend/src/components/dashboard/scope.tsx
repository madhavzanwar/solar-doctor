"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type RangeKey = "today" | "7d" | "30d" | "custom";

export interface Scope {
  plantId: number | null;
  range: RangeKey;
  from: string;
  to: string;
}

interface ScopeApi extends Scope {
  setPlantId: (id: number | null) => void;
  setRange: (range: RangeKey) => void;
  setCustom: (from: string, to: string) => void;
}

const KEY = "solardoctor_scope";
const DEFAULT: Scope = { plantId: null, range: "7d", from: "", to: "" };

const Ctx = createContext<ScopeApi | null>(null);

function read(): Scope {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULT;
    const v = JSON.parse(raw) as Partial<Scope>;
    return {
      plantId: typeof v.plantId === "number" ? v.plantId : null,
      range: v.range === "today" || v.range === "7d" || v.range === "30d" || v.range === "custom" ? v.range : "7d",
      from: typeof v.from === "string" ? v.from : "",
      to: typeof v.to === "string" ? v.to : "",
    };
  } catch {
    return DEFAULT;
  }
}

/** Global plant + date-range selection from the topbar (DESIGN.md §5). Persisted per browser. */
export function ScopeProvider({ children }: { children: React.ReactNode }) {
  const [scope, setScope] = useState<Scope>(DEFAULT);

  useEffect(() => {
    setScope(read());
  }, []);

  const update = useCallback((patch: Partial<Scope>) => {
    setScope((prev) => {
      const next = { ...prev, ...patch };
      try {
        window.localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        // Storage can be unavailable (private mode); the selection then lasts for this page view only.
      }
      return next;
    });
  }, []);

  const api = useMemo<ScopeApi>(
    () => ({
      ...scope,
      setPlantId: (plantId) => update({ plantId }),
      setRange: (range) => update({ range }),
      setCustom: (from, to) => update({ from, to, range: "custom" }),
    }),
    [scope, update],
  );

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

const FALLBACK_API: ScopeApi = {
  ...DEFAULT,
  setPlantId: () => {},
  setRange: () => {},
  setCustom: () => {},
};

export function useScope(): ScopeApi {
  const v = useContext(Ctx);
  if (!v) return FALLBACK_API;
  return v;
}

/** Utility to filter timestamp/date records according to the active global scope range */
export function isDateWithinScope(
  dateStr: string | Date | null | undefined,
  scope: { range: RangeKey; from: string; to: string }
): boolean {
  if (!dateStr) return true;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return true;
  const now = new Date();

  if (scope.range === "today") {
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return d >= startOfToday;
  }
  if (scope.range === "7d") {
    const cutoff = new Date(now.getTime() - 7 * 24 * 3600 * 1000);
    return d >= cutoff;
  }
  if (scope.range === "30d") {
    const cutoff = new Date(now.getTime() - 30 * 24 * 3600 * 1000);
    return d >= cutoff;
  }
  if (scope.range === "custom") {
    if (scope.from) {
      const fromD = new Date(scope.from);
      if (d < fromD) return false;
    }
    if (scope.to) {
      const toD = new Date(scope.to);
      toD.setHours(23, 59, 59, 999);
      if (d > toD) return false;
    }
    return true;
  }
  return true;
}

