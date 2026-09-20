import { useEffect, useMemo, useState } from "react";

import type { RunStatusResponse } from "../api/client";

type Props = {
  status: RunStatusResponse | null;
  stageObservedAtMs: number | null;
  lastPollAtMs: number | null;
};

const TERMINAL = new Set<RunStatusResponse["state"]>(["COMPLETE", "FAILED", "CANCELLED"]);

const BACKEND_ORDER = [
  "CREATED",
  "VALIDATING",
  "ACQUIRING_TERRAIN",
  "ACQUIRING_VECTORS",
  "ACQUIRING_RAINFALL",
  "PREPROCESSING_TERRAIN",
  "ALLOCATING_ROOF_RAIN",
  "BUILDING_GRID",
  "BUILDING_MODEL",
  "ENSURING_ENGINE",
  "RUNNING_ENGINE",
  "READING_RESULTS",
  "COMPLETE",
] as const;

const GROUPS = [
  {
    label: "準備",
    icon: "✓",
    codes: ["CREATED", "VALIDATING"],
  },
  {
    label: "データ取得",
    icon: "⛰ ▦ ☂",
    codes: ["ACQUIRING_TERRAIN", "ACQUIRING_VECTORS", "ACQUIRING_RAINFALL"],
  },
  {
    label: "解析格子",
    icon: "▤ ▱ ⚙",
    codes: ["PREPROCESSING_TERRAIN", "ALLOCATING_ROOF_RAIN", "BUILDING_GRID", "BUILDING_MODEL", "ENSURING_ENGINE"],
  },
  {
    label: "SFINCS計算",
    icon: "▶",
    codes: ["RUNNING_ENGINE"],
  },
  {
    label: "結果",
    icon: "▥ ⌖",
    codes: ["READING_RESULTS", "COMPLETE"],
  },
] as const;

function backendIndex(code: string | null | undefined): number {
  return BACKEND_ORDER.findIndex((stageCode) => stageCode === code);
}

function groupIndex(code: string | null | undefined): number {
  return GROUPS.findIndex((group) => group.codes.some((stageCode) => stageCode === code));
}

function groupLastBackendIndex(group: (typeof GROUPS)[number]): number {
  return Math.max(...group.codes.map((code) => backendIndex(code)));
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

  const currentBackendIndex = backendIndex(status?.stage_code);
  const currentGroupIndex = groupIndex(status?.stage_code);
  const elapsedSeconds = stageObservedAtMs == null ? 0 : (nowMs - stageObservedAtMs) / 1000;
  const pollAgeSeconds = lastPollAtMs == null
    ? null
    : Math.max(0, Math.floor((nowMs - lastPollAtMs) / 1000));
  const activityLines = status?.activity_lines ?? [];

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

  const displayGroupIndex = status.state === "COMPLETE"
    ? GROUPS.length - 1
    : currentGroupIndex;

  return (
    <section className="run-progress" aria-label="解析工程">
      <div className="run-progress-summary">
        <div>
          <strong>{progressText}</strong>
          {displayGroupIndex >= 0 && <span>工程 {displayGroupIndex + 1} / {GROUPS.length}</span>}
        </div>
        {stageObservedAtMs != null && !TERMINAL.has(status.state) && (
          <span>現在処理の経過 {formatElapsed(elapsedSeconds)}</span>
        )}
      </div>

      {displayGroupIndex >= 0 && (
        <progress
          className="run-progress-overall"
          value={displayGroupIndex + 1}
          max={GROUPS.length}
          aria-label="アプリケーション工程の進捗"
        />
      )}

      <ol className="run-progress-stages">
        {GROUPS.map((group, index) => {
          const complete =
            status.state === "COMPLETE" ||
            (currentBackendIndex >= 0 && currentBackendIndex > groupLastBackendIndex(group));
          const current = displayGroupIndex === index && status.state !== "COMPLETE";
          const mode = complete ? "complete" : current ? "current" : "pending";
          return (
            <li className={`run-progress-stage is-${mode}`} key={group.label}>
              <span className="run-progress-stage-icon" aria-hidden="true">{group.icon}</span>
              <span className="run-progress-stage-copy">
                <strong>{group.label}</strong>
                {current && <small>{status.progress_detail ?? status.stage_label}</small>}
              </span>
            </li>
          );
        })}
      </ol>

      {status.stage_code !== "RUNNING_ENGINE" &&
        !TERMINAL.has(status.state) &&
        status.progress_fraction != null && (
          <div className="run-progress-work" role="status">
            <progress
              className="run-progress-work-bar"
              max={1}
              value={status.progress_fraction}
              aria-label="現在工程の処理進捗"
            />
            <div>
              <strong>{Math.round(status.progress_fraction * 100)}%</strong>
              <span>{status.progress_detail ?? status.stage_label}</span>
            </div>
          </div>
        )}

      {status.stage_code === "RUNNING_ENGINE" && (
        <div className="run-progress-engine" role="status">
          {status.progress_fraction == null ? (
            <div className="run-progress-indeterminate" aria-hidden="true"><span /></div>
          ) : (
            <progress
              className="run-progress-engine-bar"
              max={1}
              value={status.progress_fraction}
              aria-label="SFINCS計算進捗"
            />
          )}
          <strong>
            SFINCS計算中
            {status.progress_fraction == null
              ? ""
              : ` — ${Math.round(status.progress_fraction * 100)}%`}
            {" — "}経過 {formatElapsed(elapsedSeconds)}
          </strong>
          <p>
            状態確認: {pollAgeSeconds == null ? "未確認" : pollAgeSeconds <= 1 ? "1秒以内" : `${pollAgeSeconds}秒前`}
            {status.estimated_remaining_seconds == null
              ? " / 実進捗を取得すると残り時間を推定します。"
              : ` / 残り目安 約${formatElapsed(status.estimated_remaining_seconds)}（実進捗から推定）`}
          </p>
        </div>
      )}

      {activityLines.length > 0 && (
        <div className="run-progress-console">
          <div className="run-progress-console-heading">
            <strong>処理ログ</strong>
            <span>最新 {Math.min(activityLines.length, 16)} 行</span>
          </div>
          <pre aria-label="処理ログ">{activityLines.slice(-16).join("\n")}</pre>
        </div>
      )}
    </section>
  );
}
