const configuredUrl =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const baseUrl = configuredUrl.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public readonly status: number) {
    super("The service is temporarily unavailable.");
  }
}

export async function getReadiness(signal?: AbortSignal): Promise<boolean> {
  const timeout = AbortSignal.timeout(5000);
  const response = await fetch(`${baseUrl}/api/v1/health/ready`, {
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new ApiError(response.status);
  const body: unknown = await response.json();
  if (
    !body ||
    typeof body !== "object" ||
    !("status" in body) ||
    body.status !== "ready"
  ) {
    throw new ApiError(502);
  }
  return true;
}
