import { afterEach, expect, it, vi } from "vitest";
import { ApiError, apiJson, errorMessage, getReadiness } from "./client";
import { json } from "../test-fixtures";
afterEach(() => vi.unstubAllGlobals());
it("includes cookies and JSON headers without exposing credentials elsewhere", async () => {
  const fetcher = vi.fn().mockResolvedValue(json({ status: "ready" }));
  vi.stubGlobal("fetch", fetcher);
  await expect(getReadiness()).resolves.toBe(true);
  expect(fetcher.mock.calls[0][1]).toMatchObject({
    credentials: "include",
    headers: { Accept: "application/json" },
  });
});
it("rejects malformed readiness data", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ status: "ok" })));
  await expect(getReadiness()).rejects.toMatchObject({ status: 502 });
});
it("does not reflect backend messages and respects Retry-After", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      json({ detail: "private-provider-secret" }, 429, {
        "Retry-After": "42",
      }),
    ),
  );
  const error = await apiJson("/auth/login").catch((e) => e);
  expect(error).toBeInstanceOf(ApiError);
  expect(errorMessage(error)).toContain("42 seconds");
  expect(errorMessage(error)).not.toContain("private-provider-secret");
});
it("shows understandable network errors", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new TypeError("private network detail")),
  );
  await expect(apiJson("/auth/login")).rejects.toMatchObject({ status: 0 });
});
it("rejects invalid successful JSON", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("invalid json", { status: 200 })),
  );
  await expect(apiJson("/auth/login")).rejects.toMatchObject({ status: 502 });
});

it("keeps its timeout active while a response body is still arriving", async () => {
  vi.useFakeTimers();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (_input, init) => ({
      ok: true,
      status: 200,
      json: () =>
        new Promise((_resolve, reject) => {
          init.signal.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    })),
  );
  try {
    const result = apiJson("/auth/login").catch((error) => error);
    await vi.advanceTimersByTimeAsync(12000);
    expect(await result).toMatchObject({ status: 0 });
  } finally {
    vi.useRealTimers();
  }
});
