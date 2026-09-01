import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("Phase 1 placeholder", () => {
  it("shows the skeleton message", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Urban Pluvial Flood Simulator" })).toBeVisible();
    expect(screen.getByText("Application skeleton is running.")).toBeVisible();
  });
});
