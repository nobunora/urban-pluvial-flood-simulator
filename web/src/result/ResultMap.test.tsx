import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ResultMetadataResponse } from "../api/client";
import ResultMap from "./ResultMap";

const mocks = vi.hoisted(() => ({
  constructorOptions: [] as Array<Record<string, unknown>>,
  jumpTo: vi.fn(),
}));

vi.mock("maplibre-gl", () => {
  class Map {
    constructor(options: Record<string, unknown>) {
      mocks.constructorOptions.push(options);
    }
    addControl() {}
    on() {}
    off() {}
    remove() {}
    once(_event: string, callback: () => void) { callback(); }
    jumpTo(value: unknown) { mocks.jumpTo(value); }
    getCenter() { return { lng: 139.75, lat: 35.65 }; }
    getZoom() { return 15; }
    getBearing() { return 0; }
    getPitch() { return 0; }
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

function overlayOptions(index: number) {
  return mocks.constructorOptions[index] as {
    style: {
      sources: Record<string, { url?: string }>;
      layers: Array<{ id: string; paint?: Record<string, unknown> }>;
    };
  };
}

describe("ResultMap", () => {
  beforeEach(() => {
    mocks.constructorOptions.length = 0;
    mocks.jumpTo.mockClear();
  });

  it("uses an independent CSS-faded basemap and full-opacity result canvas", () => {
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

    expect(mocks.constructorOptions).toHaveLength(2);
    const base = overlayOptions(0);
    const overlay = overlayOptions(1);
    expect(base.style.sources.gsi).toBeDefined();
    expect(overlay.style.sources["result-overlay"].url).toBe("/api/result/max.png");
    expect(
      overlay.style.layers.find((layer) => layer.id === "result-overlay")?.paint?.["raster-opacity"],
    ).toBe(1);
    expect(overlay.style.layers.some((layer) => layer.id === "flow-overlay")).toBe(false);
    expect(
      overlay.style.layers.find((layer) => layer.id === "analysis-boundary-outline")?.paint?.["line-color"],
    ).toBe("#DC2626");

    const baseElement = view.container.querySelector(".result-map-base") as HTMLElement;
    expect(baseElement.style.opacity).toBe("0.55");

    view.rerender(
      <ResultMap
        metadata={metadata}
        imageUrl="/api/result/max.png"
        flowImageUrl={null}
        backgroundOpacity={0.1}
        mapLabel="結果"
        onInspect={vi.fn()}
      />,
    );

    expect(mocks.constructorOptions).toHaveLength(2);
    expect(baseElement.style.opacity).toBe("0.1");
  });

  it("rebuilds the overlay map with the selected depth/grid/vector image URLs", () => {
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

    view.rerender(
      <ResultMap
        metadata={metadata}
        imageUrl="/api/result/depth.png?time_index=3"
        flowImageUrl="/api/result/flow.png?time_index=3"
        backgroundOpacity={0.55}
        mapLabel="結果"
        onInspect={vi.fn()}
      />,
    );

    expect(mocks.constructorOptions).toHaveLength(4);
    const replacementOverlay = overlayOptions(3);
    expect(replacementOverlay.style.sources["result-overlay"].url)
      .toBe("/api/result/depth.png?time_index=3");
    expect(replacementOverlay.style.sources["flow-overlay"].url)
      .toBe("/api/result/flow.png?time_index=3");
    expect(
      replacementOverlay.style.layers.find((layer) => layer.id === "result-overlay")?.paint?.["raster-opacity"],
    ).toBe(1);
    expect(
      replacementOverlay.style.layers.find((layer) => layer.id === "flow-overlay")?.paint?.["raster-opacity"],
    ).toBe(1);
  });
});
