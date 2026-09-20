import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { RunStatusResponse } from "../api/client";
import RunProgress from "./RunProgress";

function status(stageCode: string, stageLabel: string, state: RunStatusResponse["state"]): RunStatusResponse {
  return {
    run_id: "00000000-0000-0000-0000-000000000001",
    state,
    stage_code: stageCode,
    stage_label: stageLabel,
    failure_code: null,
    failure_message: null,
    activity_lines: [],
  };
}

describe("RunProgress", () => {
  it("groups fast backend stages into five icon-bearing progress boxes", () => {
    render(
      <RunProgress
        status={status("BUILDING_GRID", "1 m計算格子を構築中", "BUILDING_GRID")}
        stageObservedAtMs={Date.now() - 5000}
        lastPollAtMs={Date.now()}
      />,
    );

    expect(screen.getByText("現在: 1 m計算格子を構築中")).toBeVisible();
    expect(screen.getByText("工程 3 / 5")).toBeVisible();
    expect(screen.getByText("準備")).toBeVisible();
    expect(screen.getByText("データ取得")).toBeVisible();
    expect(screen.getByText("解析格子")).toBeVisible();
    expect(screen.getByText("SFINCS計算")).toBeVisible();
    expect(screen.getByText("結果")).toBeVisible();
    expect(screen.getByText("⛰ ▦ ☂")).toBeInTheDocument();
    expect(screen.getByText("▤ ▱ ⚙")).toBeInTheDocument();
    expect(screen.queryByLabelText("取得・生成データ")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "アプリケーション工程の進捗" })).toHaveValue(3);
  });

  it("shows provider/grid progress detail and remaining work outside SFINCS", () => {
    const acquiring = status(
      "ACQUIRING_VECTORS",
      "建物・道路データを取得中",
      "ACQUIRING_VECTORS",
    );
    acquiring.progress_fraction = 0.45;
    acquiring.progress_detail = "PLATEAU 3/8ファイル処理済み / 建物120件 / 残り5ファイル";
    acquiring.activity_lines = [
      "[APP] PLATEAU対象ファイル 8件",
      "[APP] PLATEAU 3/8ファイル処理済み / 建物120件 / 残り5ファイル",
    ];

    render(
      <RunProgress
        status={acquiring}
        stageObservedAtMs={Date.now() - 5000}
        lastPollAtMs={Date.now()}
      />,
    );

    expect(screen.getByRole("progressbar", { name: "現在工程の処理進捗" })).toHaveValue(0.45);
    expect(screen.getByText("45%")).toBeVisible();
    expect(screen.getAllByText(/残り5ファイル/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByLabelText("処理ログ")).toHaveTextContent("3/8ファイル処理済み");
  });

  it("uses indeterminate engine activity until real progress is available", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-20T08:00:10Z"));

    render(
      <RunProgress
        status={status("RUNNING_ENGINE", "SFINCSを実行中", "RUNNING_ENGINE")}
        stageObservedAtMs={Date.parse("2026-09-20T08:00:00Z")}
        lastPollAtMs={Date.parse("2026-09-20T08:00:09Z")}
      />,
    );

    expect(screen.getByText("SFINCS計算中 — 経過 00:10")).toBeVisible();
    expect(screen.getByText(/実進捗を取得すると残り時間を推定します/)).toBeVisible();
    expect(screen.queryByRole("progressbar", { name: "SFINCS計算進捗" })).not.toBeInTheDocument();

    vi.useRealTimers();
  });

  it("shows recent backend and raw SFINCS activity lines", () => {
    const running = status("RUNNING_ENGINE", "SFINCSを実行中", "RUNNING_ENGINE");
    running.activity_lines = [
      "[APP] SFINCSを実行しています。",
      "---- Using 8 of 8 available threads ----",
      "40% complete, 18.5 s remaining",
    ];

    render(
      <RunProgress
        status={running}
        stageObservedAtMs={Date.now() - 5000}
        lastPollAtMs={Date.now()}
      />,
    );

    expect(screen.getByText("処理ログ")).toBeVisible();
    expect(screen.getByLabelText("処理ログ")).toHaveTextContent("Using 8 of 8 available threads");
    expect(screen.getByLabelText("処理ログ")).toHaveTextContent("40% complete");
  });

  it("shows actual parsed SFINCS percentage and elapsed-based ETA", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-20T08:00:12Z"));
    const running = status("RUNNING_ENGINE", "SFINCSを実行中", "RUNNING_ENGINE");
    running.progress_fraction = 0.4;
    running.estimated_remaining_seconds = 18;

    render(
      <RunProgress
        status={running}
        stageObservedAtMs={Date.parse("2026-09-20T08:00:00Z")}
        lastPollAtMs={Date.parse("2026-09-20T08:00:11Z")}
      />,
    );

    expect(screen.getByText(/SFINCS計算中 — 40% — 経過 00:12/)).toBeVisible();
    expect(screen.getByRole("progressbar", { name: "SFINCS計算進捗" })).toHaveValue(0.4);
    expect(screen.getByText(/残り目安 約00:18（実進捗から推定）/)).toBeVisible();

    vi.useRealTimers();
  });
});
