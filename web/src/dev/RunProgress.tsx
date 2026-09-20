import { useEffect, useMemo, useState } from "react";

import type { RunStatusResponse } from "../api/client";

type Props = {
  status: RunStatusResponse | null;
  stageObservedAtMs: number | null;
  lastPollAtMs: number | null;
};

const TERMINAL = new Set<RunStatusResponse["state"]>(["COMPLETE", "FAILED", "CANCELLED"]);

const STAGES = [
  ["CREATED", "受付"],
  ["VALIDATING", "入力確認"],
  ["ACQUIRING_TERRAIN", "標高取得"],
  ["ACQUIRING_VECTORS", "建物・道路取得"],
  ["ACQUIRING_RAINFALL", "降雨準備"],
  ["PREPROCESSING_TERRAIN", "地形前処理"],
  ["ALLOCATING_ROOF_RAIN", "屋根雨水配分"],
  ["BUILDING_GRID", "1 m格子構築"],
  ["BUILDING_MODEL", "SFINCSモデル構築"],
  ["ENSURING_ENGINE", "エンジン確認"],
  ["RUNNING_ENGINE", "SFINCS計算"],
  ["READING_RESULTS", "結果読込"],
  ["COMPLETE", "完了"],
] as const;

const ARTIFACTS = [
  ["ACQUIRING_TERRAIN", "⛰", "標高"],
  ["ACQUIRING_VECTORS", "▦", "建物・道路"],
  ["ACQUIRING_RAINFALL", "☂", "雨"],
  ["BUILDING_GRID", "▤", "1 m格子"],
  ["BUILDING_MODEL", "▱", "モデル"],
  ["ENSURING_ENGINE", "⚙", "SFINCS"],
  ["RUNNING_ENGINE", "▶", "計算"],
  ["READING_RESULTS", "▥", "結果"],
  ["COMPLETE", "⌖", "地図"],
] as const;

function stageIndex(code: string | null | undefined): number {
  return STAGES.findIndex(([stageCode]) => stageCode === code);
}

function formatElapsed(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = seconds % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
}

export default function RunProgress({ status, stageObservedAtMs, lastPollAtMs }: Props) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    setNowMs(Date.now());
    if (!status || TERMINAL.has(status.state)) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [status]);

  const currentIndex = stageIndex(status?.stage_code);
  const enteredStage = currentIndex >= 0 ? currentIndex + 1 : 0;
  const elapsedSeconds = stageObservedAtMs == null ? 0 : (nowMs - stageObservedAtMs) / 1000;
  const pollAgeSeconds = lastPollAtMs == null ? null : Math.max(0, Math.floor((nowMs - lastPollAtMs) / 1000));

  const progressText = useMemo(() => {
    if (!status) return "解析を開始すると工程が表示されます。";
    if (status.state === "FAILED") return "解析に失敗しました。";
    if (status.state === "CANCELLED") return "解析はキャンセルされました。";
    if (status.state === "CANCELLING") return "キャンセル処理中です。";
    if (status.state === "COMPLETE") return "すべての工程が完了しました。";
    return `現在: ${status.stage_label}`;
  }, [status]);

  if (!status) {
    return <p className="run-progress-empty">{progressText}</p>;
  }

  return (
    <section className="run-progress" aria-label="解析工程">
      <div className="run-progress-summary">
        <div>
          <strong>{progressText}</strong>
          {currentIndex >= 0 && <span>工程 {enteredStage} / {STAGES.length}</span>}
        </div>
        {stageObservedAtMs != null && !TERMINAL.has(status.state) && (
          <span>この工程の経過 {formatElapsed(elapsedSeconds)}</span>
        )}
      </div>

      {currentIndex >= 0 && (
        <progress
          className="run-progress-overall"
          value={enteredStage}
          max={STAGES.length}
          aria-label="アプリケーション工程の進捗"
        />
      )}

      <ol className="run-progress-stages">
        {STAGES.map(([code, label], index) => {
          const mode =
            status.state === "COMPLETE" || index < currentIndex
              ? "complete"
              : index === currentIndex
                ? "current"
                : "pending";
          return (
            <li className={`run-progress-stage is-${mode}`} key={code}>
              <span className="run-progress-dot" aria-hidden="true" />
              <span>{label}</span>
            </li>
          );
        })}
      </ol>

      <div className="run-progress-artifacts" aria-label="取得・生成データ">
        {ARTIFACTS.map(([code, icon, label]) => {
          const index = stageIndex(code);
          const complete = status.state === "COMPLETE" || (currentIndex >= 0 && currentIndex > index);
          const current = currentIndex === index && !TERMINAL.has(status.state);
          return (
            <span
              className={`run-progress-artifact ${complete ? "is-complete" : current ? "is-current" : ""}`}
              key={code}
            >
              <span aria-hidden="true">{icon}</span>
              {label}
            </span>
          );
        })}
      </div>

      {status.stage_code === "RUNNING_ENGINE" && (
        <div className="run-progress-engine" role="status">
          <div className="run-progress-indeterminate" aria-hidden="true"><span /></div>
          <strong>SFINCS計算中 — 経過 {formatElapsed(elapsedSeconds)}</strong>
          <p>
            状態確認: {pollAgeSeconds == null ? "未確認" : pollAgeSeconds <= 1 ? "1秒以内" : `${pollAgeSeconds}秒前`}
            {" / "}
            完了率はエンジンから取得していません。
          </p>
        </div>
      )}
    </section>
  );
}
