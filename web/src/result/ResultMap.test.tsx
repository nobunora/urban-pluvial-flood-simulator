import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ResultMetadataResponse } from "../api/client";
import ResultMap from "./ResultMap";

const mocks = vi.hoisted(() => ({
  constructorOptions: [] as Array<Record<string, unknown>>,
  jumpTo: vi.fn(),
  updateImage: vi.fn(),
  setData: vi.fn(),
  setLayoutProperty: vi.fn(),
  triggerRepaint: vi.fn(),
}));

vi.mock("maplibre-gl", () => {
  class ImageSource {
    updateImage(value: unknown) { mocks.updateImage(value); }
  }

  class GeoJSONSource {
    setData(value: unknown) { mocks.setData(value); }
  }

  class Map {
    sources = new globalThis.Map<string, unknown>();

    constructor(options: Record<string, unknown>) {
      mocks.constructorOptions.push(options);
      const style = options.style as {
        sources?: Record<string, { type?: string }>;
      };
      for (const [id, source] of Object.entries(style.sources ?? {})) {
        if (source.type === "image") this.sources.set(id, new ImageSource());
        if (source.type === "geojson") this.sources.set(id, new GeoJSONSource());
      }
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
    getSource(id: string) { return this.sources.get(id); }
    setLayoutProperty(...args: unknown[]) { mocks.setLayoutProperty(...args); }
    triggerRepaint() { mocks.triggerRepaint(); }
  }

  class Marker {
    setLngLat() { return this; }
    addTo() { return this; }
    remove() {}
  }

  class NavigationControl {}

  return {
    GeoJSONSource,
    ImageSource,
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

function options(index: number) {
  return mocks.constructorOptions[index] as {
    style: {
      sources: Record<string, { type?: string; url?: string }>;
      layers: Array<{
        id: string;
        type: string;
        paint?: Record<string, unknown>;
        layout?: Record<string, unknown>;
      }>;
    };
  };
}

describe("ResultMap", () => {
  beforeEach(() => {
    mocks.constructorOptions.length = 0;
    mocks.jumpTo.mockClear();
    mocks.updateImage.mockClear();
    mocks.setData.mockClear();
    mocks.setLayoutProperty.mockClear();
    mocks.triggerRepaint.mockClear();
  });

  it("uses an independent CSS-faded basemap and a persistent analysis map", () => {
    const view = render(
      <ResultMap
        metadata={metadata}
        imageUrl="/api/result/max.png"
        flowVectorUrl={null}
        backgroundOpacity={0.55}
        mapLabel="結果"
        onInspect={vi.fn()}
      />,
    );

    expect(mocks.constructorOptions).toHaveLength(2);
    const base = options(0);
    const overlay = options(1);
    expect(base.style.sources.gsi).toBeDefined();
    expect(overlay.style.sources["result-overlay"].url).toBe("/api/result/max.png");
    expect(overlay.style.sources["flow-vectors"].type).toBe("geojson");
    expect(
      overlay.style.layers.find((layer) => layer.id === "result-overlay")?.paint?.["raster-opacity"],
    ).toBe(1);
    expect(
      overlay.style.layers.find((layer) => layer.id === "flow-vectors")?.type,
    ).toBe("line");

    const baseElement = view.container.querySelector(".result-map-base") as HTMLElement;
    expect(baseElement.style.opacity).toBe("0.55");

    view.rerender(
      <ResultMap
        metadata={metadata}
        imageUrl="/api/result/max.png"
        flowVectorUrl={null}
        backgroundOpacity={0.1}
        mapLabel="結果"
        onInspect={vi.fn()}
      />,
    );

    expect(mocks.constructorOptions).toHaveLength(2);
    expect(baseElement.style.opacity).toBe("0.1");
  });

  it("switches time/grid images without recreating MapLibre and loads vector GeoJSON", () => {
    const view = render(
      <ResultMap
        metadata={metadata}
        imageUrl="/api/result/max.png"
        flowVectorUrl={null}
        backgroundOpacity={0.55}
        mapLabel="結果"
        onInspect={vi.fn()}
      />,
    );
    const initialMapCount = mocks.constructorOptions.length;

    view.rerender(
      <ResultMap
        metadata={metadata}
        imageUrl="/api/result/depth.png?time_index=3"
        flowVectorUrl="/api/result/flow-vectors.geojson?time_index=3"
        backgroundOpacity={0.55}
        mapLabel="結果"
        onInspect={vi.fn()}
      />,
    );

    expect(mocks.constructorOptions).toHaveLength(initialMapCount);
    expect(mocks.updateImage).toHaveBeenLastCalledWith(
      expect.objectContaining({ url: "/api/result/depth.png?time_index=3" }),
    );
    expect(mocks.setData).toHaveBeenLastCalledWith(
      "/api/result/flow-vectors.geojson?time_index=3",
    );
    expect(mocks.setLayoutProperty).toHaveBeenCalledWith(
      "flow-vectors",
      "visibility",
      "visible",
    );

    const overlay = options(1);
    const vectorPaint = overlay.style.layers.find(
      (layer) => layer.id === "flow-vectors",
    )?.paint;
    expect(vectorPaint?.["line-color"]).toEqual(
      expect.arrayContaining(["step", expect.anything()]),
    );
  });
});
