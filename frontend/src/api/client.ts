const configured = import.meta.env.VITE_API_BASE_URL?.trim();
const baseUrl = configured?.replace(/\/$/, "") || "";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly retryAfter?: number,
  ) {
    super(
      status === 0
        ? "We could not reach EduMind. Check your connection and try again."
        : status === 429
          ? `Too many attempts. Please wait${retryAfter ? ` ${retryAfter} seconds` : " a moment"} before trying again.`
          : status === 401
            ? "Your session has expired. Please sign in again."
            : status === 403
              ? "We could not verify this request. Reload the page and try again."
              : status === 422
                ? "Check your details and try again."
                : "EduMind is temporarily unavailable. Please try again.",
    );
  }
}

export function errorMessage(
  error: unknown,
  action?: "login" | "register" | "password",
): string {
  if (!(error instanceof ApiError))
    return "Something went wrong. Please try again.";
  if (error.status === 401 && action === "login")
    return "Incorrect email or password.";
  if (error.status === 409 && action === "register")
    return "We could not create an account with these details. If you already have an account, sign in.";
  if (error.status === 400 && action === "password")
    return "Check your current password and choose a different new password.";
  return error.message;
}

export async function apiJson(
  path: string,
  init: RequestInit = {},
  timeoutMs = 12000,
): Promise<unknown> {
  // Vite's dev proxy supports local preview. Production requires an explicit API origin.
  if (import.meta.env.PROD && !configured) throw new ApiError(503);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    let response: Response;
    try {
      response = await fetch(`${baseUrl}/api/v1${path}`, {
        ...init,
        credentials: "include",
        signal: controller.signal,
        headers: {
          Accept: "application/json",
          ...(init.body ? { "Content-Type": "application/json" } : {}),
          ...init.headers,
        },
      });
    } catch {
      throw new ApiError(0);
    }
    if (!response.ok) {
      const wait = Number(response.headers.get("retry-after"));
      throw new ApiError(
        response.status,
        wait > 0 && wait <= 3600 ? Math.ceil(wait) : undefined,
      );
    }
    if (response.status === 204) return undefined;
    try {
      return await response.json();
    } catch {
      throw new ApiError(controller.signal.aborted ? 0 : 502);
    }
  } finally {
    clearTimeout(timer);
  }
}

export async function getReadiness(): Promise<boolean> {
  const body = await apiJson("/health/ready");
  if (
    !body ||
    typeof body !== "object" ||
    !("status" in body) ||
    body.status !== "ready"
  )
    throw new ApiError(502);
  return true;
}
