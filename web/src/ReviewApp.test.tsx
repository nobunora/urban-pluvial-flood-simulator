import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import {
  createRun,
  getAppConfig,
  getHealth,
  getRecentRainfallRanking,
  getResultMetadata,
  getRun,
  importResult,
  openDemoResult,
  searchLocation,
  type ResultMetadataResponse,
} from "./api/client";

vi.mock("./api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/client")>();
  return {
    ...actual,
    getHealth: vi.fn(),
    getAppConfig: vi.fn(),
    getRecentRainfallRanking: vi.fn(),
    createRun: vi.fn(),
    getRun: vi.fn(),
    cancelRun: vi.fn(),
    getResultMetadata: vi.fn(),
    importResult: vi.fn(),
    openDemoResult: vi.fn(),
    inspectResult: vi.fn(),
    searchLocation: vi.fn(),
  };
});

vi.mock("./dev/SetupMap", () => ({
  default: ({
    area,
    disabled,
    onSelect,
  }: {
    area: { width_m: number } | null;
    disabled: boolean;
    onSelect: (lon: number, lat: number) => void;
  }) => (
    <div
      data-testid="setup-map"
      data-area-width={area?.width_m ?? ""}
      data-disabled={String(disabled)}
    >
      <button type="button" disabled={disabled} onClick={() => onSelect(139.8, 35.7)}>
        地図で地点選択
      </button>
    </div>
  ),
}));

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
  flow_vectors_available: false,
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
    window.localStorage.clear();
    vi.mocked(getAppConfig).mockResolvedValue({
      mode: "local",
      allow_run: true,
      allow_result_import: true,
      download_url: "https://github.com/example/releases/latest",
      demo_result_event_ids: [],
    });
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
    vi.mocked(importResult).mockResolvedValue({
      run_id: "00000000-0000-0000-0000-000000000002",
      status: "COMPLETE",
    });
    vi.mocked(getRecentRainfallRanking).mockResolvedValue({
      period_start: "2016-09-23",
      period_end: "2026-09-23",
      coverage_note: "代表被災地点であり、市内の絶対最大浸水地点を示すものではありません。",
      events: [
        {
          event_id: "tokyo-60m-1",
          station_id: "44132",
          station_name: "四日市市中心部",
          duration_minutes: 60,
          total_precipitation_mm: 123.5,
          intensity_mm_per_h: 123.5,
          event_date_or_datetime_metadata: "2025",
          source_url: "https://example.test/jma",
          catalog_generated_at_utc: "2026-09-03T00:00:00+00:00",
          data_quality_flags: [],
          station_lon_deg: 139.75,
          station_lat_deg: 35.69,
          profile_available: false,
          damage_location_name: "くすの木パーキング",
          damage_location_source_url: "https://example.test/damage",
        },
      ],
    });
    vi.mocked(searchLocation).mockResolvedValue({
      candidates: [],
      attribution: {
        text: "CSISシンプルジオコーディング実験を利用",
        url: "https://geocode.csis.u-tokyo.ac.jp/",
      },
    });
  });

  it("renders the Full 1 m controls and lets the setup map change location/range", () => {
    render(<App />);

    expect(screen.getByText("ローカルレビュー版")).toBeVisible();
    expect(screen.queryByText(/Full 1 m/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("雨量強度 (mm/h)")).toHaveValue("150");
    expect(screen.getByLabelText("継続時間 (min)")).toHaveValue("20");
    expect(screen.queryByRole("button", { name: "Adaptive OFF" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Adaptive ON" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "負荷を見積る" })).not.toBeInTheDocument();
    expect(screen.queryByText(/精度:/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "解析開始" })).toBeVisible();
    expect(screen.getByTestId("setup-map")).toHaveAttribute("data-area-width", "500");

    fireEvent.click(screen.getByRole("button", { name: "地図で地点選択" }));
    expect(screen.getByLabelText("緯度")).toHaveValue("35.700000");
    expect(screen.getByLabelText("経度")).toHaveValue("139.800000");

    fireEvent.change(screen.getByLabelText("範囲"), { target: { value: "500" } });
    expect(screen.getByTestId("setup-map")).toHaveAttribute("data-area-width", "1000");
  });

  it("fills rainfall inputs from the static rainfall ranking", async () => {
    render(<App />);

    await waitFor(() => expect(getAppConfig).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: /2025.*四日市.*123.5 mm\/h/ }));

    const rainfallEvent = screen.getByRole("button", { name: /2025.*四日市.*123.5 mm\/h/ });
    expect(rainfallEvent).toHaveTextContent("2025四日市123.5 mm/h");

    expect(screen.getByLabelText("雨量強度 (mm/h)")).toHaveValue("123.5");
    expect(screen.getByLabelText("継続時間 (min)")).toHaveValue("60");
    expect(screen.getByLabelText("緯度")).toHaveValue("34.966500");
    expect(screen.getByLabelText("経度")).toHaveValue("136.620800");
    expect(screen.getByLabelText("範囲")).toHaveValue("2000");
    expect(screen.getByLabelText("最小ブロック")).toHaveValue("auto");
  });

  it("reconnects to the saved run after a browser reload", async () => {
    const runId = "00000000-0000-0000-0000-000000000001";
    window.localStorage.setItem("urban-pluvial-flood-simulator.active-run-id", runId);

    render(<App />);

    await waitFor(() => expect(getRun).toHaveBeenCalledWith(runId));
  });

  it("offers a prepared result in local mode and opens it on request", async () => {
    vi.mocked(getAppConfig).mockResolvedValue({
      mode: "local",
      allow_run: true,
      allow_result_import: true,
      download_url: "https://github.com/example/releases/latest",
      demo_result_event_ids: ["2025-yokkaichi"],
    });
    vi.mocked(openDemoResult).mockResolvedValue({
      run_id: "00000000-0000-0000-0000-000000000002",
      status: "COMPLETE",
    });
    render(<App />);

    await waitFor(() => expect(getAppConfig).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: /2025.*四日市.*123.5 mm\/h/ }));
    expect(await screen.findByRole("dialog", { name: "解析済み結果があります" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "解析済み結果を表示" }));

    await waitFor(() => expect(openDemoResult).toHaveBeenCalledWith("2025-yokkaichi"));
    expect(await screen.findByRole("heading", { name: "解析結果" })).toBeVisible();
  });

  it("opens prepared results directly and replaces analysis with download in demo mode", async () => {
    vi.mocked(getAppConfig).mockResolvedValue({
      mode: "demo",
      allow_run: false,
      allow_result_import: false,
      download_url: "https://github.com/example/releases/latest",
      demo_result_event_ids: ["2025-yokkaichi"],
    });
    vi.mocked(openDemoResult).mockResolvedValue({
      run_id: "00000000-0000-0000-0000-000000000002",
      status: "COMPLETE",
    });
    render(<App />);

    expect(await screen.findByRole("link", { name: "Windows版をダウンロード" })).toHaveAttribute(
      "href",
      "https://github.com/example/releases/latest",
    );
    expect(screen.queryByRole("button", { name: "解析開始" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("解析済みデータを読み込む")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /2025.*四日市.*123.5 mm\/h/ }));
    await waitFor(() => expect(openDemoResult).toHaveBeenCalledWith("2025-yokkaichi"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("imports a saved result for review and offers compressed export", async () => {
    render(<App />);
    const file = new File(["archive"], "saved-result.zip", { type: "application/zip" });
    fireEvent.change(screen.getByLabelText("解析済みデータを読み込む"), {
      target: { files: [file] },
    });

    await waitFor(() => expect(importResult).toHaveBeenCalledWith(file));
    expect(await screen.findByRole("heading", { name: "解析結果" })).toBeVisible();
    expect(screen.getByRole("link", { name: "結果をエクスポート" })).toHaveAttribute(
      "href",
      "/api/v1/runs/00000000-0000-0000-0000-000000000002/export",
    );
  });


  it("uses the selected uniform block size for a new calculation", async () => {
    render(<App />);

    expect(screen.queryByRole("button", { name: "Adaptive OFF" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Adaptive ON" })).not.toBeInTheDocument();
    expect(screen.queryByText(/精度:/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "解析開始" }));
    await waitFor(() => {
      expect(createRun).toHaveBeenCalledWith(
        expect.objectContaining({ requested_accuracy_mode: "uniform", grid_cell_size_m: 1 }),
      );
    });
  });

  it("sends a manually selected 4 m block size to the run API", async () => {
    render(<App />);

    fireEvent.change(screen.getByLabelText("最小ブロック"), {
      target: { value: "4" },
    });
    expect(screen.getByText("15,625")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "解析開始" }));

    await waitFor(() => {
      expect(createRun).toHaveBeenCalledWith(
        expect.objectContaining({
          requested_accuracy_mode: "uniform",
          grid_cell_size_m: 4,
        }),
      );
    });
    expect(createRun).not.toHaveBeenCalledWith(
      expect.objectContaining({ requested_accuracy_mode: "adaptive" }),
    );
  });


  it("uses a geocoder candidate as the canonical setup center", async () => {
    vi.mocked(searchLocation).mockResolvedValue({
      candidates: [
        {
          title: "東京都府中市宮町1丁目",
          lon: 139.4805,
          lat: 35.6722,
          provider: "csis_simple_geocoding",
          confidence: 5,
          level: 8,
          converted: "東京都府中市宮町1丁目",
        },
      ],
      attribution: {
        text: "CSISシンプルジオコーディング実験を利用",
        url: "https://geocode.csis.u-tokyo.ac.jp/",
      },
    });

    render(<App />);

    fireEvent.change(screen.getByLabelText("住所・地名を検索"), {
      target: { value: "府中駅" },
    });
    fireEvent.click(screen.getByRole("button", { name: "検索" }));

    const candidate = await screen.findByRole("button", {
      name: /東京都府中市宮町1丁目/,
    });
    fireEvent.click(candidate);

    expect(screen.getByLabelText("緯度")).toHaveValue("35.672200");
    expect(screen.getByLabelText("経度")).toHaveValue("139.480500");
    expect(screen.getByTestId("setup-map")).toHaveAttribute("data-area-width", "500");
    expect(screen.getByText(/CSISシンプルジオコーディング実験を利用/)).toBeVisible();
  });

  it("disables setup-map mutation while a run is active", async () => {
    vi.mocked(getRun).mockResolvedValue({
      run_id: "00000000-0000-0000-0000-000000000001",
      state: "RUNNING_ENGINE",
      stage_code: "RUNNING_ENGINE",
      stage_label: "SFINCSを実行中",
      failure_code: null,
      failure_message: null,
    });

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "解析開始" }));

    await waitFor(() => {
      expect(screen.getByTestId("setup-map")).toHaveAttribute("data-disabled", "true");
    });
    expect(screen.getByRole("button", { name: "地図で地点選択" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "解析開始" })).toBeDisabled();

    await waitFor(() => {
      expect(screen.getByText(/SFINCS計算中/)).toBeVisible();
    });
  });

  it("enters dedicated RESULT mode after a completed run and retains setup inputs for a new analysis", async () => {
    render(<App />);

    fireEvent.change(screen.getByLabelText("継続時間 (min)"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("雨量強度 (mm/h)"), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: "解析開始" }));

    await waitFor(() => {
      expect(createRun).toHaveBeenCalledWith(
        expect.objectContaining({ requested_accuracy_mode: "uniform", grid_cell_size_m: 1 }),
      );
    });
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "解析結果" })).toBeVisible();
    });

    expect(screen.getByTestId("result-map")).toHaveTextContent("最大浸水深の地図");
    expect(screen.queryByRole("heading", { name: "1. 条件" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "新しい解析" }));

    expect(screen.getByRole("heading", { name: "1. 条件" })).toBeVisible();
    expect(screen.getByLabelText("緯度")).toHaveValue("35.681236");
    expect(screen.getByLabelText("経度")).toHaveValue("139.767125");
    expect(screen.getByLabelText("範囲")).toHaveValue("250");
    expect(screen.getByLabelText("雨量強度 (mm/h)")).toHaveValue("10");
    expect(screen.getByLabelText("継続時間 (min)")).toHaveValue("1");
    expect(screen.queryByText(/精度:/)).not.toBeInTheDocument();
  });
});
