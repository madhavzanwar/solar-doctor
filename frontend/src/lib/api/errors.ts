/** Normalised API error: every failure the UI sees is an ApiError with a human message. */
export class ApiError extends Error {
  readonly status: number;
  readonly details?: unknown;
  /** Seconds from the Retry-After header (429 only). */
  readonly retryAfterSeconds?: number;

  constructor(status: number, message: string, details?: unknown, retryAfterSeconds?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

interface ValidationItem {
  msg?: string;
  loc?: unknown[];
}

/** Turn a FastAPI error body (`{detail: string | ValidationItem[]}`) into one readable line. */
export function messageFromBody(body: unknown, fallback: string): string {
  if (body && typeof body === "object") {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail)) {
      const parts = (detail as ValidationItem[])
        .map((d) => {
          if (!d || typeof d.msg !== "string") return null;
          const field = Array.isArray(d.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
          return field ? `${field}: ${d.msg}` : d.msg;
        })
        .filter((p): p is string => !!p);
      if (parts.length) return parts.join("; ");
    }
    const message = (body as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  return fallback;
}

export function rateLimitMessage(retryAfterSeconds?: number): string {
  if (!retryAfterSeconds) return "Too many attempts. Please wait a few minutes and try again.";
  const minutes = Math.ceil(retryAfterSeconds / 60);
  return minutes <= 1
    ? "Too many attempts. Please try again in about a minute."
    : `Too many attempts. Please try again in about ${minutes} minutes.`;
}

export async function errorFromResponse(res: Response): Promise<ApiError> {
  const body: unknown = await res.json().catch(() => null);
  if (res.status === 429) {
    const secs = Number(res.headers.get("Retry-After"));
    const retry = Number.isFinite(secs) && secs > 0 ? Math.ceil(secs) : undefined;
    return new ApiError(429, rateLimitMessage(retry), body, retry);
  }
  return new ApiError(res.status, messageFromBody(body, res.statusText || `Request failed (${res.status})`), body);
}

export function networkError(apiUrl: string, cause: unknown): ApiError {
  return new ApiError(
    0,
    `Could not reach the SolarDoctor API at ${apiUrl}. Check that the backend is running.`,
    cause,
  );
}
