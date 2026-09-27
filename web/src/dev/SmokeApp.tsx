import { useEffect, useMemo, useRef, useState } from "react";

import {
  cancelRun,
  createElevationPreview,
  createRun,
  getAppConfig,
  getHealth,
  getResultMetadata,
  getRun,
  importResult,
  openDemoResult,
  type AppConfigResponse,
  type AnalysisArea,
  type ElevationPreviewResponse,
  type ResultMetadataResponse,
  type RunStatusResponse,
} from "../api/client";
import ResultPanel from "../result/ResultPanel";
import ElevationPreviewPanel from "./ElevationPreviewPanel";
import LocationSearch from "./LocationSearch";
import RunProgress from "./RunProgress";
import SetupMap from "./SetupMap";
import "./smoke.css";

const TERMINAL = new Set<RunStatusResponse["state"]>(["COMPLETE", "FAILED", "CANCELLED"]);
const ACTIVE_RUN_STORAGE_KEY = "urban-pluvial-flood-simulator.active-run-id";
const RUN_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DEFAULT_LAT = 35.681236;
const DEFAULT_LON = 139.767125;
const STATIC_RAINFALL_RANKING = [
  { eventId: "2025-yokkaichi", year: "2025", city: "四日市", lon: 136.6208, lat: 34.9665, intensity: 123.5, duration: 60 },
  { eventId: "2026-chiba", year: "2026", city: "千葉", lon: 140.1141, lat: 35.6129, intensity: 115, duration: 60 },
  { eventId: "2019-saga", year: "2019", city: "佐賀", lon: 130.2975, lat: 33.2642, intensity: 110, duration: 60 },
  { eventId: "2026-nagoya", year: "2026", city: "名古屋", lon: 136.9196, lat: 35.1569, intensity: 104.5, duration: 60 },
  { eventId: "2000-nagoya", year: "2000", city: "名古屋", lon: 136.9555, lat: 35.1028, intensity: 97, duration: 60 },
] as const;

function squareArea(lat: number, lon: number, halfSizeM: number): AnalysisArea {
  const metresPerDegree = 111_320;
  const latDelta = halfSizeM / metresPerDegree;
  const cosLat = Math.max(Math.cos((lat * Math.PI) / 180), 0.01);
  const lonDelta = halfSizeM / (metresPerDegree * cosLat);
  const size = halfSizeM * 2;
  return {
    mode: "preset_square",
    center: { lat_deg: lat, lon_deg: lon },
    bounds: {
      west_deg: lon - lonDelta,
      south_deg: lat - latDelta,
      east_deg: lon + lonDelta,
      north_deg: lat + latDelta,
    },
    width_m: size,
    height_m: size,
    area_m2: size * size,
  };
}

function parseNumber(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function recommendedMinimumBlockSize(halfSizeM: number): 1 | 2 | 4 {
  if (halfSizeM <= 500) return 1;
  if (halfSizeM <= 1000) return 2;
  return 4;
}

function estimatedPeakMemoryRange(cellCount: number): string {
  // This deliberately broad range covers the Python preprocessing arrays,
  // duplicated conversion buffers and the SFINCS working set. It is a setup
  // warning, not an operating-system reservation or a hard upper bound.
  const gibibyte = 1024 ** 3;
  const lowerBytes = 0.5 * gibibyte + cellCount * 512;
  const upperBytes = gibibyte + cellCount * 1024;
  const format = (bytes: number) => {
    const gibibytes = bytes / gibibyte;
    return gibibytes < 10 ? gibibytes.toFixed(1) : String(Math.ceil(gibibytes));
  };
  return `約 ${format(lowerBytes)}〜${format(upperBytes)} GB`;
}

export default function SmokeApp() {
  const [lat, setLat] = useState(String(DEFAULT_LAT));
  const [lon, setLon] = useState(String(DEFAULT_LON));
  const [halfSize, setHalfSize] = useState("250");
  const [intensity, setIntensity] = useState("150");
  const [duration, setDuration] = useState("20");
  const [minimumBlockSizeChoice, setMinimumBlockSizeChoice] = useState<"auto" | "1" | "2" | "4">("auto");
  const [backend, setBackend] = useState("確認中…");
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<RunStatusResponse | null>(null);
  const [stageObservedAtMs, setStageObservedAtMs] = useState<number | null>(null);
  const [lastPollAtMs, setLastPollAtMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resultMetadata, setResultMetadata] = useState<ResultMetadataResponse | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [appConfig, setAppConfig] = useState<AppConfigResponse>({
    mode: "local",
    allow_run: true,
    allow_result_import: true,
    download_url: "https://github.com/nobunora/urban-pluvial-flood-simulator/releases/latest",
    demo_result_event_ids: [],
  });
  const [elevationPreview, setElevationPreview] = useState<ElevationPreviewResponse | null>(null);
  const [elevationLoading, setElevationLoading] = useState(false);
  const [sampleChoiceEventId, setSampleChoiceEventId] = useState<string | null>(null);
  const importInputRef = useRef<HTMLInputElement>(null);

  const latValue = parseNumber(lat);
  const lonValue = parseNumber(lon);
  const mapCenterLat =
    latValue !== null && latValue >= -90 && latValue <= 90 ? latValue : DEFAULT_LAT;
  const mapCenterLon =
    lonValue !== null && lonValue >= -180 && lonValue <= 180 ? lonValue : DEFAULT_LON;

  const area = useMemo(() => {
    const parsedLat = parseNumber(lat);
    const parsedLon = parseNumber(lon);
    const halfValue = parseNumber(halfSize);
    if (
      parsedLat === null ||
      parsedLon === null ||
      halfValue === null ||
      parsedLat < -90 ||
      parsedLat > 90 ||
      parsedLon < -180 ||
      parsedLon > 180 ||
      ![250, 500, 1000, 2000, 4000].includes(halfValue)
    ) {
      return null;
    }
    return squareArea(parsedLat, parsedLon, halfValue);
  }, [lat, lon, halfSize]);
  const suggestedMinimumBlockSize = recommendedMinimumBlockSize(parseNumber(halfSize) ?? 500);
  const gridCellSizeM = Number(
    minimumBlockSizeChoice === "auto" ? suggestedMinimumBlockSize : minimumBlockSizeChoice,
  ) as 1 | 2 | 4;
  const gridCellCount = area
    ? Math.round(area.area_m2 / (gridCellSizeM * gridCellSizeM))
    : null;
  const peakMemoryEstimate = gridCellCount === null
    ? null
    : estimatedPeakMemoryRange(gridCellCount);

  const runActive = status !== null && !TERMINAL.has(status.state);
  const setupLocked =
    busy ||
    elevationLoading ||
    (runId !== null && status?.state !== "FAILED" && status?.state !== "CANCELLED");

  useEffect(() => {
    setElevationPreview(null);
  }, [lat, lon, halfSize, gridCellSizeM]);

  useEffect(() => {
    getHealth()
      .then((health) => setBackend(`${health.status} / app ${health.application_version}`))
      .catch((cause: unknown) => setBackend(`NG: ${String(cause)}`));
  }, []);

  useEffect(() => {
    const savedRunId = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    if (savedRunId && RUN_ID_PATTERN.test(savedRunId)) {
      setRunId(savedRunId);
    }
  }, []);

  useEffect(() => {
    if (runId) {
      window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, runId);
    } else {
      window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
    }
  }, [runId]);

  useEffect(() => {
    getAppConfig().then(setAppConfig).catch((cause: unknown) => {
      setError(`アプリ設定を取得できません: ${String(cause)}`);
    });
  }, []);

  useEffect(() => {
    if (!status) {
      setStageObservedAtMs(null);
      return;
    }
    setStageObservedAtMs(Date.now());
  }, [status?.stage_code]);

  useEffect(() => {
    if (!runId || (status && TERMINAL.has(status.state))) return;
    let closed = false;
    const refresh = async () => {
      try {
        const next = await getRun(runId);
        if (!closed) {
          setStatus(next);
          setLastPollAtMs(Date.now());
        }
      } catch (cause: unknown) {
        if (!closed) setError(String(cause));
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => {
      closed = true;
      window.clearInterval(timer);
    };
  }, [runId, status?.state]);

  useEffect(() => {
    if (!runId || status?.state !== "COMPLETE" || resultMetadata) return;
    let closed = false;
    setResultError(null);
    getResultMetadata(runId)
      .then((metadata) => {
        if (!closed) setResultMetadata(metadata);
      })
      .catch((cause: unknown) => {
        if (!closed) setResultError(String(cause));
      });
    return () => {
      closed = true;
    };
  }, [resultMetadata, runId, status]);

  const updateLocation = (nextLon: number, nextLat: number) => {
    if (setupLocked) return;
    setLat(nextLat.toFixed(6));
    setLon(nextLon.toFixed(6));
  };

  const handleRun = async () => {
    if (!area) return;
    const intensityValue = parseNumber(intensity);
    const durationValue = parseNumber(duration);
    if (
      intensityValue === null ||
      durationValue === null ||
      intensityValue <= 0 ||
      intensityValue > 500 ||
      !Number.isInteger(durationValue) ||
      durationValue < 1 ||
      durationValue > 10080
    ) {
      setError("雨量強度または継続時間が不正です。");
      return;
    }
    setBusy(true);
    setError(null);
    setRunId(null);
    setStatus(null);
    setStageObservedAtMs(null);
    setLastPollAtMs(null);
    setResultMetadata(null);
    setResultError(null);
    setElevationPreview(null);
    try {
      const created = await createRun({
        analysis_area: area,
        requested_accuracy_mode: "uniform",
        grid_cell_size_m: gridCellSizeM,
        adaptive_max_block_size_m: gridCellSizeM,
        rainfall: {
          kind: "constant",
          intensity_mm_per_h: intensityValue,
          duration_minutes: durationValue,
        },
      });
      setRunId(created.run_id);
    } catch (cause: unknown) {
      setError(String(cause));
    } finally {
      setBusy(false);
    }
  };

  const handleElevationPreview = async () => {
    if (!area) return;
    setElevationLoading(true);
    setError(null);
    try {
      setElevationPreview(await createElevationPreview(area, gridCellSizeM));
    } catch (cause: unknown) {
      setError(String(cause));
    } finally {
      setElevationLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!runId) return;
    setError(null);
    // Cancellation is best-effort from the browser's point of view. The
    // backend may terminate the SFINCS process quickly enough to close/reset
    // the in-flight HTTP connection on some local Windows setups. Do not turn
    // that transport symptom into a false cancellation failure; reconcile
    // state through the normal status endpoint.
    try {
      await cancelRun(runId);
    } catch {
      // Status reconciliation below is authoritative.
    }
    try {
      const next = await getRun(runId);
      setStatus(next);
      setLastPollAtMs(Date.now());
    } catch (cause: unknown) {
      setError(`キャンセル後の状態確認に失敗しました: ${String(cause)}`);
    }
  };

  const handleNewAnalysis = () => {
    setRunId(null);
    setStatus(null);
    setStageObservedAtMs(null);
    setLastPollAtMs(null);
    setResultMetadata(null);
    setResultError(null);
    setError(null);
  };

  const handleImport = async (file: File | undefined) => {
    if (!file) return;
    setImporting(true);
    setError(null);
    setResultError(null);
    try {
      const imported = await importResult(file);
      const [nextStatus, metadata] = await Promise.all([
        getRun(imported.run_id),
        getResultMetadata(imported.run_id),
      ]);
      setRunId(imported.run_id);
      setStatus(nextStatus);
      setResultMetadata(metadata);
    } catch (cause: unknown) {
      setError(String(cause));
    } finally {
      setImporting(false);
    }
  };

  const handleOpenDemoResult = async (eventId: string) => {
    setImporting(true);
    setSampleChoiceEventId(null);
    setError(null);
    setResultError(null);
    try {
      const imported = await openDemoResult(eventId);
      const [nextStatus, metadata] = await Promise.all([
        getRun(imported.run_id),
        getResultMetadata(imported.run_id),
      ]);
      setRunId(imported.run_id);
      setStatus(nextStatus);
      setResultMetadata(metadata);
    } catch (cause: unknown) {
      setError(String(cause));
    } finally {
      setImporting(false);
    }
  };

  const applySampleCondition = (event: (typeof STATIC_RAINFALL_RANKING)[number]) => {
    setIntensity(String(event.intensity));
    setDuration(String(event.duration));
    setLon(event.lon.toFixed(6));
    setLat(event.lat.toFixed(6));
    setHalfSize("2000");
    setMinimumBlockSizeChoice("auto");
  };

  const rainfallSummary = `${intensity} mm/h × ${duration}分`;
  const selectedSample = STATIC_RAINFALL_RANKING.find(
    (event) => event.eventId === sampleChoiceEventId,
  );
  const selectedSampleResultAvailable = selectedSample
    ? appConfig.demo_result_event_ids.includes(selectedSample.eventId)
    : false;

  return (
    <main className="smoke-shell">
      <header>
        <div>
          <h1>Urban Pluvial Flood Simulator</h1>
          <p className="smoke-kicker">ローカルレビュー版</p>
        </div>
        <div className="smoke-health">Backend: {backend}</div>
      </header>

      {!resultMetadata && (
        <section className="smoke-grid">
          <div className="smoke-card">
            {importing && <p>解析済み結果を読み込んでいます…</p>}
            <section className="rainfall-ranking" aria-label="サンプルまたは読込み">
              <h2>サンプルまたは読込み</h2>
              {appConfig.allow_result_import && (
                <>
                  <button type="button" className="result-import-button" disabled={setupLocked || importing} onClick={() => importInputRef.current?.click()}>
                    ファイルから読込
                  </button>
                  <input
                    ref={importInputRef}
                    type="file"
                    aria-label="解析済みデータをファイルから読み込む"
                    accept=".zip,application/zip"
                    className="result-import-input"
                    disabled={setupLocked || importing}
                    onChange={(event) => void handleImport(event.target.files?.[0])}
                  />
                </>
              )}
              <ol>
                {STATIC_RAINFALL_RANKING.map((event) => (
                  <li key={event.eventId}>
                    <button
                      type="button"
                      disabled={setupLocked}
                      onClick={() => setSampleChoiceEventId(event.eventId)}
                    >
                      <small>{event.year}</small>
                      <strong>{event.city}</strong>
                      <span>{event.intensity} mm/h</span>
                    </button>
                  </li>
                ))}
              </ol>
              <hr />
            </section>
            <h2>1. 条件</h2>
            <LocationSearch disabled={setupLocked} onSelect={updateLocation} />
            <div className="location-manual-divider">
              <span>または緯度経度を直接入力</span>
            </div>
            <div className="compact-input-grid">
              <label>緯度<input value={lat} disabled={setupLocked} onChange={(event) => setLat(event.target.value)} /></label>
              <label>経度<input value={lon} disabled={setupLocked} onChange={(event) => setLon(event.target.value)} /></label>
              <label>範囲<select value={halfSize} disabled={setupLocked} onChange={(event) => { setHalfSize(event.target.value); setMinimumBlockSizeChoice("auto"); }}><option value="250">±250 m</option><option value="500">±500 m</option><option value="1000">±1000 m</option><option value="2000">±2000 m</option><option value="4000">±4000 m</option></select></label>
              <label>最小ブロック<select value={minimumBlockSizeChoice} disabled={setupLocked} onChange={(event) => setMinimumBlockSizeChoice(event.target.value as "auto" | "1" | "2" | "4")}><option value="auto">自動 ({suggestedMinimumBlockSize} m)</option><option value="1">1 m</option><option value="2">2 m</option><option value="4">4 m</option></select></label>
              <label>雨量強度 (mm/h)<input value={intensity} disabled={setupLocked} onChange={(event) => setIntensity(event.target.value)} /></label>
              <label>継続時間 (min)<input value={duration} disabled={setupLocked} onChange={(event) => setDuration(event.target.value)} /></label>
            </div>
            <div className="smoke-actions">
              {appConfig.allow_run ? (
                <>
                  <button className="analysis-start-button" disabled={!area || setupLocked} onClick={() => void handleRun()}>
                    解析開始
                  </button>
                  <button className="elevation-preview-button" disabled={!area || setupLocked} onClick={() => void handleElevationPreview()}>
                    {elevationLoading ? "標高を取得中…" : "標高のみ取得"}
                  </button>
                </>
              ) : (
                <a className="analysis-start-button download-app-link" href={appConfig.download_url}>
                  Windows版をダウンロード
                </a>
              )}
            </div>
            {selectedSample && (
              <div className="scenario-result-dialog" role="dialog" aria-modal="true" aria-labelledby="scenario-result-title">
                <div className="scenario-result-dialog-card">
                  <h3 id="scenario-result-title">{selectedSample.year} {selectedSample.city}</h3>
                  <p>{selectedSample.intensity} mm/h × {selectedSample.duration}分をどう使いますか？</p>
                  <div className="scenario-result-dialog-actions">
                    <button
                      type="button"
                      onClick={() => {
                        applySampleCondition(selectedSample);
                        setSampleChoiceEventId(null);
                      }}
                    >
                      解析条件に反映
                    </button>
                    <button
                      type="button"
                      disabled={!selectedSampleResultAvailable || importing}
                      onClick={() => void handleOpenDemoResult(selectedSample.eventId)}
                    >
                      解析済みデータを読み込む
                    </button>
                    {!selectedSampleResultAvailable && (
                      <p className="sample-result-unavailable">このサンプルの解析済みデータは現在ありません。</p>
                    )}
                    <button type="button" onClick={() => setSampleChoiceEventId(null)}>
                      キャンセル
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="smoke-main-column">
            <div className="smoke-card smoke-map-card">
              <h2>場所と解析範囲</h2>
              <SetupMap
                centerLat={mapCenterLat}
                centerLon={mapCenterLon}
                area={area}
                disabled={setupLocked}
                onSelect={updateLocation}
              />
            </div>

            <div className="smoke-card">
              <h2>2. 実行状態</h2>
              {area ? (
                <>
                  <dl>
                    <dt>範囲</dt><dd>{area.width_m} × {area.height_m} m</dd>
                    <dt>セル数</dt><dd>{gridCellCount?.toLocaleString()}</dd>
                    <dt>概算ピークメモリ</dt><dd>{peakMemoryEstimate}</dd>
                  </dl>
                  <p className="memory-estimate-note">
                    前処理とSFINCS計算を含む目安です。地物数や実行環境により増減します。
                  </p>
                </>
              ) : <p className="smoke-error">入力値を確認してください。</p>}

              {runId && <p><strong>Run ID:</strong> <code>{runId}</code></p>}
              <RunProgress
                status={status}
                stageObservedAtMs={stageObservedAtMs}
                lastPollAtMs={lastPollAtMs}
              />
              {status?.failure_code && (
                <p className="smoke-error">{status.failure_code}: {status.failure_message}</p>
              )}
              {status && !TERMINAL.has(status.state) && (
                <button onClick={() => void handleCancel()}>キャンセル</button>
              )}
              {status?.state === "COMPLETE" && !resultMetadata && !resultError && (
                <p>結果地図を読み込んでいます…</p>
              )}
              {resultError && <pre className="smoke-error">{resultError}</pre>}
              {error && <pre className="smoke-error">{error}</pre>}
            </div>
            {elevationPreview && (
              <ElevationPreviewPanel
                preview={elevationPreview}
                onRun={() => void handleRun()}
                onClose={() => setElevationPreview(null)}
              />
            )}
          </div>
        </section>
      )}

      {runId && resultMetadata && (
        <>
          <ResultPanel
            runId={runId}
            metadata={resultMetadata}
            rainfallSummary={rainfallSummary}
            onNewAnalysis={handleNewAnalysis}
          />
          <section className="smoke-card result-run-log" aria-label="完了した解析の処理ログ">
            <RunProgress
              status={status}
              stageObservedAtMs={stageObservedAtMs}
              lastPollAtMs={lastPollAtMs}
            />
          </section>
        </>
      )}

      <footer>
        レビュー対象: 地図による場所・範囲指定 / 工程・取得データ表示 / SFINCS稼働表示 / 最大浸水深地図・地点確認 / 下水・浸透は未考慮 / 雨は解析範囲内で一様 / 公的な洪水予報・避難情報ではありません
      </footer>
    </main>
  );
}
