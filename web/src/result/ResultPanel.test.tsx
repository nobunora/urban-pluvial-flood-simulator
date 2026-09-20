import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ResultMetadataResponse } from "../api/client";
import ResultPanel from "./ResultPanel";

vi.mock("./ResultMap", () => ({
  default: ({ mapLabel }: { mapLabel: string }) => <div data-testid="result-map">{mapLabel}</div>,
}));

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
  available_time_indices: [0, 1],
  time_values: ["2026-01-01T00:00:00", "2026-01-01T00:10:00"],
  max_depth_summary: {
    global_max_depth_m: 1.25,
  },
  grid_level_summary: {
    "1m": 250000,
  },
  depth_legend: [
    { label: "0.01–0.05 m", min_m: 0.01, max_m: 0.05, color: "#C6E8FF" },
    { label: "1.00 m以上", min_m: 1, max_m: null, color: "#6D1B4A" },
  ],
  provider_summary: {
    building_provider: "osm",
    road_provider: "osm",
    warnings: ["PLATEAUからOSMへフォールバックしました。"],
  },
  engine_summary: {
    sfincs_version: "2.4.0 Galibier",
    hydromt_sfincs_version: "2.0.0rc3",
  },
  no_data_policy: "inactive cells are NaN",
  limitations: {
    infiltration_modelled: false,
    sewer_network_modelled: false,
    storm_drain_inlets_modelled: false,
    building_interior_modelled: false,
    spatial_meteorological_rainfall_modelled: false,
    river_stage_boundary_modelled: false,
    coastal_tide_surge_modelled: false,
    official_forecast: false,
  },
};

describe("ResultPanel", () => {
  it("shows maximum depth first and exposes backend provenance/limitations", () => {
    render(
      <ResultPanel
        runId="run-1"
        metadata={metadata}
        rainfallSummary="10 mm/h × 1分"
        onNewAnalysis={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "解析結果" })).toBeVisible();
    expect(screen.getByTestId("result-map")).toHaveTextContent("最大浸水深の地図");
    expect(screen.getByText("1.250 m")).toBeVisible();
    expect(screen.getAllByText("osm").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("浸透は考慮していません。")).toBeVisible();
  });

  it("switches to time depth and grid-resolution controls", () => {
    render(
      <ResultPanel
        runId="run-1"
        metadata={metadata}
        rainfallSummary="10 mm/h × 1分"
        onNewAnalysis={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "時刻別の浸水深" }));
    expect(screen.getByTestId("result-map")).toHaveTextContent("時刻別浸水深の地図");
    expect(screen.getByRole("slider", { name: "結果時刻" })).toBeVisible();
    expect(screen.getByText("現在: 00:00")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "次の時刻" }));
    expect(screen.getByText("現在: 00:10")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "計算格子" }));
    expect(screen.getByTestId("result-map")).toHaveTextContent("計算格子解像度の地図");
    expect(screen.getByText("32 m")).toBeVisible();
  });
});
