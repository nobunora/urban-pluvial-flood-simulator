import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("local review UI", () => {
  it("renders the Full 1 m controls", () => {
    render(<App />);
    expect(screen.getByText("ローカルレビュー版 — Full 1 m")).toBeVisible();
    expect(screen.getByRole("button", { name: "解析開始" })).toBeVisible();
  });
});
