/** Normalised API error: every failure the UI sees is an ApiError with a human message. */
export class ApiError extends Error {
  readonly status: number;
  readonly details?: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
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

export async function errorFromResponse(res: Response): Promise<ApiError> {
  const body: unknown = await res.json().catch(() => null);
  return new ApiError(res.status, messageFromBody(body, res.statusText || `Request failed (${res.status})`), body);
}

export function networkError(apiUrl: string, cause: unknown): ApiError {
  return new ApiError(
    0,
    `Could not reach the SolarDoctor API at ${apiUrl}. Check that the backend is running.`,
    cause,
  );
}
