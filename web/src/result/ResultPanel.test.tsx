import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { inspectResult, type ResultMetadataResponse } from "../api/client";
import ResultPanel from "./ResultPanel";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, inspectResult: vi.fn() };
});

vi.mock("./ResultMap", () => ({
  default: ({
    mapLabel,
    imageUrl,
    flowImageUrl,
    backgroundOpacity,
    onInspect,
  }: {
    mapLabel: string;
    imageUrl: string;
    flowImageUrl: string | null;
    backgroundOpacity: number;
    onInspect: (lon: number, lat: number) => void;
  }) => (
    <div
      data-testid="result-map"
      data-image-url={imageUrl}
      data-flow-image-url={flowImageUrl ?? ""}
      data-background-opacity={String(backgroundOpacity)}
    >
      {mapLabel}
      <button type="button" onClick={() => onInspect(139.75, 35.65)}>地点を確認</button>
    </div>
  ),
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
  available_time_indices: [0, 3],
  flow_vectors_available: true,
  time_values: [
    "2026-01-01T00:00:00",
    "2026-01-01T00:10:00",
    "2026-01-01T00:20:00",
    "2026-01-01T00:30:00",
  ],
  max_depth_summary: {
    global_max_depth_m: 1.25,
  },
  grid_level_summary: {
    "1m": 250000,
  },
  depth_legend: [
    { label: "0.01–0.05 m", min_m: 0.01, max_m: 0.05, color: "#C6E8FF" },
    { label: "0.05–0.10 m", min_m: 0.05, max_m: 0.1, color: "#5BB1FF" },
    { label: "0.10–0.30 m", min_m: 0.1, max_m: 0.3, color: "#406EDE" },
    { label: "0.30–0.50 m", min_m: 0.3, max_m: 0.5, color: "#7E52C4" },
    { label: "0.50–1.00 m", min_m: 0.5, max_m: 1, color: "#C4418B" },
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
  run_summary: {
    application_version: "0.1.0",
    requested_accuracy_mode: "full_1m",
    rainfall_source: { mode: "constant", intensity_mm_per_h: 10 },
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

describe("ResultPanel", () => {
  beforeEach(() => {
    vi.mocked(inspectResult).mockReset();
  });

  it("shows native point values including maximum time", async () => {
    vi.mocked(inspectResult).mockResolvedValue({
      lon_deg: 139.75,
      lat_deg: 35.65,
      has_data: true,
      row: 10,
      column: 20,
      time_index: null,
      time_value: null,
      depth_m: null,
      max_depth_m: 0.42,
      max_time_index: 3,
      max_time_value: "2026-01-01T00:30:00",
      terrain_elevation_m: 12.3,
      grid_resolution_m: 1,
    });

    render(
      <ResultPanel
        runId="run-1"
        metadata={metadata}
        rainfallSummary="10 mm/h × 1分"
        onNewAnalysis={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "地点を確認" }));

    expect(await screen.findByText("0.420 m")).toBeVisible();
    expect(screen.getByText("最大時刻")).toBeVisible();
    expect(screen.getByText("00:30")).toBeVisible();
    expect(screen.getByText("12.300 m")).toBeVisible();
    expect(screen.getByText("1.000 m")).toBeVisible();
  });

  it("passes the selected actual output index to native inspection on the time layer", async () => {
    vi.mocked(inspectResult).mockResolvedValue({
      lon_deg: 139.75,
      lat_deg: 35.65,
      has_data: true,
      row: 10,
      column: 20,
      time_index: 3,
      time_value: "2026-01-01T00:30:00",
      depth_m: 0.12,
      max_depth_m: 0.42,
      max_time_index: 3,
      max_time_value: "2026-01-01T00:30:00",
      terrain_elevation_m: 12.3,
      grid_resolution_m: 1,
    });

    render(
      <ResultPanel
        runId="run-1"
        metadata={metadata}
        rainfallSummary="10 mm/h × 1分"
        onNewAnalysis={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "時刻別の浸水深" }));
    fireEvent.click(screen.getByRole("button", { name: "次の時刻" }));
    fireEvent.click(screen.getByRole("button", { name: "地点を確認" }));

    expect(await screen.findByText("0.120 m")).toBeVisible();
    expect(screen.getByText("現在水深")).toBeVisible();
    expect(vi.mocked(inspectResult).mock.calls[0]?.slice(0, 4)).toEqual([
      "run-1",
      139.75,
      35.65,
      3,
    ]);
  });

  it("shows no-data distinctly from zero depth", async () => {
    vi.mocked(inspectResult).mockResolvedValue({
      lon_deg: 139.75,
      lat_deg: 35.65,
      has_data: false,
      row: 10,
      column: 20,
      time_index: null,
      time_value: null,
      depth_m: null,
      max_depth_m: null,
      max_time_index: null,
      max_time_value: null,
      terrain_elevation_m: null,
      grid_resolution_m: null,
    });

    render(
      <ResultPanel
        runId="run-1"
        metadata={metadata}
        rainfallSummary="10 mm/h × 1分"
        onNewAnalysis={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "地点を確認" }));

    expect(
      await screen.findByText("この地点には解析データがありません。"),
    ).toBeVisible();
    expect(screen.queryByText("0.000 m")).not.toBeInTheDocument();
  });

  it("shows maximum depth first, the exact six-band legend, and complete provenance/limitations", () => {
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

    for (const label of [
      "0.01–0.05 m",
      "0.05–0.10 m",
      "0.10–0.30 m",
      "0.30–0.50 m",
      "0.50–1.00 m",
      "1.00 m以上",
    ]) {
      expect(screen.getByText(label)).toBeVisible();
    }

    expect(screen.getAllByText("osm").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("浸透は考慮していません。")).toBeVisible();

    fireEvent.click(screen.getByText("解析条件と出典"));
    expect(screen.getByText("Application: 0.1.0")).toBeVisible();
    expect(screen.getByText(/Rainfall:/)).toBeVisible();
    expect(screen.getByText(/Elevation:/)).toBeVisible();
    expect(screen.getByText(/Elevation provider counts:/)).toBeVisible();
    expect(screen.getByText(/Manning:/)).toBeVisible();
    expect(screen.getByText("Boundary: closed boundary")).toBeVisible();
    expect(screen.getByText(/Roof-rain mass diagnostic:/)).toBeVisible();
    expect(screen.getByText("HydroMT-SFINCS: 2.0.0rc3")).toBeVisible();
  });

  it("switches only among actual time indices and exposes grid-resolution controls", () => {
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
    expect(screen.getByTestId("result-map")).toHaveAttribute(
      "data-image-url",
      "/api/v1/runs/run-1/layers/depth.png?time_index=0",
    );

    fireEvent.click(screen.getByRole("button", { name: "次の時刻" }));
    expect(screen.getByText("現在: 00:30")).toBeVisible();
    expect(screen.getByTestId("result-map")).toHaveAttribute(
      "data-image-url",
      "/api/v1/runs/run-1/layers/depth.png?time_index=3",
    );

    fireEvent.click(screen.getByRole("button", { name: "計算格子" }));
    expect(screen.getByTestId("result-map")).toHaveTextContent("計算格子解像度の地図");
    expect(screen.getByTestId("result-map")).toHaveAttribute(
      "data-image-url",
      "/api/v1/runs/run-1/layers/grid-resolution.png",
    );
    expect(screen.getByText("実計算格子: 1 m")).toBeVisible();
    expect(screen.getByText("32 m")).toBeVisible();
  });

  it("passes opacity and actual selected time to the flow-vector overlay", () => {
    render(
      <ResultPanel
        runId="run-1"
        metadata={metadata}
        rainfallSummary="10 mm/h × 1分"
        onNewAnalysis={vi.fn()}
      />,
    );

    expect(screen.getByTestId("result-map")).toHaveAttribute("data-background-opacity", "0.55");

    fireEvent.change(screen.getByRole("slider", { name: "背景地図の透明度" }), {
      target: { value: "80" },
    });
    expect(screen.getByTestId("result-map")).toHaveAttribute("data-background-opacity", "0.2");
    expect(screen.getByText("80%")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "流れベクトル" }));
    expect(screen.getByTestId("result-map")).toHaveAttribute(
      "data-flow-image-url",
      "/api/v1/runs/run-1/layers/flow-vectors.png?time_index=0",
    );

    fireEvent.click(screen.getByRole("button", { name: "次の時刻" }));
    expect(screen.getByTestId("result-map")).toHaveAttribute(
      "data-flow-image-url",
      "/api/v1/runs/run-1/layers/flow-vectors.png?time_index=3",
    );
  });

  it("shows vector unavailability for historical runs without stored velocities", () => {
    render(
      <ResultPanel
        runId="run-1"
        metadata={{ ...metadata, flow_vectors_available: false }}
        rainfallSummary="10 mm/h × 1分"
        onNewAnalysis={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "流れベクトル" })).toBeDisabled();
    expect(screen.getByText("この解析には流れベクトルデータがありません。")).toBeVisible();
  });
});
