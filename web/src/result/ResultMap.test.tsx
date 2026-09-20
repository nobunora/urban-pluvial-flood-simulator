import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ResultMetadataResponse } from "../api/client";
import ResultMap from "./ResultMap";

const mocks = vi.hoisted(() => ({
  constructorOptions: [] as unknown[],
  resultUpdateImage: vi.fn(),
  flowUpdateImage: vi.fn(),
  setPaintProperty: vi.fn(),
  triggerRepaint: vi.fn(),
}));

vi.mock("maplibre-gl", () => {
  class Map {
    constructor(options: unknown) {
      mocks.constructorOptions.push(options);
    }
    addControl() {}
    on() {}
    off() {}
    remove() {}
    once(_event: string, callback: () => void) { callback(); }
    isStyleLoaded() { return true; }
    getLayer() { return { id: "layer" }; }
    getSource(id: string) {
      if (id === "result-overlay") return { updateImage: mocks.resultUpdateImage };
      if (id === "flow-overlay") return { updateImage: mocks.flowUpdateImage };
      return undefined;
    }
    setPaintProperty(...args: unknown[]) { mocks.setPaintProperty(...args); }
    triggerRepaint() { mocks.triggerRepaint(); }
  }

  class Marker {
    setLngLat() { return this; }
    addTo() { return this; }
    remove() {}
  }

  class NavigationControl {}

  return {
    Map,
    Marker,
    NavigationControl,
  };
});

const metadata: ResultMetadataResponse = {
  schema_version: "1",
  bounds: {
    west_deg: 139.7,
    south_deg: 35.6,
    east_deg: 139.8,
    north_deg: 35.7,
  },
  units: {
    water_depth: "m",
    terrain_elevation: "m",
    grid_resolution: "m",
  },
  available_time_indices: [0, 3],
  flow_vectors_available: true,
  time_values: [
    "2026-01-01T00:00:00",
    "2026-01-01T00:10:00",
    "2026-01-01T00:20:00",
    "2026-01-01T00:30:00",
  ],
  max_depth_summary: { global_max_depth_m: 1.0 },
  grid_level_summary: { "1m": 250000 },
  depth_legend: [],
  provider_summary: { warnings: [] },
  engine_summary: {},
  run_summary: {
    application_version: "0.1.0",
    requested_accuracy_mode: "full_1m",
    rainfall_source: {},
    elevation_provider_counts: {},
    elevation_source_summary: {},
    manning_defaults: {},
    boundary_policy: "closed boundary",
    roof_rain_mass_diagnostic: {},
  },
  no_data_policy: "inactive cells are NaN",
  limitations: {},
};

describe("ResultMap", () => {
  beforeEach(() => {
    mocks.constructorOptions.length = 0;
    mocks.resultUpdateImage.mockClear();
    mocks.flowUpdateImage.mockClear();
    mocks.setPaintProperty.mockClear();
    mocks.triggerRepaint.mockClear();
  });

  it("creates visible result layers in the initial style and fades only the basemap", () => {
    const view = render(
      <ResultMap
        metadata={metadata}
        imageUrl="/api/result/max.png"
        flowImageUrl={null}
        backgroundOpacity={0.55}
        mapLabel="結果"
        onInspect={vi.fn()}
      />,
    );

    const options = mocks.constructorOptions[0] as {
      style: {
        sources: Record<string, { url?: string }>;
        layers: Array<{ id: string; paint?: Record<string, unknown> }>;
      };
    };
    expect(options.style.sources["result-overlay"].url).toBe("/api/result/max.png");

    const gsi = options.style.layers.find((layer) => layer.id === "gsi");
    const result = options.style.layers.find((layer) => layer.id === "result-overlay");
    const flow = options.style.layers.find((layer) => layer.id === "flow-overlay");
    const boundary = options.style.layers.find((layer) => layer.id === "analysis-boundary-outline");

    expect(gsi?.paint?.["raster-opacity"]).toBe(0.55);
    expect(result?.paint?.["raster-opacity"]).toBe(1);
    expect(flow?.paint?.["raster-opacity"]).toBe(0);
    expect(boundary?.paint?.["line-color"]).toBe("#DC2626");

    view.rerender(
      <ResultMap
        metadata={metadata}
        imageUrl="/api/result/depth.png?time_index=3"
        flowImageUrl="/api/result/flow.png?time_index=3"
        backgroundOpacity={0.2}
        mapLabel="結果"
        onInspect={vi.fn()}
      />,
    );

    expect(mocks.resultUpdateImage).toHaveBeenLastCalledWith(
      expect.objectContaining({ url: "/api/result/depth.png?time_index=3" }),
    );
    expect(mocks.flowUpdateImage).toHaveBeenLastCalledWith(
      expect.objectContaining({ url: "/api/result/flow.png?time_index=3" }),
    );
    expect(mocks.setPaintProperty).toHaveBeenCalledWith("gsi", "raster-opacity", 0.2);
    expect(mocks.setPaintProperty).toHaveBeenCalledWith("flow-overlay", "raster-opacity", 1);
    expect(mocks.setPaintProperty).not.toHaveBeenCalledWith(
      "result-overlay",
      "raster-opacity",
      expect.anything(),
    );
  });
});
