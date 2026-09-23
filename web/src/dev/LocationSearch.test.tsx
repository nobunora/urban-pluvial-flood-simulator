import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { searchLocation } from "../api/client";
import LocationSearch from "./LocationSearch";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    searchLocation: vi.fn(),
  };
});

describe("LocationSearch", () => {
  beforeEach(() => {
    vi.mocked(searchLocation).mockReset();
  });

  it("searches explicitly and selects a candidate", async () => {
    const onSelect = vi.fn();
    vi.mocked(searchLocation).mockResolvedValue({
      candidates: [
        {
          title: "東京都千代田区千代田1-1",
          lon: 139.7528,
          lat: 35.6852,
          provider: "csis_simple_geocoding",
          confidence: 5,
          level: 8,
          converted: "東京都千代田区千代田1-1",
        },
      ],
      attribution: {
        text: "CSISシンプルジオコーディング実験を利用",
        url: "https://geocode.csis.u-tokyo.ac.jp/",
      },
    });

    render(<LocationSearch disabled={false} onSelect={onSelect} />);

    fireEvent.change(screen.getByLabelText("住所・地名を検索"), {
      target: { value: "皇居" },
    });
    fireEvent.click(screen.getByRole("button", { name: "検索" }));

    await waitFor(() => {
      expect(searchLocation).toHaveBeenCalledWith("皇居", expect.any(AbortSignal));
    });

    expect(await screen.findByText("東京都千代田区千代田1-1")).toBeVisible();
    expect(screen.getByText(/CSISシンプルジオコーディング実験を利用/)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /東京都千代田区千代田1-1/ }));
    expect(onSelect).toHaveBeenCalledWith(139.7528, 35.6852);
    expect(screen.queryByRole("list", { name: "住所・地名検索候補" })).not.toBeInTheDocument();
  });

  it("rejects over-limit query locally without an API request", () => {
    render(<LocationSearch disabled={false} onSelect={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("住所・地名を検索"), {
      target: { value: "あ".repeat(201) },
    });
    fireEvent.click(screen.getByRole("button", { name: "検索" }));

    expect(screen.getByText("検索語は200文字以内で入力してください。")).toBeVisible();
    expect(searchLocation).not.toHaveBeenCalled();
  });

  it("keeps manual-coordinate fallback available when geocoding fails", async () => {
    vi.mocked(searchLocation).mockRejectedValue(new Error("GEOCODER_UNAVAILABLE"));

    render(<LocationSearch disabled={false} onSelect={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("住所・地名を検索"), {
      target: { value: "府中駅" },
    });
    fireEvent.click(screen.getByRole("button", { name: "検索" }));

    expect(
      await screen.findByText("住所・地名検索を利用できません。緯度経度を直接入力できます。"),
    ).toBeVisible();
  });
});
