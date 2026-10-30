import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { AuthProvider } from "../auth/AuthContext";
import { SessionClient } from "../auth/session";
import Chat from "./Chat";
import { bundle, json, pathOf } from "../test-fixtures";
const cid = "e94f285d-5bb8-46bf-bfd7-f7d94bdab421";
const created = "2026-10-30T12:00:00Z";
const conversation = {
  id: cid,
  title: "New conversation",
  created_at: created,
  updated_at: created,
};
function setup(
  available = true,
  mutate?: (
    path: string,
    init: RequestInit,
  ) => Response | Promise<Response> | null,
) {
  const rows: {
    id: string;
    request_id: string;
    sequence: number;
    role: string;
    content: string;
    provider: string | null;
    created_at: string;
  }[] = [];
  const requests: {
    id: string;
    status: string;
    error_code: string | null;
    deadline_at: string;
  }[] = [];
  const fetcher = vi
    .fn()
    .mockImplementation(async (input, init: RequestInit = {}) => {
      const path = pathOf(input);
      const custom = mutate?.(path, init);
      if (custom) return await custom;
      if (path.endsWith("/csrf")) return json({ csrf_token: "test-csrf" });
      if (path.endsWith("/refresh")) return json(bundle());
      if (path.endsWith("/capabilities"))
        return json({
          available,
          mode: available ? "verification" : "unconfigured",
          timeout_seconds: 20,
        });
      if (path.endsWith("/messages")) {
        const data = JSON.parse(init.body as string);
        const q = {
          id: data.request_id,
          status: "succeeded",
          error_code: null,
          deadline_at: created,
        };
        requests.push(q);
        rows.push({
          id: crypto.randomUUID(),
          request_id: q.id,
          sequence: rows.length + 1,
          role: "user",
          content: data.content,
          provider: null,
          created_at: created,
        });
        rows.push({
          id: crypto.randomUUID(),
          request_id: q.id,
          sequence: rows.length + 1,
          role: "assistant",
          content: "### Explanation\nA scripted result: $F = ma$.",
          provider: "verification",
          created_at: created,
        });
        return json(
          { request: q, messages: rows.slice(-2), replayed: false },
          201,
        );
      }
      if (path.endsWith(`/conversations/${cid}`))
        return json({
          conversation,
          messages: rows,
          requests,
          has_older: false,
        });
      if (path.endsWith("/conversations"))
        return json({ items: [conversation], total: 1 });
      return json({}, 404);
    });
  vi.stubGlobal("fetch", fetcher);
  render(
    <MemoryRouter initialEntries={[`/app/chat/${cid}`]}>
      <AuthProvider client={new SessionClient()}>
        <Routes>
          <Route path="/app/chat/:conversationId" element={<Chat />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
  return { fetcher, rows, requests };
}
it("discloses verification mode and saves a question and its answer", async () => {
  setup();
  const field = await screen.findByLabelText("Your question");
  await waitFor(() => expect(field).toBeEnabled());
  expect(
    screen.getByText(/responses are scripted test fixtures/),
  ).toBeInTheDocument();
  fireEvent.change(field, { target: { value: "Explain force" } });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
  expect(
    await screen.findByRole("heading", { name: "Explanation" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Explain force")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Copy question" }),
  ).toBeInTheDocument();
  expect(field).toHaveValue("");
});
it("makes the unconfigured mode explicit and does not offer fake answers", async () => {
  setup(false);
  const field = await screen.findByLabelText("Your question");
  expect(
    await screen.findByText(/AI answers aren’t connected yet/),
  ).toBeInTheDocument();
  expect(field).toBeDisabled();
  expect(screen.getByRole("button", { name: "Send question" })).toBeDisabled();
  expect(screen.queryByText("Verification response")).not.toBeInTheDocument();
});
it("retains the draft and reuses its request ID after an unknown network outcome", async () => {
  const ids: string[] = [];
  setup(true, (path, init) => {
    if (path.endsWith("/messages")) {
      ids.push(JSON.parse(init.body as string).request_id);
      return Promise.reject(new TypeError("connection lost"));
    }
    return null;
  });
  const field = await screen.findByLabelText("Your question");
  await waitFor(() => expect(field).toBeEnabled());
  fireEvent.change(field, { target: { value: "Keep this question" } });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "We could not reach EduMind",
  );
  expect(field).toHaveValue("Keep this question");
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
  await waitFor(() => expect(ids).toHaveLength(2));
  expect(ids[0]).toBe(ids[1]);
});
it("renders a failed saved question without inventing an assistant message", async () => {
  const rid = crypto.randomUUID();
  setup(true, (path) =>
    path.endsWith(`/conversations/${cid}`)
      ? json({
          conversation,
          messages: [
            {
              id: crypto.randomUUID(),
              request_id: rid,
              sequence: 1,
              role: "user",
              content: "A saved question",
              provider: null,
              created_at: created,
            },
          ],
          requests: [
            {
              id: rid,
              status: "failed",
              error_code: "timeout",
              deadline_at: created,
            },
          ],
          has_older: false,
        })
      : null,
  );
  expect(
    await screen.findByText(/The answer timed out. Your question was saved./),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("article", { name: "EduMind response" }),
  ).not.toBeInTheDocument();
});
it("shows a private or missing conversation as unavailable", async () => {
  setup(true, (path) =>
    path.endsWith(`/conversations/${cid}`) ? json({}, 404) : null,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "This conversation is not available.",
  );
  expect(screen.queryByLabelText("Your question")).not.toBeInTheDocument();
});
