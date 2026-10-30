import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, it, expect, beforeEach } from "vitest";
import Knowledge from "./Knowledge";
import { ApiError } from "../api/client";
const request = vi.fn();
const identity = { role: "student", full_name: "Student" };
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: identity, client: { request } }),
}));
beforeEach(() => {
  identity.role = "student";
  request.mockReset();
  request.mockImplementation(async (path: string) => {
    if (path === "/knowledge/capabilities") return { storage_available: false };
    if (path.startsWith("/knowledge/submissions")) return [];
    if (path === "/contributor/application") return null;
    return [];
  });
});
it("offers a student contributor application without upload permissions", async () => {
  render(
    <MemoryRouter>
      <Knowledge />
    </MemoryRouter>,
  );
  await screen.findByRole("button", { name: "Apply to contribute" });
  expect(
    screen.queryByRole("button", { name: "Submit for review" }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/what materials/i), {
    target: { value: "I contribute verified mathematics notes." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Apply to contribute" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "/contributor/application",
      expect.objectContaining({ method: "POST" }),
    ),
  );
});
it("disables upload until private storage is configured", async () => {
  identity.role = "contributor";
  render(
    <MemoryRouter>
      <Knowledge />
    </MemoryRouter>,
  );
  expect(
    await screen.findByRole("button", { name: "Submit for review" }),
  ).toBeDisabled();
  expect(
    screen.getByText(/storage is awaiting configuration/i),
  ).toBeInTheDocument();
});
it("shows a backend failure clearly", async () => {
  request.mockRejectedValue(new ApiError(503));
  render(
    <MemoryRouter>
      <Knowledge />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    /temporarily unavailable/i,
  );
});
