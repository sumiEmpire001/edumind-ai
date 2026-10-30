import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => vi.unstubAllGlobals());
function open(path = "/") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}
it("reports a real readiness response", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({ status: "ready" }) });
  vi.stubGlobal("fetch", fetcher);
  open();
  fireEvent.click(screen.getByRole("button"));
  expect(
    await screen.findByText("Backend and database are ready"),
  ).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it("shows unavailable and allows retry after a backend error", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
  open();
  fireEvent.click(screen.getByRole("button"));
  expect(await screen.findByText(/Service unavailable/)).toBeInTheDocument();
  expect(screen.getByRole("button")).toBeEnabled();
});
it("handles network failure without exposing error details", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new Error("private provider detail")),
  );
  open();
  fireEvent.click(screen.getByRole("button"));
  expect(await screen.findByText(/Service unavailable/)).toBeInTheDocument();
  expect(screen.queryByText(/private provider detail/)).not.toBeInTheDocument();
});
it("does not call a malformed response ready", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ status: "ok" }) }),
  );
  open();
  fireEvent.click(screen.getByRole("button"));
  expect(await screen.findByText(/Service unavailable/)).toBeInTheDocument();
});
it("handles unknown routes", () => {
  open("/missing");
  expect(screen.getByText("Page not found")).toBeInTheDocument();
});
