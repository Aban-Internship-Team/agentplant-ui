import type { ErrorBody } from "../types/errors.ts";

export const FALLBACK_ERROR_BODY: ErrorBody = {
  message: "Request failed",
  errors: ["Request failed"],
  warnings: [],
};

export class ApiError extends Error {
  readonly status: number;
  readonly body: ErrorBody;

  constructor(status: number, body: ErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export class NetworkError extends Error {
  override readonly cause?: unknown;

  constructor(message = "Network request failed", cause?: unknown) {
    super(message);
    this.name = "NetworkError";
    this.cause = cause;
  }
}

export function apiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL;
  if (typeof raw !== "string") {
    return "";
  }
  return raw.replace(/\/+$/, "");
}

export function apiUrl(
  path: string,
  query?: Record<string, string | number | undefined>,
): string {
  const params = new URLSearchParams();
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) {
        params.set(key, String(value));
      }
    }
  }
  const search = params.toString();
  return `${apiBaseUrl()}${path}${search ? `?${search}` : ""}`;
}

export function isErrorBody(value: unknown): value is ErrorBody {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.message === "string" &&
    record.message.length > 0 &&
    Array.isArray(record.errors) &&
    record.errors.every((item) => typeof item === "string") &&
    Array.isArray(record.warnings) &&
    record.warnings.every((item) => typeof item === "string")
  );
}

export async function readErrorBody(response: Response): Promise<ErrorBody> {
  let parsed: unknown;
  try {
    parsed = await response.json();
  } catch {
    return FALLBACK_ERROR_BODY;
  }
  if (isErrorBody(parsed)) {
    return parsed;
  }
  return FALLBACK_ERROR_BODY;
}

type JsonRequestInit = Omit<RequestInit, "body"> & {
  body?: unknown;
  query?: Record<string, string | number | undefined>;
};

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (cause) {
    throw new NetworkError("Network request failed", cause);
  }
  if (!response.ok) {
    throw new ApiError(response.status, await readErrorBody(response));
  }
  return response;
}

export async function requestJson<T>(
  path: string,
  init: JsonRequestInit = {},
): Promise<T> {
  const { body, query, headers, ...rest } = init;
  const headerInit = new Headers(headers);
  if (body !== undefined && !headerInit.has("Content-Type")) {
    headerInit.set("Content-Type", "application/json");
  }
  const response = await request(apiUrl(path, query), {
    ...rest,
    headers: headerInit,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) {
    return undefined as T;
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(response.status, FALLBACK_ERROR_BODY);
  }
}

export async function requestForm<T>(
  path: string,
  formData: FormData,
  init: Omit<RequestInit, "body"> = {},
): Promise<T> {
  const { headers, ...rest } = init;
  const headerInit = new Headers(headers);
  headerInit.delete("Content-Type");
  const response = await request(apiUrl(path), {
    ...rest,
    method: rest.method ?? "POST",
    headers: headerInit,
    body: formData,
  });
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(response.status, FALLBACK_ERROR_BODY);
  }
}

export async function requestVoid(
  path: string,
  init: JsonRequestInit = {},
): Promise<void> {
  const { body, query, headers, ...rest } = init;
  const headerInit = new Headers(headers);
  if (body !== undefined && !headerInit.has("Content-Type")) {
    headerInit.set("Content-Type", "application/json");
  }
  const response = await request(apiUrl(path, query), {
    ...rest,
    headers: headerInit,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status !== 204) {
    return;
  }
}
