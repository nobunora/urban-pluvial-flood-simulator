import { useEffect, useMemo, useState } from "react";

import {
  cancelRun,
  createRun,
  getHealth,
  getResultMetadata,
  getRecentRainfallRanking,
  getRun,
  importResult,
  type AnalysisArea,
  type ResultMetadataResponse,
  type RecentRainfallRankingResponse,
  type RunStatusResponse,
} from "../api/client";
import ResultPanel from "../result/ResultPanel";
import LocationSearch from "./LocationSearch";
import RunProgress from "./RunProgress";
import SetupMap from "./SetupMap";
import "./smoke.css";

const TERMINAL = new Set<RunStatusResponse["state"]>(["COMPLETE", "FAILED", "CANCELLED"]);
const DEFAULT_LAT = 35.681236;
const DEFAULT_LON = 139.767125;

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

export default function SmokeApp() {
  const [lat, setLat] = useState(String(DEFAULT_LAT));
  const [lon, setLon] = useState(String(DEFAULT_LON));
  const [halfSize, setHalfSize] = useState("250");
  const [intensity, setIntensity] = useState("150");
  const [duration, setDuration] = useState("20");
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
  const [rainfallRanking, setRainfallRanking] = useState<RecentRainfallRankingResponse | null>(null);

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
      ![250, 500, 1000, 2000].includes(halfValue)
    ) {
      return null;
    }
    return squareArea(parsedLat, parsedLon, halfValue);
  }, [lat, lon, halfSize]);

  const runActive = status !== null && !TERMINAL.has(status.state);
  const setupLocked =
    busy ||
    (runId !== null && status?.state !== "FAILED" && status?.state !== "CANCELLED");

  useEffect(() => {
    getHealth()
      .then((health) => setBackend(`${health.status} / app ${health.application_version}`))
      .catch((cause: unknown) => setBackend(`NG: ${String(cause)}`));
  }, []);

  useEffect(() => {
    getRecentRainfallRanking().then(setRainfallRanking).catch(() => setRainfallRanking(null));
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
    try {
      const created = await createRun({
        analysis_area: area,
        requested_accuracy_mode: "full_1m",
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

  const rainfallSummary = `${intensity} mm/h × ${duration}分`;

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
            <h2>保存済み結果</h2>
            <label className="result-import-control">
              解析結果を読み込んでレビュー
              <input
                type="file"
                accept=".zip,application/zip"
                disabled={setupLocked || importing}
                onChange={(event) => void handleImport(event.target.files?.[0])}
              />
            </label>
            {importing && <p>解析結果を読み込んでいます…</p>}
            <hr />
            <h2>1. 条件</h2>
            <LocationSearch disabled={setupLocked} onSelect={updateLocation} />
            <div className="location-manual-divider">
              <span>または緯度経度を直接入力</span>
            </div>
            <label>
              緯度
              <input
                value={lat}
                disabled={setupLocked}
                onChange={(event) => {
                  setLat(event.target.value);
                }}
              />
            </label>
            <label>
              経度
              <input
                value={lon}
                disabled={setupLocked}
                onChange={(event) => {
                  setLon(event.target.value);
                }}
              />
            </label>
            <label>
              範囲
              <select
                value={halfSize}
                disabled={setupLocked}
                onChange={(event) => {
                  setHalfSize(event.target.value);
                }}
              >
                <option value="250">±250 m</option>
                <option value="500">±500 m</option>
                <option value="1000">±1000 m</option>
                <option value="2000">±2000 m</option>
              </select>
            </label>
            <label>雨量強度 (mm/h)<input value={intensity} disabled={setupLocked} onChange={(event) => setIntensity(event.target.value)} /></label>
            <label>継続時間 (min)<input value={duration} disabled={setupLocked} onChange={(event) => setDuration(event.target.value)} /></label>
            {rainfallRanking && rainfallRanking.events.length > 0 && (
              <section className="rainfall-ranking" aria-label="都市型豪雨の降雨リスト">
                <h3>都市型豪雨の降雨リスト</h3>
                <ol>
                  {rainfallRanking.events.map((event) => (
                    <li key={event.event_id}>
                      <button
                        type="button"
                        disabled={setupLocked}
                        onClick={() => {
                          setIntensity(String(Number(event.intensity_mm_per_h.toFixed(1))));
                          setDuration(String(event.duration_minutes));
                          setLon(event.station_lon_deg.toFixed(6));
                          setLat(event.station_lat_deg.toFixed(6));
                        }}
                      >
                        <span className="rainfall-event-place">
                          <strong>{event.event_date_or_datetime_metadata ?? "年不明"}年</strong>
                          {event.station_name}
                        </span>
                        <span className="rainfall-event-amount">
                          1h降水量 {event.intensity_mm_per_h.toFixed(1)} mm
                          {event.damage_location_name && ` ・ ${event.damage_location_name}`}
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
              </section>
            )}
            {rainfallRanking && (
              <p className="rainfall-ranking-note">{rainfallRanking.coverage_note}</p>
            )}
            <div className="smoke-actions">
              <button className="analysis-start-button" disabled={!area || setupLocked} onClick={() => void handleRun()}>
                解析開始
              </button>
            </div>
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
                <dl>
                  <dt>範囲</dt><dd>{area.width_m} × {area.height_m} m</dd>
                  <dt>セル数</dt><dd>{area.area_m2.toLocaleString()}</dd>
                </dl>
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
