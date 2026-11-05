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

export function useScope(): ScopeApi {
  const v = useContext(Ctx);
  if (!v) throw new Error("useScope must be used inside ScopeProvider");
  return v;
}
