import { describe, expect, it } from "vitest";
import type { Plant } from "@/lib/api";
import {
  BASEMAPS,
  generateParkStringPolygons,
  STRING_HEALTH_COLORS,
  type BasemapId,
} from "@/lib/map";

const mockPlant: Plant = {
  id: 42,
  name: "Bhadla Solar Park Sector 4",
  location: "Rajasthan, India",
  latitude: 27.53,
  longitude: 71.91,
  timezone: "Asia/Kolkata",
  capacity_kw: 250000,
  inverter_capacity_kw: 225000,
  is_active: true,
  park_id: "bhadla-sec-4",
  source: "MANUAL",
  created_at: "2026-01-15T00:00:00Z",
  updated_at: "2026-01-15T00:00:00Z",
};

describe("Gigawatt-Scale Orthomosaic GIS & Drone Tile Layers", () => {
  it("defines standard and drone orthomosaic tile layers", () => {
    const keys = Object.keys(BASEMAPS) as BasemapId[];
    expect(keys).toContain("positron");
    expect(keys).toContain("imagery");
    expect(keys).toContain("drone_ortho");
    expect(keys).toContain("thermal_ir");

    // Standard map layers
    expect(BASEMAPS.positron.label).toBe("Standard Map");
    expect(BASEMAPS.imagery.label).toBe("Satellite Imagery");

    // High-Res Drone Orthomosaic
    expect(BASEMAPS.drone_ortho.label).toBe("High-Res Drone Orthomosaic");
    expect(BASEMAPS.drone_ortho.isOverlay).toBe(true);
    expect(BASEMAPS.drone_ortho.maxZoom).toBeGreaterThanOrEqual(20);
    expect(BASEMAPS.drone_ortho.filterClass).toBe("sd-layer-ortho");

    // Radiometric Thermal Infrared (FLIR Ironbow)
    expect(BASEMAPS.thermal_ir.label).toBe("Radiometric Thermal IR");
    expect(BASEMAPS.thermal_ir.isOverlay).toBe(true);
    expect(BASEMAPS.thermal_ir.palette).toBe("ironbow");
    expect(BASEMAPS.thermal_ir.filterClass).toBe("sd-layer-thermal");
  });

  it("defines exact enterprise design token health colors", () => {
    expect(STRING_HEALTH_COLORS.NORMAL).toBe("#2f6b4f");
    expect(STRING_HEALTH_COLORS.DERATED).toBe("#a8792f");
    expect(STRING_HEALTH_COLORS.CRITICAL).toBe("#9b2c2c");
  });
});

describe("generateParkStringPolygons utility-scale generator", () => {
  it("generates realistic GeoJSON bounding boxes for 10 inverter stations and 240 string tables", () => {
    const geo = generateParkStringPolygons(mockPlant);

    expect(geo.type).toBe("FeatureCollection");
    expect(geo.stations).toHaveLength(10);
    expect(geo.strings).toHaveLength(240);
    expect(geo.features).toHaveLength(250); // 10 stations + 240 strings

    // Summary counts
    expect(geo.summary.total_stations).toBe(10);
    expect(geo.summary.total_strings).toBe(240);
    expect(geo.summary.normal_count + geo.summary.derated_count + geo.summary.critical_count).toBe(240);
    expect(geo.summary.total_power_kw).toBeGreaterThan(0);
  });

  it("maps station and string polygons around the plant's actual GPS latitude/longitude", () => {
    const geo = generateParkStringPolygons(mockPlant);

    // Verify coordinates are clustered around plant's lat=27.53, lon=71.91
    for (const station of geo.stations) {
      expect(station.geometry.type).toBe("Polygon");
      const ring = station.geometry.coordinates[0];
      expect(ring.length).toBeGreaterThanOrEqual(5); // closed polygon

      for (const [lon, lat] of ring) {
        expect(lat).toBeGreaterThan(27.50);
        expect(lat).toBeLessThan(27.56);
        expect(lon).toBeGreaterThan(71.85);
        expect(lon).toBeLessThan(71.97);
      }
    }

    for (const str of geo.strings) {
      expect(str.geometry.type).toBe("Polygon");
      const ring = str.geometry.coordinates[0];
      expect(ring.length).toBe(5); // 4 corners + closed point

      for (const [lon, lat] of ring) {
        expect(lat).toBeGreaterThan(27.50);
        expect(lat).toBeLessThan(27.56);
        expect(lon).toBeGreaterThan(71.85);
        expect(lon).toBeLessThan(71.97);
      }
    }
  });

  it("strictly implements Edge engineer telemetry schema & defect attributes", () => {
    const geo = generateParkStringPolygons(mockPlant);
    const sample = geo.strings[0].properties;

    // Edge telemetry contract fields
    expect(sample.plant_id).toBe(42);
    expect(sample.inverter_id).toMatch(/^INV-\d{2}$/);
    expect(sample.string_id).toMatch(/^S-\d{2}$/);
    expect(typeof sample.power_kw).toBe("number");
    expect(typeof sample.voltage_v).toBe("number");
    expect(typeof sample.current_a).toBe("number");
    expect(typeof sample.shortfall_kw).toBe("number");
    expect(["NORMAL", "DERATED", "CRITICAL"]).toContain(sample.status);

    // Additional inspection attributes
    expect(typeof sample.loss_pct).toBe("number");
    expect(typeof sample.defect_diagnosis).toBe("string");
    expect(typeof sample.temperature_c).toBe("number");
  });

  it("merges dynamic Edge sensor telemetry overrides accurately", () => {
    const telemetryOverrides = {
      "INV-01-S-01": {
        status: "CRITICAL" as const,
        voltage_v: 110.5,
        current_a: 0.45,
        power_kw: 0.05,
        shortfall_kw: 6.4,
        loss_pct: 99.2,
        defect_diagnosis: "Simulated Junction Box Arcing & Thermal Runaway",
        temperature_c: 89.6,
      },
    };

    const geo = generateParkStringPolygons(mockPlant, telemetryOverrides);
    const targetString = geo.strings.find((s) => s.id === "INV-01-S-01");

    expect(targetString).toBeDefined();
    expect(targetString?.properties.status).toBe("CRITICAL");
    expect(targetString?.properties.voltage_v).toBe(110.5);
    expect(targetString?.properties.current_a).toBe(0.45);
    expect(targetString?.properties.shortfall_kw).toBe(6.4);
    expect(targetString?.properties.defect_diagnosis).toBe("Simulated Junction Box Arcing & Thermal Runaway");
    expect(targetString?.properties.temperature_c).toBe(89.6);
  });
});
