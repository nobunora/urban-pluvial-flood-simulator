import type { components } from "./generated";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type GeocodeResponse = components["schemas"]["GeocodeResponse"];
export type GeocodeCandidateResponse = components["schemas"]["GeocodeCandidateResponse"];
export type AnalysisArea = components["schemas"]["AnalysisArea"];
export type ResourceEstimateResponse = components["schemas"]["ResourceEstimateResponse"];
export type RunConfig = components["schemas"]["RunConfig"];
export type RunCreateResponse = components["schemas"]["RunCreateResponse"];
export type RunStatusResponse = components["schemas"]["RunStatusResponse"];
export type ResultMetadataResponse = components["schemas"]["ResultMetadataResponse"];
export type PointInspectionResponse = components["schemas"]["PointInspectionResponse"];

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await window.fetch(path, init);
  const data = (await response.json()) as unknown;
  if (!response.ok) {
    const envelope = data as { error?: { code?: string; message?: string } };
    const code = envelope.error?.code ?? `HTTP_${response.status}`;
    const message = envelope.error?.message ?? `HTTP ${response.status}`;
    throw new Error(`${code}: ${message}`);
  }
  return data as T;
}

export function getHealth(): Promise<HealthResponse> {
  return jsonRequest<HealthResponse>("/api/v1/health");
}

export function searchLocation(query: string, signal?: AbortSignal): Promise<GeocodeResponse> {
  const params = new URLSearchParams({ q: query });
  return jsonRequest<GeocodeResponse>(`/api/v1/geocode?${params.toString()}`, { signal });
}

export function estimateResources(
  analysisArea: AnalysisArea,
  accuracyMode: RunConfig["requested_accuracy_mode"] = "full_1m",
): Promise<ResourceEstimateResponse> {
  return jsonRequest<ResourceEstimateResponse>("/api/v1/estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis_area: analysisArea, accuracy_mode: accuracyMode }),
  });
}

export function createRun(config: RunConfig): Promise<RunCreateResponse> {
  return jsonRequest<RunCreateResponse>("/api/v1/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
}

export function getRun(runId: string): Promise<RunStatusResponse> {
  return jsonRequest<RunStatusResponse>(`/api/v1/runs/${encodeURIComponent(runId)}`);
}

export function cancelRun(runId: string): Promise<void> {
  return jsonRequest<void>(`/api/v1/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
}


export function getResultMetadata(runId: string): Promise<ResultMetadataResponse> {
  return jsonRequest<ResultMetadataResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/result-metadata`,
  );
}

export function inspectResult(
  runId: string,
  lon: number,
  lat: number,
  timeIndex: number | null = null,
  signal?: AbortSignal,
): Promise<PointInspectionResponse> {
  const params = new URLSearchParams({
    lon: String(lon),
    lat: String(lat),
  });
  if (timeIndex !== null) params.set("time_index", String(timeIndex));
  return jsonRequest<PointInspectionResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/inspect?${params.toString()}`,
    { signal },
  );
}

export function resultLayerUrl(
  runId: string,
  layer: "max-depth" | "grid-resolution" | "depth",
  timeIndex: number | null = null,
): string {
  const encodedRunId = encodeURIComponent(runId);
  if (layer === "depth") {
    if (timeIndex === null) {
      throw new Error("timeIndex is required for time-dependent result layers");
    }
    return `/api/v1/runs/${encodedRunId}/layers/${layer}.png?time_index=${timeIndex}`;
  }
  return `/api/v1/runs/${encodedRunId}/layers/${layer}.png`;
}


export type FlowViewport = {
  west: number;
  south: number;
  east: number;
  north: number;
};

export function flowVectorsGeoJsonUrl(
  runId: string,
  timeIndex: number,
  viewport: FlowViewport,
  stride: number,
): string {
  const params = new URLSearchParams({
    time_index: String(timeIndex),
    west: String(viewport.west),
    south: String(viewport.south),
    east: String(viewport.east),
    north: String(viewport.north),
    stride: String(Math.max(1, Math.trunc(stride))),
  });
  return `/api/v1/runs/${encodeURIComponent(runId)}/layers/flow-vectors.geojson?${params.toString()}`;
}

export type FlowVectorFeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: {
      type: "MultiLineString";
      coordinates: number[][][];
    };
    properties: {
      speed_mps: number;
      u_mps: number;
      v_mps: number;
      time_index: number;
      row: number;
      column: number;
      face_index?: number;
      grid_resolution_m?: number;
    };
  }>;
  metadata: {
    speed_unit: string;
    min_speed_mps: number;
    sample_stride_cells: number;
    arrow_length_m: number;
    arrow_count: number;
    sampling_method: string;
    viewport: FlowViewport;
  };
};

export function getFlowVectors(
  runId: string,
  timeIndex: number,
  viewport: FlowViewport,
  stride: number,
  signal?: AbortSignal,
): Promise<FlowVectorFeatureCollection> {
  return jsonRequest<FlowVectorFeatureCollection>(
    flowVectorsGeoJsonUrl(runId, timeIndex, viewport, stride),
    { signal },
  );
}
