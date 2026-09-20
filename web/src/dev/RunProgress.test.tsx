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
  };
}

describe("RunProgress", () => {
  it("shows ordered stage state and acquired/generated artifact labels", () => {
    render(
      <RunProgress
        status={status("BUILDING_GRID", "1 m計算格子を構築中", "BUILDING_GRID")}
        stageObservedAtMs={Date.now() - 5000}
        lastPollAtMs={Date.now()}
      />,
    );

    expect(screen.getByText("現在: 1 m計算格子を構築中")).toBeVisible();
    expect(screen.getByText("工程 8 / 13")).toBeVisible();
    expect(screen.getByText("標高")).toBeVisible();
    expect(screen.getByText("建物・道路")).toBeVisible();
    expect(screen.getByText("1 m格子")).toBeVisible();
    expect(screen.getByRole("progressbar", { name: "アプリケーション工程の進捗" })).toHaveValue(8);
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
