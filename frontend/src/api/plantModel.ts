import type {
  ArtifactCreateRequest,
  ArtifactCreateResponse,
  ArtifactDetail,
  ArtifactPluginResponse,
  ArtifactSummary,
  FileRef,
  HealthResponse,
  PlantModelChatRequest,
  PlantModelChatResponse,
  PlantModelConversationDetail,
  PlantModelConversationSummary,
  SimulateRequest,
  SimulateResponse,
  UserScopedOptions,
  ValidationRequest,
  ValidationResponse,
} from "../types/models.ts";
import { requestForm, requestJson, requestVoid } from "./client.ts";

const PLANT = "/api/plant-model";

function userQuery(opts?: UserScopedOptions): { user_id?: number } {
  return opts?.userId === undefined ? {} : { user_id: opts.userId };
}

export function getHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/health");
}

export function createChatTurn(
  body: PlantModelChatRequest,
  opts?: UserScopedOptions,
): Promise<PlantModelChatResponse> {
  return requestJson<PlantModelChatResponse>(`${PLANT}/chat`, {
    method: "POST",
    body,
    query: userQuery(opts),
  });
}

export function listConversations(
  opts?: UserScopedOptions,
): Promise<PlantModelConversationSummary[]> {
  return requestJson<PlantModelConversationSummary[]>(`${PLANT}/conversations`, {
    method: "GET",
    query: userQuery(opts),
  });
}

export function getConversation(
  id: number,
  opts?: UserScopedOptions,
): Promise<PlantModelConversationDetail> {
  return requestJson<PlantModelConversationDetail>(`${PLANT}/conversations/${id}`, {
    method: "GET",
    query: userQuery(opts),
  });
}

export function deleteConversation(
  id: number,
  opts?: UserScopedOptions,
): Promise<void> {
  return requestVoid(`${PLANT}/conversations/${id}`, {
    method: "DELETE",
    query: userQuery(opts),
  });
}

export function uploadFile(file: File): Promise<FileRef> {
  const formData = new FormData();
  formData.append("file", file);
  return requestForm<FileRef>(`${PLANT}/files`, formData);
}

export function simulatePlant(
  body: SimulateRequest,
  opts?: UserScopedOptions,
): Promise<SimulateResponse> {
  return requestJson<SimulateResponse>(`${PLANT}/simulate`, {
    method: "POST",
    body,
    query: userQuery(opts),
  });
}

export function createArtifact(
  body: ArtifactCreateRequest,
  opts?: UserScopedOptions,
): Promise<ArtifactCreateResponse> {
  return requestJson<ArtifactCreateResponse>(`${PLANT}/artifacts`, {
    method: "POST",
    body,
    query: userQuery(opts),
  });
}

export function listArtifacts(): Promise<ArtifactSummary[]> {
  return requestJson<ArtifactSummary[]>(`${PLANT}/artifacts`, { method: "GET" });
}

export function getArtifact(id: string): Promise<ArtifactDetail> {
  return requestJson<ArtifactDetail>(`${PLANT}/artifacts/${id}`, { method: "GET" });
}

export function getArtifactPlugin(id: string): Promise<ArtifactPluginResponse> {
  return requestJson<ArtifactPluginResponse>(`${PLANT}/artifacts/${id}/plugin`, {
    method: "GET",
  });
}

export function getArtifactAdaptiveSpec(id: string): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(`${PLANT}/artifacts/${id}/adaptive-spec`, {
    method: "GET",
  });
}

export function validatePlant(
  body: ValidationRequest,
  opts?: UserScopedOptions,
): Promise<ValidationResponse> {
  return requestJson<ValidationResponse>(`${PLANT}/validate`, {
    method: "POST",
    body,
    query: userQuery(opts),
  });
}
