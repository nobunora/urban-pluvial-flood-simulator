import { describe, expect, it } from "vitest";

import { resultBounds, resultImageCoordinates } from "./resultGeometry";

const bounds = {
  west_deg: 139.7,
  south_deg: 35.6,
  east_deg: 139.8,
  north_deg: 35.7,
};

describe("result map geometry", () => {
  it("maps API bounds to MapLibre image corners in NW/NE/SE/SW order", () => {
    expect(resultImageCoordinates(bounds)).toEqual([
      [139.7, 35.7],
      [139.8, 35.7],
      [139.8, 35.6],
      [139.7, 35.6],
    ]);
  });

  it("maps API bounds to southwest/northeast fit bounds", () => {
    expect(resultBounds(bounds)).toEqual([
      [139.7, 35.6],
      [139.8, 35.7],
    ]);
  });
});
