import { useEffect, useMemo, useState } from "react";

import {
  cancelRun,
  createRun,
  estimateResources,
  getHealth,
  getResultMetadata,
  getRun,
  type AnalysisArea,
  type ResourceEstimateResponse,
  type ResultMetadataResponse,
  type RunStatusResponse,
} from "../api/client";
import ResultPanel from "../result/ResultPanel";
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
  const [intensity, setIntensity] = useState("50");
  const [duration, setDuration] = useState("60");
  const [backend, setBackend] = useState("確認中…");
  const [estimate, setEstimate] = useState<ResourceEstimateResponse | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<RunStatusResponse | null>(null);
  const [stageObservedAtMs, setStageObservedAtMs] = useState<number | null>(null);
  const [lastPollAtMs, setLastPollAtMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resultMetadata, setResultMetadata] = useState<ResultMetadataResponse | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
    setEstimate(null);
  };

  const handleEstimate = async () => {
    if (!area) return;
    setBusy(true);
    setError(null);
    try {
      setEstimate(await estimateResources(area));
    } catch (cause: unknown) {
      setError(String(cause));
    } finally {
      setBusy(false);
    }
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
    try {
      await cancelRun(runId);
      const next = await getRun(runId);
      setStatus(next);
      setLastPollAtMs(Date.now());
    } catch (cause: unknown) {
      setError(String(cause));
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

  const rainfallSummary = `${intensity} mm/h × ${duration}分`;

  return (
    <main className="smoke-shell">
      <header>
        <div>
          <h1>Urban Pluvial Flood Simulator</h1>
          <p className="smoke-kicker">ローカルレビュー版 — Full 1 m</p>
          <p>
            Full 1 mの条件入力からSFINCS実行、最大浸水深の結果地図までをレビューできます。Adaptiveはまだ無効です。
          </p>
        </div>
        <div className="smoke-health">Backend: {backend}</div>
      </header>

      {!resultMetadata && (
        <section className="smoke-grid">
          <div className="smoke-card">
            <h2>1. 条件</h2>
            <label>
              緯度
              <input
                value={lat}
                disabled={setupLocked}
                onChange={(event) => {
                  setLat(event.target.value);
                  setEstimate(null);
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
                  setEstimate(null);
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
                  setEstimate(null);
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
            <p>精度: <strong>Full 1 m</strong>（Adaptiveはレビュー版では無効）</p>
            <div className="smoke-actions">
              <button disabled={!area || setupLocked} onClick={() => void handleEstimate()}>負荷を見積る</button>
              <button disabled={!area || busy || runActive} onClick={() => void handleRun()}>
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
                  <dt>セル数</dt><dd>{area.area_m2.toLocaleString()} (Full 1 m相当)</dd>
                </dl>
              ) : <p className="smoke-error">入力値を確認してください。</p>}

              {estimate && (
                <div className="smoke-result">
                  <h3>見積り</h3>
                  <p>{estimate.full_1m_equivalent_cells.toLocaleString()} cells / 負荷 {estimate.runtime_class}</p>
                  {estimate.warnings.map((warning) => <p key={warning} className="smoke-warning">{warning}</p>)}
                </div>
              )}

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
        <ResultPanel
          runId={runId}
          metadata={resultMetadata}
          rainfallSummary={rainfallSummary}
          onNewAnalysis={handleNewAnalysis}
        />
      )}

      <footer>
        レビュー対象: 地図による場所・範囲指定 / Full 1 m実行 / 工程・取得データ表示 / SFINCS稼働表示 / 最大浸水深地図・地点確認 / 下水・浸透は未考慮 / 雨は解析範囲内で一様 / 公的な洪水予報・避難情報ではありません
      </footer>
    </main>
  );
}
