import { useCallback, useRef, useState } from "react";

import {
  inspectResult,
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

function metres(value: number | null | undefined): string {
  return value == null ? "—" : `${value.toFixed(3)} m`;
}

export default function ResultPanel({
  runId,
  metadata,
  rainfallSummary,
  onNewAnalysis,
}: Props) {
  const [inspection, setInspection] = useState<PointInspectionResponse | null>(null);
  const [inspectionLoading, setInspectionLoading] = useState(false);
  const [inspectionError, setInspectionError] = useState<string | null>(null);
  const inspectionController = useRef<AbortController | null>(null);

  const handleInspect = useCallback(
    (lon: number, lat: number) => {
      inspectionController.current?.abort();
      const controller = new AbortController();
      inspectionController.current = controller;
      setInspectionLoading(true);
      setInspectionError(null);

      void inspectResult(runId, lon, lat, null, controller.signal)
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
    [runId],
  );

  const omittedLimitations = Object.entries(metadata.limitations)
    .filter(([, implemented]) => !implemented)
    .map(([key]) => LIMITATION_LABELS[key] ?? `${key}: 未実装`);

  const provider = metadata.provider_summary;
  const engine = metadata.engine_summary;
  const globalMax = metadata.max_depth_summary.global_max_depth_m;

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

      <div className="result-layout">
        <div className="result-map-panel">
          <ResultMap runId={runId} metadata={metadata} onInspect={handleInspect} />
          <div className="result-legend" aria-label="最大浸水深の凡例">
            <strong>最大浸水深 (m)</strong>
            {metadata.depth_legend?.map((item) => (
              <span key={item.label}>
                <i style={{ backgroundColor: item.color }} aria-hidden="true" />
                {item.label}
              </span>
            ))}
          </div>
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
            <p>Grid: {Object.entries(metadata.grid_level_summary).map(([level, count]) => `${level}: ${count.toLocaleString()}`).join(" / ")}</p>
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
