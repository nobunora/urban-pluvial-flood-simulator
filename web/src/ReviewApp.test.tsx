import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import {
  createRun,
  getHealth,
  getResultMetadata,
  getRun,
  type ResultMetadataResponse,
} from "./api/client";

vi.mock("./api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/client")>();
  return {
    ...actual,
    getHealth: vi.fn(),
    estimateResources: vi.fn(),
    createRun: vi.fn(),
    getRun: vi.fn(),
    cancelRun: vi.fn(),
    getResultMetadata: vi.fn(),
    inspectResult: vi.fn(),
  };
});

vi.mock("./result/ResultMap", () => ({
  default: ({ mapLabel }: { mapLabel: string }) => (
    <div data-testid="result-map">{mapLabel}</div>
  ),
}));

const metadata: ResultMetadataResponse = {
  schema_version: "1",
  bounds: {
    west_deg: 139.764,
    south_deg: 35.679,
    east_deg: 139.770,
    north_deg: 35.684,
  },
  units: {
    water_depth: "m",
    terrain_elevation: "m",
    grid_resolution: "m",
  },
  available_time_indices: [0, 1],
  time_values: ["2026-01-01T00:00:00", "2026-01-01T00:01:00"],
  max_depth_summary: { global_max_depth_m: 1.25 },
  grid_level_summary: { "1m": 250000 },
  depth_legend: [
    { label: "0.01–0.05 m", min_m: 0.01, max_m: 0.05, color: "#C6E8FF" },
  ],
  provider_summary: {
    building_provider: "osm",
    road_provider: "osm",
    warnings: [],
  },
  engine_summary: {
    sfincs_version: "2.4.0 Galibier",
    sfincs_build_sha256: "ABC",
    sfincs_engine_source: "SFINCS_BIN",
    hydromt_sfincs_version: "2.0.0rc3",
  },
  run_summary: {
    application_version: "0.1.0",
    requested_accuracy_mode: "full_1m",
    rainfall_source: { mode: "constant" },
    elevation_provider_counts: { gsi_1m: 250000 },
    elevation_source_summary: { primary: "GSI" },
    manning_defaults: { general: 0.03, road: 0.02 },
    boundary_policy: "closed boundary",
    roof_rain_mass_diagnostic: { relative_mass_error: 0 },
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

describe("local review UI", () => {
  beforeEach(() => {
    vi.mocked(getHealth).mockResolvedValue({
      status: "ok",
      api_version: "v1",
      application_version: "0.1.0",
      engine: { required: "SFINCS 2.4.0 Galibier" },
    });
    vi.mocked(createRun).mockResolvedValue({
      run_id: "00000000-0000-0000-0000-000000000001",
      status: "QUEUED",
    });
    vi.mocked(getRun).mockResolvedValue({
      run_id: "00000000-0000-0000-0000-000000000001",
      state: "COMPLETE",
      stage_code: "COMPLETE",
      stage_label: "完了",
      failure_code: null,
      failure_message: null,
    });
    vi.mocked(getResultMetadata).mockResolvedValue(metadata);
  });

  it("renders the Full 1 m controls", () => {
    render(<App />);
    expect(screen.getByText("ローカルレビュー版 — Full 1 m")).toBeVisible();
    expect(screen.getByRole("button", { name: "解析開始" })).toBeVisible();
  });

  it("enters dedicated RESULT mode after a completed run", async () => {
    render(<App />);

    fireEvent.change(screen.getByLabelText("継続時間 (min)"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("雨量強度 (mm/h)"), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: "解析開始" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "解析結果" })).toBeVisible();
    });

    expect(screen.getByTestId("result-map")).toHaveTextContent("最大浸水深の地図");
    expect(screen.queryByRole("heading", { name: "1. 条件" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新しい解析" })).toBeVisible();
  });
});
