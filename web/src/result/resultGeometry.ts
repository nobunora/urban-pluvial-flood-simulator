import type { ResultMetadataResponse } from "../api/client";

export type ResultImageCoordinates = [
  [number, number],
  [number, number],
  [number, number],
  [number, number],
];

export function resultImageCoordinates(
  bounds: ResultMetadataResponse["bounds"],
): ResultImageCoordinates {
  return [
    [bounds.west_deg, bounds.north_deg],
    [bounds.east_deg, bounds.north_deg],
    [bounds.east_deg, bounds.south_deg],
    [bounds.west_deg, bounds.south_deg],
  ];
}

export function resultBounds(
  bounds: ResultMetadataResponse["bounds"],
): [[number, number], [number, number]] {
  return [
    [bounds.west_deg, bounds.south_deg],
    [bounds.east_deg, bounds.north_deg],
  ];
}
