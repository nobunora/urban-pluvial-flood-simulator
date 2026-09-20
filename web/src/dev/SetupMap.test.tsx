import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AnalysisArea } from "../api/client";
import SetupMap from "./SetupMap";

const mocks = vi.hoisted(() => ({
  fitBounds: vi.fn(),
  jumpTo: vi.fn(),
  easeTo: vi.fn(),
  stop: vi.fn(),
  resize: vi.fn(),
  setData: vi.fn(),
  markerSetLngLat: vi.fn(),
}));

vi.mock("maplibre-gl", () => {
  class Map {
    addControl() {}
    on() {}
    off() {}
    remove() {}
    once(_event: string, callback: () => void) { callback(); }
    isStyleLoaded() { return true; }
    getCanvas() { return { style: { cursor: "" } }; }
    getSource() { return { setData: mocks.setData }; }
    fitBounds(...args: unknown[]) { mocks.fitBounds(...args); }
    jumpTo(...args: unknown[]) { mocks.jumpTo(...args); }
    easeTo(...args: unknown[]) { mocks.easeTo(...args); }
    stop() { mocks.stop(); }
    resize() { mocks.resize(); }
  }

  class Marker {
    setLngLat(value: unknown) {
      mocks.markerSetLngLat(value);
      return this;
    }
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

function area(lat: number, lon: number): AnalysisArea {
  return {
    mode: "preset_square",
    center: { lat_deg: lat, lon_deg: lon },
    bounds: {
      west_deg: lon - 0.002,
      south_deg: lat - 0.002,
      east_deg: lon + 0.002,
      north_deg: lat + 0.002,
    },
    width_m: 500,
    height_m: 500,
    area_m2: 250000,
  };
}

describe("SetupMap", () => {
  beforeEach(() => {
    for (const mock of Object.values(mocks)) mock.mockClear();
  });

  it("recenters and refits when canonical location changes", () => {
    const initial = area(35.681236, 139.767125);
    const selected = area(35.6722, 139.4805);

    const view = render(
      <SetupMap
        centerLat={initial.center.lat_deg}
        centerLon={initial.center.lon_deg}
        area={initial}
        disabled={false}
        onSelect={vi.fn()}
      />,
    );

    view.rerender(
      <SetupMap
        centerLat={selected.center.lat_deg}
        centerLon={selected.center.lon_deg}
        area={selected}
        disabled={false}
        onSelect={vi.fn()}
      />,
    );

    expect(mocks.markerSetLngLat).toHaveBeenLastCalledWith([
      selected.center.lon_deg,
      selected.center.lat_deg,
    ]);
    expect(mocks.stop).toHaveBeenCalled();
    expect(mocks.resize).toHaveBeenCalled();
    expect(mocks.fitBounds).toHaveBeenLastCalledWith(
      [
        [selected.bounds.west_deg, selected.bounds.south_deg],
        [selected.bounds.east_deg, selected.bounds.north_deg],
      ],
      { padding: 40, maxZoom: 17, duration: 350 },
    );
  });
});
