/**
 * Wire types — match the backend's response envelopes exactly.
 * See `app/shared/base_schemas.py` on the FastAPI side.
 */

export interface ApiMessage {
  success: boolean;
  detail: string;
  code?: string;
}

export interface ApiSingle<T> {
  success: true;
  data: T;
}

export interface ApiPaginated<T> {
  success: true;
  data: {
    items: T[];
    total: number;
    skip: number;
    limit: number;
  };
}

export interface ApiError {
  success: false;
  detail: string;
  code?: string;
  errors?: unknown[];
}

export class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiError | { detail?: string } | unknown,
  ) {
    super(
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `HTTP ${status}`,
    );
    this.name = "HttpError";
  }
}
