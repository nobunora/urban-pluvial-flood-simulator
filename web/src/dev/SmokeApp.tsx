import { useEffect, useMemo, useState } from "react";

import {
  cancelRun,
  createRun,
  estimateResources,
  getHealth,
  getRun,
  type AnalysisArea,
  type ResourceEstimateResponse,
  type RunStatusResponse,
} from "../api/client";
import "./smoke.css";

const TERMINAL = new Set<RunStatusResponse["state"]>(["COMPLETE", "FAILED", "CANCELLED"]);

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
  const [lat, setLat] = useState("35.681236");
  const [lon, setLon] = useState("139.767125");
  const [halfSize, setHalfSize] = useState("250");
  const [intensity, setIntensity] = useState("50");
  const [duration, setDuration] = useState("60");
  const [backend, setBackend] = useState("確認中…");
  const [estimate, setEstimate] = useState<ResourceEstimateResponse | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<RunStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const area = useMemo(() => {
    const latValue = parseNumber(lat);
    const lonValue = parseNumber(lon);
    const halfValue = parseNumber(halfSize);
    if (
      latValue === null ||
      lonValue === null ||
      halfValue === null ||
      latValue < -90 ||
      latValue > 90 ||
      lonValue < -180 ||
      lonValue > 180 ||
      ![250, 500, 1000, 2000].includes(halfValue)
    ) {
      return null;
    }
    return squareArea(latValue, lonValue, halfValue);
  }, [lat, lon, halfSize]);

  useEffect(() => {
    getHealth()
      .then((health) => setBackend(`${health.status} / app ${health.application_version}`))
      .catch((cause: unknown) => setBackend(`NG: ${String(cause)}`));
  }, []);

  useEffect(() => {
    if (!runId || (status && TERMINAL.has(status.state))) return;
    let closed = false;
    const refresh = async () => {
      try {
        const next = await getRun(runId);
        if (!closed) setStatus(next);
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
  }, [runId, status]);

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
    setStatus(null);
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
      setStatus(await getRun(runId));
    } catch (cause: unknown) {
      setError(String(cause));
    }
  };

  return (
    <main className="smoke-shell">
      <header>
        <div>
          <h1>Urban Pluvial Flood Simulator</h1>
          <p className="smoke-kicker">開発用 Full 1 m 動作確認</p>
        </div>
        <div className="smoke-health">Backend: {backend}</div>
      </header>

      <section className="smoke-grid">
        <div className="smoke-card">
          <h2>1. 入力</h2>
          <label>緯度<input value={lat} onChange={(event) => setLat(event.target.value)} /></label>
          <label>経度<input value={lon} onChange={(event) => setLon(event.target.value)} /></label>
          <label>範囲
            <select value={halfSize} onChange={(event) => setHalfSize(event.target.value)}>
              <option value="250">±250 m</option>
              <option value="500">±500 m</option>
              <option value="1000">±1000 m</option>
              <option value="2000">±2000 m</option>
            </select>
          </label>
          <label>雨量強度 (mm/h)<input value={intensity} onChange={(event) => setIntensity(event.target.value)} /></label>
          <label>継続時間 (min)<input value={duration} onChange={(event) => setDuration(event.target.value)} /></label>
          <p>精度: <strong>Full 1 m</strong>（Adaptiveはまだ無効）</p>
          <div className="smoke-actions">
            <button disabled={!area || busy} onClick={() => void handleEstimate()}>負荷を見積る</button>
            <button disabled={!area || busy || (status !== null && !TERMINAL.has(status.state))} onClick={() => void handleRun()}>
              解析開始
            </button>
          </div>
        </div>

        <div className="smoke-card">
          <h2>2. 状態</h2>
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
          {status && (
            <div className="smoke-result">
              <h3>{status.stage_label}</h3>
              <p>state: <code>{status.state}</code></p>
              {status.failure_code && <p className="smoke-error">{status.failure_code}: {status.failure_message}</p>}
              {!TERMINAL.has(status.state) && <button onClick={() => void handleCancel()}>キャンセル</button>}
            </div>
          )}
          {error && <pre className="smoke-error">{error}</pre>}
        </div>
      </section>

      <footer>
        下水・浸透は未考慮 / 雨は解析範囲内で一様 / 公的な洪水予報・避難情報ではありません
      </footer>
    </main>
  );
}
