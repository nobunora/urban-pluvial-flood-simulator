import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getFlowVectors,
  inspectResult,
  resultLayerUrl,
  type FlowVectorFeatureCollection,
  type FlowViewport,
  type PointInspectionResponse,
  type ResultMetadataResponse,
} from "../api/client";
import ResultMap, { type FlowRenderStats } from "./ResultMap";
import { encodeGif, type GifFrame } from "./gifEncoder";
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

function strideForZoom(zoom: number): number {
  const exponent = Math.max(0, Math.min(9, Math.round(18 - zoom)));
  return 2 ** exponent;
}

function interpolateFlow(a: FlowVectorFeatureCollection, b: FlowVectorFeatureCollection, t: number): FlowVectorFeatureCollection {
  const byId = new Map(b.features.map((feature) => [`${feature.properties.row}:${feature.properties.column}`, feature]));
  const features = a.features.map((left) => {
    const right = byId.get(`${left.properties.row}:${left.properties.column}`);
    if (!right) return left;
    const coordinates = left.geometry.coordinates.map((line, lineIndex) => line.map((point, pointIndex) => {
      const target = right.geometry.coordinates[lineIndex]?.[pointIndex] ?? point;
      return [point[0] + (target[0] - point[0]) * t, point[1] + (target[1] - point[1]) * t];
    }));
    return { ...left, geometry: { ...left.geometry, coordinates }, properties: { ...left.properties, u_mps: left.properties.u_mps + (right.properties.u_mps - left.properties.u_mps) * t, v_mps: left.properties.v_mps + (right.properties.v_mps - left.properties.v_mps) * t, speed_mps: left.properties.speed_mps + (right.properties.speed_mps - left.properties.speed_mps) * t } };
  });
  return { ...a, features, metadata: { ...a.metadata, arrow_count: features.length, sampling_method: "canonical-1m-viewport-stride-interpolated" } };
}

const FLOW_SPEED_LEGEND = [
  ["0.001–0.10 m/s", "#2DC4B2"],
  ["0.10–0.30 m/s", "#3BB2D0"],
  ["0.30–0.50 m/s", "#3F51B5"],
  ["0.50–1.00 m/s", "#8E44AD"],
  ["1.00–2.00 m/s", "#E74C3C"],
  ["2.00 m/s以上", "#7F0000"],
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
  const [flowVectorData, setFlowVectorData] = useState<FlowVectorFeatureCollection | null>(null);
  const [flowLoading, setFlowLoading] = useState(false);
  const [flowError, setFlowError] = useState<string | null>(null);
  const [flowRenderStats, setFlowRenderStats] = useState<FlowRenderStats | null>(null);
  const [flowViewport, setFlowViewport] = useState<FlowViewport>({ west: metadata.bounds.west_deg, south: metadata.bounds.south_deg, east: metadata.bounds.east_deg, north: metadata.bounds.north_deg });
  const [flowStride, setFlowStride] = useState(8);
  const [nextFlowVectorData, setNextFlowVectorData] = useState<FlowVectorFeatureCollection | null>(null);
  const [visualFlowVectorData, setVisualFlowVectorData] = useState<FlowVectorFeatureCollection | null>(null);
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState(true);
  const [gifProgress, setGifProgress] = useState<number | null>(null);
  const gifCancelRef = useRef(false);
  const captureRef = useRef<(() => Promise<HTMLCanvasElement>) | null>(null);
  const flowAutoLocateRef = useRef(false);
  const [inspection, setInspection] = useState<PointInspectionResponse | null>(null);
  const [inspectionLoading, setInspectionLoading] = useState(false);
  const [inspectionError, setInspectionError] = useState<string | null>(null);
  const inspectionController = useRef<AbortController | null>(null);
  const depthFrameCacheRef = useRef<Map<number, string>>(new Map());
  const focusRegionRef = useRef<HTMLDivElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === focusRegionRef.current);
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);




  return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  const toggleFullscreen = useCallback(() => {
    const region = focusRegionRef.current;
    if (!region) return;
    if (document.fullscreenElement === region) {
      void document.exitFullscreen();
      return;
    }
    void region.requestFullscreen();
  }, []);

  const selectedTimeIndex = metadata.available_time_indices[timePosition] ?? null;
  const activeTimeIndex = layer === "time_depth" ? selectedTimeIndex : null;
  const imageUrl = useMemo(() => {
    if (layer === "time_depth") {
      if (selectedTimeIndex === null) return resultLayerUrl(runId, "max-depth");
      return (
        depthFrameCacheRef.current.get(selectedTimeIndex) ??
        resultLayerUrl(runId, "depth", selectedTimeIndex)
      );
    }
    if (layer === "grid_resolution") return resultLayerUrl(runId, "grid-resolution");
    return resultLayerUrl(runId, "max-depth");
  }, [layer, runId, selectedTimeIndex]);

  const handleFlowToggle = useCallback(() => {
    if (flowVisible) {
      flowAutoLocateRef.current = false;
      setFlowVisible(false);
      setFlowVectorData(null);
      setFlowError(null);
      setFlowRenderStats(null);
      return;
    }
    flowAutoLocateRef.current = true;
    setFlowVisible(true);
  }, [flowVisible]);

  useEffect(() => {
    if (
      !flowVisible ||
      !metadata.flow_vectors_available ||
      selectedTimeIndex === null
    ) {
      setFlowVectorData(null);
      setFlowLoading(false);
      setFlowError(null);
      return;
    }

    const controller = new AbortController();
    let disposed = false;

    const load = async () => {
      setFlowLoading(true);
      setFlowError(null);
      try {
        const current = await getFlowVectors(
          runId,
          selectedTimeIndex,
          flowViewport,
          flowStride,
          controller.signal,
        );
        if (disposed) return;

        if (current.metadata.arrow_count > 0 || !flowAutoLocateRef.current) {
          flowAutoLocateRef.current = false;
          setFlowVectorData(current);
          return;
        }

        const positions = metadata.available_time_indices
          .map((_, position) => position)
          .filter((position) => position !== timePosition)
          .sort((a, b) => Math.abs(a - timePosition) - Math.abs(b - timePosition));

        for (const position of positions) {
          const candidateIndex = metadata.available_time_indices[position];
          if (candidateIndex == null) continue;
          const candidate = await getFlowVectors(
            runId,
            candidateIndex,
            flowViewport,
          flowStride,
            controller.signal,
          );
          if (disposed) return;
          if (candidate.metadata.arrow_count > 0) {
            flowAutoLocateRef.current = false;
            setFlowVectorData(candidate);
            setTimePosition(position);
            return;
          }
        }

        flowAutoLocateRef.current = false;
        setFlowVectorData(current);
      } catch (cause: unknown) {
        if (!controller.signal.aborted && !disposed) {
          flowAutoLocateRef.current = false;
          setFlowVectorData(null);
          setFlowError(String(cause));
        }
      } finally {
        if (!controller.signal.aborted && !disposed) setFlowLoading(false);
      }
    };

    void load();
    return () => {
      disposed = true;
      controller.abort();
    };
  }, [
    flowVisible,
    metadata.available_time_indices,
    metadata.flow_vectors_available,
    runId,
    selectedTimeIndex,
    timePosition,
    flowViewport,
    flowStride,
  ]);

  useEffect(() => {
    const cache = depthFrameCacheRef.current;
    for (const cachedUrl of cache.values()) {
      if (cachedUrl.startsWith("blob:")) URL.revokeObjectURL(cachedUrl);
    }
    cache.clear();

    const indices = metadata.available_time_indices;
    if (indices.length === 0 || typeof window.fetch !== "function") return;

    const controller = new AbortController();
    const createdObjectUrls: string[] = [];
    let cursor = 0;

    const worker = async () => {
      while (!controller.signal.aborted) {
        const index = indices[cursor];
        cursor += 1;
        if (index == null) return;

        const remoteUrl = resultLayerUrl(runId, "depth", index);
        try {
          const response = await window.fetch(remoteUrl, {
            cache: "force-cache",
            signal: controller.signal,
          });
          if (!response.ok) continue;
          const blob = await response.blob();
          if (controller.signal.aborted) return;

          if (typeof URL.createObjectURL === "function") {
            const objectUrl = URL.createObjectURL(blob);
            createdObjectUrls.push(objectUrl);
            cache.set(index, objectUrl);
          } else {
            // The response is still warm in the HTTP cache even when Blob URLs
            // are unavailable (for example, some test environments).
            cache.set(index, remoteUrl);
          }
        } catch {
          if (controller.signal.aborted) return;
        }
      }
    };

    // RESULT opens on maximum depth, so use that dwell time to warm all
    // time-depth frames. Eight bounded workers keep localhost latency low
    // without recreating MapLibre or starting unbounded requests.
    void Promise.allSettled(Array.from({ length: 8 }, () => worker()));

    return () => {
      controller.abort();
      for (const objectUrl of createdObjectUrls) URL.revokeObjectURL(objectUrl);
      cache.clear();
    };
  }, [metadata.available_time_indices, runId]);

  const showTimeline =
    metadata.available_time_indices.length > 0 &&
    (layer === "time_depth" || flowVisible || isFullscreen);

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

  useEffect(() => {
    setVisualFlowVectorData(flowVectorData);
    setNextFlowVectorData(null);
    if (!flowVisible || !flowVectorData || selectedTimeIndex === null) return;
    const nextPosition = timePosition + 1;
    const nextIndex = metadata.available_time_indices[nextPosition];
    if (nextIndex == null) return;
    const controller = new AbortController();
    void getFlowVectors(runId, nextIndex, flowViewport, flowStride, controller.signal)
      .then(setNextFlowVectorData)
      .catch(() => undefined);
    return () => controller.abort();
  }, [flowVectorData, flowVisible, flowStride, flowViewport, metadata.available_time_indices, runId, selectedTimeIndex, timePosition]);

  useEffect(() => {
    if (!playing || metadata.available_time_indices.length < 2) return;
    let frame = 0;
    let started = performance.now();
    const durationMs = 1000;
    const tick = (now: number) => {
      const fraction = Math.min(1, (now - started) / durationMs);
      if (flowVectorData && nextFlowVectorData) setVisualFlowVectorData(interpolateFlow(flowVectorData, nextFlowVectorData, fraction));
      if (fraction >= 1) {
        setTimePosition((position) => {
          if (position < maxTimePosition) return position + 1;
          if (loop) return 0;
          setPlaying(false);
          return position;
        });
        started = now;
      }
      if (playing) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, flowVectorData, nextFlowVectorData, loop, metadata.available_time_indices.length]);

  const handleViewportChange = useCallback((viewport: FlowViewport, zoom: number) => {
    setFlowViewport(viewport);
    setFlowStride(strideForZoom(zoom));
  }, []);

  const exportGif = useCallback(async () => {
    const capture = captureRef.current;
    if (!capture || metadata.available_time_indices.length === 0) return;
    gifCancelRef.current = false;
    setPlaying(false);
    setLayer("time_depth");
    const count = Math.min(80, metadata.available_time_indices.length);
    const positions = Array.from({ length: count }, (_, i) => Math.round(i * (metadata.available_time_indices.length - 1) / Math.max(1, count - 1)));
    const frames: GifFrame[] = [];
    let width = 0;
    let height = 0;
    for (let i = 0; i < positions.length; i += 1) {
      if (gifCancelRef.current) break;
      const position = positions[i];
      setTimePosition(position);
      await new Promise((resolve) => window.setTimeout(resolve, 100));
      const source = await capture();
      const scale = Math.min(1, 640 / source.width, 480 / source.height);
      width = Math.max(1, Math.round(source.width * scale));
      height = Math.max(1, Math.round(source.height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height + 28;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Canvas 2D context is unavailable");
      ctx.drawImage(source, 0, 0, width, height);
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, height, width, 28);
      ctx.fillStyle = "#111827";
      ctx.font = "14px sans-serif";
      ctx.fillText(elapsedLabel(metadata.time_values, metadata.available_time_indices[position] ?? 0), 10, height + 19);
      frames.push({ rgba: ctx.getImageData(0, 0, width, height + 28).data, delayCs: 10 });
      setGifProgress((i + 1) / positions.length);
    }
    if (!gifCancelRef.current && frames.length > 0) {
      const blob = encodeGif(width, height + 28, frames, loop);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `flood-result-${runId}.gif`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    setGifProgress(null);
  }, [loop, metadata.available_time_indices, metadata.time_values, runId]);

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

      <div className="result-focus-region" ref={focusRegionRef} data-testid="result-focus-region">
        <div className="result-focus-controls" data-testid="result-focus-controls">
          <div className="result-focus-control-row">
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
                onClick={handleFlowToggle}
              >
                流れベクトル
              </button>
            </div>

            <button
              type="button"
              className="result-fullscreen-button"
              onClick={toggleFullscreen}
              aria-label={isFullscreen ? "全画面表示を終了" : "地図を全画面表示"}
            >
              {isFullscreen ? "全画面を終了" : "全画面"}
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
              <button type="button" onClick={() => setPlaying((value) => !value)} aria-label={playing ? "一時停止" : "再生"}>
                {playing ? "Pause" : "Play"}
              </button>
              <label>
                <input type="checkbox" checked={loop} onChange={(event) => setLoop(event.target.checked)} />
                Loop
              </label>
              <button type="button" onClick={() => void exportGif()} disabled={gifProgress !== null}>GIF</button>
              {gifProgress !== null && (
                <>
                  <progress max={1} value={gifProgress} />
                  <button type="button" onClick={() => { gifCancelRef.current = true; }}>Cancel</button>
                </>
              )}
              <span className="result-vector-note">GIFではCORS制約を避けるため背景地図を省略します。</span>
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
        </div>

        <div className="result-layout">
          <div className="result-map-panel">
            <ResultMap
              metadata={metadata}
              imageUrl={imageUrl}
              flowVectorData={visualFlowVectorData}
              backgroundOpacity={(100 - backgroundTransparency) / 100}
              mapLabel={mapLabel}
              onInspect={handleInspect}
              onFlowRenderStats={setFlowRenderStats}
              onViewportChange={handleViewportChange}
              onCaptureReady={(capture) => { captureRef.current = capture; }}
            />
          </div>

          <aside className="result-sidebar">
            <section className="result-point-panel">
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

            <section className="result-legend result-legend-sidebar" aria-label={layer === "grid_resolution" ? "計算格子の凡例" : "浸水深の凡例"}>
              {layer !== "grid_resolution" ? (
                <>
                  <strong>{layer === "max_depth" ? "最大浸水深 (m)" : "浸水深 (m)"}</strong>
                  {metadata.depth_legend?.map((item) => (
                    <span key={item.label}>
                      <i style={{ backgroundColor: item.color }} aria-hidden="true" />
                      {item.label}
                    </span>
                  ))}

                </>
              ) : (
                <>
                  <strong>格子解像度</strong>
                  {GRID_LEGEND.map(([label, color]) => (
                    <span key={label}>
                      <i style={{ backgroundColor: color }} aria-hidden="true" />
                      {label}
                    </span>
                  ))}
                  <span className="result-vector-note">実計算格子: 1 m</span>
                </>
              )}
            </section>

            {flowVisible && metadata.flow_vectors_available && (
              <section className="result-legend result-legend-sidebar result-flow-legend" aria-label="流速の凡例">
                <strong>流速 (m/s)</strong>
                {FLOW_SPEED_LEGEND.map(([label, color]) => (
                  <span key={label}>
                    <i style={{ backgroundColor: color }} aria-hidden="true" />
                    {label}
                  </span>
                ))}
                <span className="result-vector-note">矢印の向き: 流向 / 色: 流速</span>
                {flowLoading && <span className="result-vector-note">流れベクトルを読み込み中…</span>}
                {flowError && <span className="result-warning">流れベクトルを読み込めません: {flowError}</span>}
                {!flowLoading && !flowError && flowVectorData && (
                  <>
                    <span className="result-vector-note">
                      GeoJSON矢印: {flowVectorData.metadata.arrow_count.toLocaleString()}本
                    </span>
                    {flowRenderStats && (
                      <span className="result-vector-note">
                        MapLibre source: {flowRenderStats.sourceFeatureCount.toLocaleString()} /
                        line描画: {flowRenderStats.renderedFeatureCount.toLocaleString()} /
                        SVG描画: {flowRenderStats.svgArrowCount.toLocaleString()}
                      </span>
                    )}
                    {flowRenderStats &&
                      flowVectorData.metadata.arrow_count > 0 &&
                      flowRenderStats.renderedFeatureCount === 0 &&
                      flowRenderStats.svgArrowCount === 0 && (
                        <span className="result-warning">
                          GeoJSONは存在しますが、現在のMapLibre表示範囲では描画featureが0件です。
                          <br />
                          layer順: {flowRenderStats.layerOrder.join(" > ")}
                          <br />
                          feature範囲: {flowRenderStats.featureBounds
                            ? flowRenderStats.featureBounds.map((value) => value.toFixed(6)).join(", ")
                            : "—"}
                          <br />
                          map範囲: {flowRenderStats.mapBounds
                            .map((value) => value.toFixed(6))
                            .join(", ")}
                        </span>
                      )}
                  </>
                )}
                {!flowLoading &&
                  !flowError &&
                  flowVectorData &&
                  flowVectorData.metadata.arrow_count === 0 && (
                    <span className="result-vector-note">この時刻には表示可能な流れがありません。</span>
                  )}
              </section>
            )}

            <div className="result-sidebar-extra">
              <details>
                <summary>結果概要</summary>
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
              </details>

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
                <p>Rainfall: <code>{JSON.stringify(runSummary.rainfall_source)}</code></p>
                <p>Elevation: <code>{JSON.stringify(runSummary.elevation_source_summary)}</code></p>
                <p>Elevation provider counts: <code>{JSON.stringify(runSummary.elevation_provider_counts)}</code></p>
                <p>Manning: <code>{JSON.stringify(runSummary.manning_defaults)}</code></p>
                <p>Boundary: {runSummary.boundary_policy}</p>
                <p>Roof-rain mass diagnostic: <code>{JSON.stringify(runSummary.roof_rain_mass_diagnostic)}</code></p>
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
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}