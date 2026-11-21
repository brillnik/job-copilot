import { toApiError } from "./errors";

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Turn an openapi-fetch result into data, or throw a normalised ApiError. */
export async function unwrap<T>(result: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await result;
  if (error !== undefined || data === undefined) {
    // 204 responses have no body; treat as success with undefined.
    if (error === undefined && response.ok) return undefined as T;
    throw toApiError(error, response.status);
  }
  return data;
}

/** Same, but also returns the ETag so callers can send If-Match later. */
export async function unwrapWithEtag<T>(
  result: Promise<Result<T>>,
): Promise<{ data: T; etag: string | null }> {
  const r = await result;
  if (r.error !== undefined || r.data === undefined) {
    throw toApiError(r.error, r.response.status);
  }
  return { data: r.data, etag: r.response.headers.get("etag") };
}
