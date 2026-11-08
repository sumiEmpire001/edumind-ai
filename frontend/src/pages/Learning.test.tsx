import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import Learning from "./Learning";
const request = vi.fn();
const identity = { role: "student" };
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: identity, client: { request } }),
}));
beforeEach(() => {
  identity.role = "student";
  request.mockReset();
  request.mockImplementation(async (path: string) =>
    path.startsWith("/learning/examples") ? [] : {},
  );
});
it("requires consent and hides admin exports from students", async () => {
  render(<Learning />);
  await screen.findByText("No questions here yet.");
  expect(
    screen.queryByRole("button", { name: "Download training JSONL" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("checkbox")).toBeRequired();
  fireEvent.change(screen.getByLabelText("Academic question"), {
    target: { value: "What is acceleration?" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(
    screen.getByRole("button", { name: "Submit question for review" }),
  );
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "/learning/examples",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          question: "What is acceleration?",
          consent_to_share: true,
        }),
      }),
    ),
  );
  expect(
    await screen.findByText(/Question submitted for review/),
  ).toBeInTheDocument();
});
it("reports unmatched questions without claiming a generated answer", async () => {
  request.mockImplementation(async (path: string) =>
    path === "/learning/query"
      ? {
          status: "insufficient_knowledge",
          sources: [],
          duration_ms: 1,
          message:
            "No matching approved knowledge. Try Study chat or a different question.",
        }
      : [],
  );
  render(<Learning />);
  await screen.findByText("No questions here yet.");
  fireEvent.change(screen.getByLabelText("Search question"), {
    target: { value: "What is acceleration?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search knowledge" }));
  expect(
    await screen.findByText(/No matching approved knowledge/),
  ).toBeInTheDocument();
});
it("shows counts and unmeasured capacity to administrators", async () => {
  identity.role = "admin";
  request.mockImplementation(async (path: string) =>
    path === "/admin/learning/overview"
      ? {
          examples: { pending: 2 },
          training_examples: 3,
          evaluation_examples: 1,
          searchable_chunks: 12,
          queries: 0,
          queries_with_sources: 0,
          p95_latency_ms: null,
          measurement_window: "Latest searches",
          gates: [
            { name: "Independent language model", status: "not_configured" },
          ],
        }
      : [],
  );
  render(<Learning />);
  expect(
    await screen.findByRole("region", { name: "API progress" }),
  ).toHaveTextContent("Not measured");
  expect(screen.getByText("not configured")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Download training JSONL" }),
  ).toBeInTheDocument();
});
it("allows retry after a backend failure", async () => {
  request.mockRejectedValue(new ApiError(503));
  render(<Learning />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    /temporarily unavailable/i,
  );
  request.mockResolvedValue([]);
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await screen.findByText("No questions here yet.");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
