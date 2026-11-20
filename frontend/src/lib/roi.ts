"use client";

import { useEffect, useState } from "react";
import type { RecoverableInr } from "@/lib/performance";
import { roiApi } from "@/lib/api/endpoints";

/**
 * Typed hook for the Performance KPI "Recoverable ₹ / month".
 * Fetches real ROI data from GET /api/v1/roi/{plant_id} and provides { state: "ready", inrPerMonth }.
 */
export function useRecoverableInr(plantId: number | null): RecoverableInr {
  const [data, setData] = useState<RecoverableInr>({ state: "unconfigured" });

  useEffect(() => {
    if (!plantId) {
      setData({ state: "unconfigured" });
      return;
    }

    let active = true;
    roiApi
      .get(plantId)
      .then((res) => {
        if (active && res && typeof res.inr_per_month === "number") {
          setData({ state: "ready", inrPerMonth: res.inr_per_month });
        }
      })
      .catch(() => {
        if (active) {
          setData({ state: "unconfigured" });
        }
      });

    return () => {
      active = false;
    };
  }, [plantId]);

  return data;
}
