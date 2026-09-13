import type { components } from "./generated";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type AnalysisArea = components["schemas"]["AnalysisArea"];
export type ResourceEstimateResponse = components["schemas"]["ResourceEstimateResponse"];
export type RunConfig = components["schemas"]["RunConfig"];
export type RunCreateResponse = components["schemas"]["RunCreateResponse"];
export type RunStatusResponse = components["schemas"]["RunStatusResponse"];

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

export function estimateResources(
  analysisArea: AnalysisArea,
): Promise<ResourceEstimateResponse> {
  return jsonRequest<ResourceEstimateResponse>("/api/v1/estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis_area: analysisArea, accuracy_mode: "full_1m" }),
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
