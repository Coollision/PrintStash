import {
  authHeaders,
  getJson,
  getUrl,
  handleResponse,
  sendAction,
  sendJson,
} from "@/lib/api/request";
import type {
  EndpointProposal,
  GenerationEstimate,
  GenerationProposal,
  InferenceEndpoint,
  InferenceModel,
  SearchGeneration,
  SearchResponse,
  SearchSettings,
  SearchSettingsRead,
  SearchStatus,
  SearchSubjectType,
} from "@/types/search";

export interface SearchQuery {
  q: string;
  mode?: "lexical" | "hybrid";
  instant?: boolean;
  cursor?: string;
  limit?: number;
  types?: SearchSubjectType[];
}
export async function searchLibrary(
  query: SearchQuery,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const params = new URLSearchParams({
    q: query.q,
    mode: query.mode ?? "hybrid",
    limit: String(query.limit ?? 30),
  });
  if (query.cursor) params.set("cursor", query.cursor);
  if (query.instant) params.set("instant", "true");
  query.types?.forEach((type) => params.append("types[]", type));
  return handleResponse<SearchResponse>(
    await fetch(getUrl(`/api/v1/search?${params}`), {
      headers: authHeaders(),
      cache: "no-store",
      signal,
    }),
  );
}
export function getSearchStatus() {
  return getJson<SearchStatus>("/api/v1/search/status", { fresh: true });
}
export async function searchUsingModel(
  modelId: number,
  cursor?: string,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const params = new URLSearchParams();
  if (cursor) params.set("cursor", cursor);
  return handleResponse<SearchResponse>(
    await fetch(getUrl(`/api/v1/models/${modelId}/similar-text?${params}`), {
      headers: authHeaders(),
      cache: "no-store",
      signal,
    }),
  );
}
export async function searchImage(
  image: File,
  query: { cursor?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ limit: String(query.limit ?? 30) });
  if (query.cursor) params.set("cursor", query.cursor);
  return handleResponse<SearchResponse>(
    await fetch(getUrl(`/api/v1/search/image?${params}`), {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": image.type },
      body: image,
      cache: "no-store",
      signal,
    }),
  );
}
const configuration = "/api/v1/config/ai-search";
export function getSearchSettings() {
  return getJson<SearchSettingsRead>(configuration, { fresh: true });
}
export function saveSearchSettings(settings: SearchSettings) {
  return sendJson<SearchSettingsRead>(configuration, "PUT", settings);
}
export function createInferenceEndpoint(proposal: EndpointProposal) {
  return sendJson<InferenceEndpoint>(`${configuration}/endpoints`, "POST", proposal);
}
export function importEnvironmentEndpoint(kind: "embedding" | "chat") {
  return sendJson<InferenceEndpoint>(
    `${configuration}/endpoints/from-environment/${kind}`,
    "POST",
    {},
  );
}
export function listSearchGenerations() {
  return getJson<SearchGeneration[]>(`${configuration}/generations`, { fresh: true });
}
export function prepareSearchGeneration(proposal: GenerationProposal) {
  return sendJson<SearchGeneration>(`${configuration}/generations`, "POST", proposal);
}
export function estimateSearchGeneration(proposal: GenerationProposal) {
  return sendJson<GenerationEstimate>(`${configuration}/generations/estimate`, "POST", proposal);
}
export function actOnSearchGeneration(
  generation: SearchGeneration,
  action: "activate" | "cancel" | "retry",
) {
  return sendJson<SearchGeneration>(
    `${configuration}/generations/${generation.id}/${action}`,
    "POST",
    { version_token: generation.version_token },
  );
}
export function listInferenceModels() {
  return getJson<InferenceModel[]>("/api/v1/inference/models", { fresh: true });
}
export function downloadInferenceModel(key: string) {
  return sendJson<{ job_id: string }>(
    `/api/v1/inference/models/${encodeURIComponent(key)}/download`,
    "POST",
    {},
  );
}
export function cancelInferenceDownload(id: string) {
  return sendAction(`/api/v1/inference/models/downloads/${encodeURIComponent(id)}/cancel`, "POST");
}
export function validateInferenceModel(id: string) {
  return sendJson<{ id: string; ready: boolean }>(
    `/api/v1/inference/models/${id}/validate`,
    "POST",
    {},
  );
}
export function deleteInferenceModel(id: string) {
  return sendAction(`/api/v1/inference/models/${id}`, "DELETE");
}
