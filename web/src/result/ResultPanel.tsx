import { useCallback, useMemo, useRef, useState } from "react";

import {
  inspectResult,
  resultLayerUrl,
  type PointInspectionResponse,
  type ResultMetadataResponse,
} from "../api/client";
import ResultMap from "./ResultMap";
import "./result.css";

type Props = {
  runId: string;
  metadata: ResultMetadataResponse;
  rainfallSummary: string;
  onNewAnalysis: () => void;
};

type ResultLayer = "max_depth" | "time_depth" | "grid_resolution";

const LIMITATION_LABELS: Record<string, string> = {
  infiltration_modelled: "浸透は考慮していません。",
  sewer_network_modelled: "下水道・雨水管は考慮していません。",
  storm_drain_inlets_modelled: "排水口・雨水桝は考慮していません。",
  building_interior_modelled: "建物内部の浸水は計算していません。",
  spatial_meteorological_rainfall_modelled: "気象降雨は解析範囲内で一様として扱います。",
  river_stage_boundary_modelled: "河川水位との連成は行いません。",
  coastal_tide_surge_modelled: "潮位・高潮との連成は行いません。",
  official_forecast: "この結果は数値シナリオであり、公的な洪水予報・避難情報ではありません。",
};

const GRID_LEGEND = [
  ["1 m", "#264653"],
  ["2 m", "#2A6F97"],
  ["4 m", "#3D9180"],
  ["8 m", "#7AA874"],
  ["16 m", "#BABC7D"],
  ["32 m", "#D0C8AD"],
] as const;

function metres(value: number | null | undefined): string {
  return value == null ? "—" : `${value.toFixed(3)} m`;
}

function elapsedLabel(values: string[], index: number): string {
  const current = Date.parse(values[index] ?? "");
  const start = Date.parse(values[0] ?? "");
  if (Number.isFinite(current) && Number.isFinite(start)) {
    const elapsedMinutes = Math.max(0, Math.round((current - start) / 60_000));
    const days = Math.floor(elapsedMinutes / 1440);
    const hours = Math.floor((elapsedMinutes % 1440) / 60);
    const minutes = elapsedMinutes % 60;
    if (days > 0) return `${days}日 ${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
  }
  return values[index] ?? `index ${index}`;
}

export default function ResultPanel({
  runId,
  metadata,
  rainfallSummary,
  onNewAnalysis,
}: Props) {
  const [layer, setLayer] = useState<ResultLayer>("max_depth");
  const [timePosition, setTimePosition] = useState(0);
  const [backgroundTransparency, setBackgroundTransparency] = useState(45);
  const [flowVisible, setFlowVisible] = useState(false);
  const [inspection, setInspection] = useState<PointInspectionResponse | null>(null);
  const [inspectionLoading, setInspectionLoading] = useState(false);
  const [inspectionError, setInspectionError] = useState<string | null>(null);
  const inspectionController = useRef<AbortController | null>(null);

  const selectedTimeIndex = metadata.available_time_indices[timePosition] ?? null;
  const activeTimeIndex = layer === "time_depth" ? selectedTimeIndex : null;
  const imageUrl = useMemo(() => {
    if (layer === "time_depth") {
      if (selectedTimeIndex === null) return resultLayerUrl(runId, "max-depth");
      return resultLayerUrl(runId, "depth", selectedTimeIndex);
    }
    if (layer === "grid_resolution") return resultLayerUrl(runId, "grid-resolution");
    return resultLayerUrl(runId, "max-depth");
  }, [layer, runId, selectedTimeIndex]);

  const flowImageUrl = useMemo(() => {
    if (
      !flowVisible ||
      !metadata.flow_vectors_available ||
      selectedTimeIndex === null
    ) {
      return null;
    }
    return resultLayerUrl(runId, "flow-vectors", selectedTimeIndex);
  }, [flowVisible, metadata.flow_vectors_available, runId, selectedTimeIndex]);

  const showTimeline =
    metadata.available_time_indices.length > 0 &&
    (layer === "time_depth" || flowVisible);

  const mapLabel =
    layer === "time_depth"
      ? "時刻別浸水深の地図"
      : layer === "grid_resolution"
        ? "計算格子解像度の地図"
        : "最大浸水深の地図";

  const handleInspect = useCallback(
    (lon: number, lat: number) => {
      inspectionController.current?.abort();
      const controller = new AbortController();
      inspectionController.current = controller;
      setInspectionLoading(true);
      setInspectionError(null);

      void inspectResult(runId, lon, lat, activeTimeIndex, controller.signal)
        .then((next) => {
          if (!controller.signal.aborted) setInspection(next);
        })
        .catch((cause: unknown) => {
          if (!controller.signal.aborted) setInspectionError(String(cause));
        })
        .finally(() => {
          if (!controller.signal.aborted) setInspectionLoading(false);
        });
    },
    [activeTimeIndex, runId],
  );

  const omittedLimitations = Object.entries(metadata.limitations)
    .filter(([, implemented]) => !implemented)
    .map(([key]) => LIMITATION_LABELS[key] ?? `${key}: 未実装`);

  const provider = metadata.provider_summary;
  const engine = metadata.engine_summary;
  const runSummary = metadata.run_summary;
  const globalMax = metadata.max_depth_summary.global_max_depth_m;
  const maxTimePosition = Math.max(0, metadata.available_time_indices.length - 1);

  return (
    <section className="result-shell" aria-labelledby="result-title">
      <div className="result-heading">
        <div>
          <p className="result-kicker">RESULT</p>
          <h2 id="result-title">解析結果</h2>
          <p>{rainfallSummary} / 高精度 — 全域1 m</p>
        </div>
        <button type="button" onClick={onNewAnalysis}>新しい解析</button>
      </div>

      <div className="result-limitation-bar">
        数値シナリオです。公的な洪水予報・避難判断の代替ではありません。
      </div>

      <div className="result-layer-controls" aria-label="結果レイヤー">
        <button
          type="button"
          className={layer === "max_depth" ? "is-active" : ""}
          aria-pressed={layer === "max_depth"}
          onClick={() => setLayer("max_depth")}
        >
          最大浸水深
        </button>
        <button
          type="button"
          className={layer === "time_depth" ? "is-active" : ""}
          aria-pressed={layer === "time_depth"}
          disabled={metadata.available_time_indices.length === 0}
          onClick={() => setLayer("time_depth")}
        >
          時刻別の浸水深
        </button>
        <button
          type="button"
          className={layer === "grid_resolution" ? "is-active" : ""}
          aria-pressed={layer === "grid_resolution"}
          onClick={() => setLayer("grid_resolution")}
        >
          計算格子
        </button>
        <button
          type="button"
          className={flowVisible ? "is-active" : ""}
          aria-pressed={flowVisible}
          disabled={!metadata.flow_vectors_available}
          onClick={() => setFlowVisible((value) => !value)}
        >
          流れベクトル
        </button>
      </div>

      <div className="result-display-controls">
        <label>
          背景地図の透明度
          <input
            aria-label="背景地図の透明度"
            type="range"
            min={0}
            max={100}
            step={1}
            value={backgroundTransparency}
            onChange={(event) => setBackgroundTransparency(Number(event.target.value))}
          />
          <span>{backgroundTransparency}%</span>
        </label>
        {!metadata.flow_vectors_available && (
          <span className="result-muted">この解析には流れベクトルデータがありません。</span>
        )}
      </div>

      {showTimeline && (
        <div className="result-timeline">
          <button
            type="button"
            disabled={timePosition <= 0}
            onClick={() => setTimePosition((value) => Math.max(0, value - 1))}
            aria-label="前の時刻"
          >
            ◀
          </button>
          <input
            aria-label="結果時刻"
            type="range"
            min={0}
            max={maxTimePosition}
            step={1}
            value={timePosition}
            onChange={(event) => setTimePosition(Number(event.target.value))}
          />
          <button
            type="button"
            disabled={timePosition >= maxTimePosition}
            onClick={() => setTimePosition((value) => Math.min(maxTimePosition, value + 1))}
            aria-label="次の時刻"
          >
            ▶
          </button>
          <strong>現在: {elapsedLabel(metadata.time_values, selectedTimeIndex ?? 0)}</strong>
        </div>
      )}

      <div className="result-layout">
        <div className="result-map-panel">
          <ResultMap
            metadata={metadata}
            imageUrl={imageUrl}
            flowImageUrl={flowImageUrl}
            backgroundOpacity={(100 - backgroundTransparency) / 100}
            mapLabel={mapLabel}
            onInspect={handleInspect}
          />
          {layer !== "grid_resolution" ? (
            <div className="result-legend" aria-label="浸水深の凡例">
              <strong>{layer === "max_depth" ? "最大浸水深 (m)" : "浸水深 (m)"}</strong>
              {metadata.depth_legend?.map((item) => (
                <span key={item.label}>
                  <i style={{ backgroundColor: item.color }} aria-hidden="true" />
                  {item.label}
                </span>
              ))}
              {flowVisible && metadata.flow_vectors_available && (
                <span className="result-vector-note">矢印: 選択時刻の流向</span>
              )}
            </div>
          ) : (
            <div className="result-legend" aria-label="計算格子の凡例">
              <strong>格子解像度</strong>
              {GRID_LEGEND.map(([label, color]) => (
                <span key={label}>
                  <i style={{ backgroundColor: color }} aria-hidden="true" />
                  {label}
                </span>
              ))}
              <span className="result-vector-note">実計算格子: 1 m</span>
            </div>
          )}
        </div>

        <aside className="result-sidebar">
          <section>
            <h3>地点</h3>
            {inspectionLoading && <p>地点データを読み込んでいます…</p>}
            {inspectionError && <p className="smoke-error">{inspectionError}</p>}
            {!inspectionLoading && !inspection && (
              <p>地図をクリックすると、その地点の計算値を確認できます。</p>
            )}
            {inspection && !inspection.has_data && (
              <p>この地点には解析データがありません。</p>
            )}
            {inspection?.has_data && (
              <dl>
                <dt>緯度</dt><dd>{inspection.lat_deg.toFixed(6)}</dd>
                <dt>経度</dt><dd>{inspection.lon_deg.toFixed(6)}</dd>
                <dt>地盤高</dt><dd>{metres(inspection.terrain_elevation_m)}</dd>
                <dt>最大浸水深</dt><dd>{metres(inspection.max_depth_m)}</dd>
                <dt>最大時刻</dt>
                <dd>
                  {inspection.max_time_index == null
                    ? "—"
                    : elapsedLabel(metadata.time_values, inspection.max_time_index)}
                </dd>
                {layer === "time_depth" && (
                  <>
                    <dt>現在水深</dt><dd>{metres(inspection.depth_m)}</dd>
                    <dt>時刻</dt><dd>{inspection.time_value ?? elapsedLabel(metadata.time_values, selectedTimeIndex ?? 0)}</dd>
                  </>
                )}
                <dt>格子</dt><dd>{metres(inspection.grid_resolution_m)}</dd>
              </dl>
            )}
          </section>

          <section>
            <h3>結果概要</h3>
            <dl>
              <dt>最大浸水深</dt>
              <dd>{typeof globalMax === "number" ? `${globalMax.toFixed(3)} m` : "—"}</dd>
              <dt>建物データ</dt><dd>{provider?.building_provider ?? "—"}</dd>
              <dt>道路データ</dt><dd>{provider?.road_provider ?? "—"}</dd>
              <dt>SFINCS</dt><dd>{engine?.sfincs_version ?? "—"}</dd>
            </dl>
            {provider?.warnings?.map((warning) => (
              <p className="result-warning" key={warning}>{warning}</p>
            ))}
          </section>

          <details>
            <summary>解析条件と出典</summary>
            <p>
              範囲: {metadata.bounds.south_deg.toFixed(6)}, {metadata.bounds.west_deg.toFixed(6)}
              {" — "}
              {metadata.bounds.north_deg.toFixed(6)}, {metadata.bounds.east_deg.toFixed(6)}
            </p>
            <p>
              Grid: {Object.entries(metadata.grid_level_summary)
                .map(([level, count]) => `${level}: ${count.toLocaleString()}`)
                .join(" / ")}
            </p>
            <p>Application: {runSummary.application_version}</p>
            <p>Accuracy: {runSummary.requested_accuracy_mode}</p>
            <p>Flow vectors: {metadata.flow_vectors_available ? "available" : "not stored"}</p>
            <p>
              Rainfall: <code>{JSON.stringify(runSummary.rainfall_source)}</code>
            </p>
            <p>
              Elevation: <code>{JSON.stringify(runSummary.elevation_source_summary)}</code>
            </p>
            <p>
              Elevation provider counts: <code>{JSON.stringify(runSummary.elevation_provider_counts)}</code>
            </p>
            <p>
              Manning: <code>{JSON.stringify(runSummary.manning_defaults)}</code>
            </p>
            <p>Boundary: {runSummary.boundary_policy}</p>
            <p>
              Roof-rain mass diagnostic: <code>{JSON.stringify(runSummary.roof_rain_mass_diagnostic)}</code>
            </p>
            <p>HydroMT-SFINCS: {engine?.hydromt_sfincs_version ?? "—"}</p>
            <p className="result-policy">{metadata.no_data_policy}</p>
          </details>

          <details open>
            <summary>モデルの主な制約</summary>
            <ul>
              {omittedLimitations.map((label) => <li key={label}>{label}</li>)}
              <li>屋根雨水は周囲の地表へ質量保存で再配分する近似です。</li>
            </ul>
          </details>
        </aside>
      </div>
    </section>
  );
}
