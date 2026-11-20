import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { AuthProvider } from "../auth/AuthContext";
import { SessionClient, type Role } from "../auth/session";
import Chat from "./Chat";
import { bundle, json, pathOf, user } from "../test-fixtures";
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
  role: Role = "student",
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
      if (path.endsWith("/refresh")) return json({ ...bundle(), user: { ...user, role } });
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
          <Route path="/app/studio/:documentId" element={<h1>Studio draft</h1>} />
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
    screen.getByRole("button", { name: "Copy question", hidden: true }),
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

it("filters loaded titles without losing the current question or sending a request", async () => {
  const other = {
    ...conversation,
    id: "ec5f0920-e74e-4834-a7e4-217990c445d4",
    title: "Biology revision",
  };
  const { fetcher } = setup(true, (path) =>
    path.endsWith("/conversations")
      ? json({
          items: [{ ...conversation, title: "Mechanics revision" }, other],
          total: 40,
        })
      : null,
  );
  const field = await screen.findByLabelText("Your question");
  const historyToggle = screen.getByRole("button", { name: "Conversations" });
  expect(historyToggle).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(historyToggle);
  await screen.findByRole("link", { name: /Mechanics revision/ });
  fireEvent.change(field, { target: { value: "Keep my unfinished question" } });
  const search = screen.getByRole("searchbox", {
    name: "Search conversation titles",
  });
  fireEvent.change(search, { target: { value: "  MECHANICS  " } });
  expect(
    screen.getByRole("link", { name: /Mechanics revision/ }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: /Biology revision/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText(/Load more to include older chats/),
  ).toBeInTheDocument();
  fireEvent.change(search, { target: { value: "unmatched topic" } });
  expect(screen.getByText(/No matching titles/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
  expect(search).toHaveFocus();
  expect(
    screen.getByRole("link", { name: /Biology revision/ }),
  ).toBeInTheDocument();
  expect(field).toHaveValue("Keep my unfinished question");
  expect(
    fetcher.mock.calls.some((call) => pathOf(call[0]).endsWith("/messages")),
  ).toBe(false);
});

it("offers automatic web research and sends an explicit override with the question", async () => {
  const modes: string[] = [];
  setup(true, (path, init) => {
    if (path.endsWith("/capabilities"))
      return json({
        available: true, mode: "verification", timeout_seconds: 20,
        web_research_available: true,
      });
    if (path.endsWith("/messages"))
      modes.push(JSON.parse(init.body as string).research_mode);
    return null;
  });
  const mode = await screen.findByLabelText("Web research");
  expect(mode).toHaveValue("auto");
  fireEvent.change(mode, { target: { value: "on" } });
  fireEvent.change(screen.getByLabelText("Your question"), {
    target: { value: "Explain incident response" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
  expect(await screen.findByRole("heading", { name: "Explanation" })).toBeInTheDocument();
  expect(modes).toEqual(["on"]);
});

it("can search approved knowledge in chat when the AI provider is unavailable", async () => {
  const sent: string[] = [];
  setup(false, (path, init) => {
    if (path.endsWith("/messages")) sent.push(JSON.parse(init.body as string).content);
    return null;
  }, "contributor");
  const field = await screen.findByLabelText("Your question");
  expect(field).toBeDisabled();
  fireEvent.click(screen.getByLabelText("Chat options"));
  fireEvent.click(screen.getByRole("button", { name: "Search approved knowledge" }));
  expect(field).toBeEnabled();
  expect(field).toHaveValue("/knowledge ");
  fireEvent.change(field, { target: { value: "/knowledge Sutterby" } });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
  await waitFor(() => expect(sent).toEqual(["/knowledge Sutterby"]));
});

it("keeps the approved knowledge search out of student chat options", async () => {
  setup();
  await screen.findByLabelText("Your question");
  fireEvent.click(screen.getByLabelText("Chat options"));
  expect(screen.queryByText("Search approved knowledge")).not.toBeInTheDocument();
});

it("sends quiz mode for a topic and the student's follow-up answer", async () => {
  const modes: string[] = [];
  setup(true, (path, init) => {
    if (path.endsWith("/messages")) modes.push(JSON.parse(init.body as string).study_mode);
    return null;
  });
  const mode = await screen.findByLabelText("Study mode");
  fireEvent.change(mode, { target: { value: "quiz" } });
  const field = screen.getByLabelText("Your question");
  for (const text of ["Newton's laws", "A net force causes acceleration"]) {
    fireEvent.change(field, { target: { value: text } });
    fireEvent.click(screen.getByRole("button", { name: "Send question" }));
    await waitFor(() => expect(field).toHaveValue(""));
  }
  expect(modes).toEqual(["quiz", "quiz"]);
});

it("opens a Studio draft seeded from the selected saved answer", async () => {
  const saved = setup(true, (path, init) => {
    if (path.endsWith("/documents") && init.method === "POST") {
      const body = JSON.parse(init.body as string);
      expect(body.source_answer).toEqual({
        conversation_id: cid,
        message_id: saved.rows.at(-1)?.id,
      });
      return json({ id: crypto.randomUUID() }, 201);
    }
    return null;
  });
  const field = await screen.findByLabelText("Your question");
  fireEvent.change(field, { target: { value: "Explain Newton’s laws" } });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
  expect(await screen.findByRole("heading", { name: "Explanation" })).toBeInTheDocument();
  fireEvent.click(screen.getByText("Answer actions", { exact: true }));
  fireEvent.click(screen.getByRole("button", { name: "Create Studio draft" }));
  expect(await screen.findByRole("heading", { name: "Studio draft" })).toBeInTheDocument();
});

it("keeps a long answer readable and prepares continuation without sending automatically", async () => {
  const longAnswer = "## Detailed report\n\n" + "Evidence and reasoning. ".repeat(1500)
    + "\n\n> Response length limit reached. Use Continue answer to carry on.";
  const saved = setup(true, (path) => {
    if (path.endsWith(`/conversations/${cid}`)) return json({
      conversation,
      messages: [{ id: "99054420-9894-4a48-bfa0-bb7bf748d823", request_id: "8cb0af80-4543-447f-8f02-09b7c8ad90d0", sequence: 2,
        role: "assistant", content: longAnswer, provider: "verification", created_at: created }],
      requests: [], has_older: false,
    });
    return null;
  });
  expect(await screen.findByRole("heading", { name: "Detailed report" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Continue answer" }));
  expect(screen.getByLabelText("Your question")).toHaveValue(
    "Continue the previous answer from where it stopped. Keep the same structure and do not repeat earlier sections.");
  expect(saved.fetcher.mock.calls.filter(([url]) => pathOf(url).endsWith("/messages"))).toHaveLength(0);
});
