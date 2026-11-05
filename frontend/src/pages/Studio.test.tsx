import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import Studio from "./Studio";

const { client } = vi.hoisted(() => ({ client: { request: vi.fn() } }));
const request = client.request;
vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ client }) }));
const id = "e94f285d-5bb8-46bf-bfd7-f7d94bdab421";
let row: Record<string, unknown>;
beforeEach(() => {
  request.mockReset();
  row = {
    id,
    title: "Mechanics",
    brief: "Explain physics",
    target_pages: 35,
    revision: 1,
    sections: [
      { title: "Introduction", content: "", last_request_id: null },
      { title: "Analysis", content: "", last_request_id: null },
      { title: "Conclusion", content: "", last_request_id: null },
    ],
    pending: null,
    word_count: 0,
    target_words: 12250,
  };
  request.mockImplementation(async (path: string, init: RequestInit = {}) => {
    if (path === "/chat/capabilities") return { available: true };
    if (path === "/documents" && init.method === "POST") return row;
    if (path === "/documents") return [];
    if (path.endsWith("/sections/0") && init.method === "PATCH") {
      const data = JSON.parse(init.body as string);
      row = {
        ...row,
        revision: 2,
        sections: [
          { title: data.title, content: data.content, last_request_id: null },
          { title: "Analysis", content: "", last_request_id: null },
          { title: "Conclusion", content: "", last_request_id: null },
        ],
        word_count: 3,
      };
      return row;
    }
    return row;
  });
});
function setup(path = "/app/studio") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/app/studio" element={<Studio />} />
        <Route path="/app/studio/:documentId" element={<Studio />} />
      </Routes>
    </MemoryRouter>,
  );
}
it("creates a long-form draft with the user's outline and page target", async () => {
  setup();
  fireEvent.change(screen.getByLabelText("Document title"), {
    target: { value: "Mechanics" },
  });
  fireEvent.change(screen.getByLabelText("What should this report cover?"), {
    target: { value: "Explain forces and motion with examples." },
  });
  fireEvent.change(screen.getByLabelText("Target length"), {
    target: { value: "45" },
  });
  expect(screen.getByText(/actual page count/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Create document" }));
  await screen.findByRole("heading", { name: "Mechanics" });
  const create = request.mock.calls.find(
    (c) => c[0] === "/documents" && c[1]?.method === "POST",
  );
  expect(JSON.parse(create![1].body)).toMatchObject({
    target_pages: 45,
    title: "Mechanics",
  });
  expect(screen.getByRole("button", { name: "Download PDF" })).toBeDisabled();
});
it("blocks generation/export until section edits are saved", async () => {
  setup(`/app/studio/${id}`);
  const text = await screen.findByLabelText("Section text");
  fireEvent.change(text, { target: { value: "Force equals mass." } });
  expect(
    screen.getByRole("button", { name: "Generate selected section" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "Download PDF" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Save section" }));
  await screen.findByText("Section saved.");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeEnabled(),
  );
});
it("keeps manual editing available when AI drafting is unavailable", async () => {
  request.mockImplementation(async (path: string) =>
    path === "/chat/capabilities"
      ? { available: false }
      : path === "/documents"
        ? []
        : row,
  );
  setup(`/app/studio/${id}`);
  await screen.findByLabelText("Section text");
  expect(
    screen.getByRole("button", { name: "Generate selected section" }),
  ).toBeDisabled();
  expect(screen.getByLabelText("Section text")).toBeEnabled();
});

it("filters draft titles and preserves an unfinished document brief", async () => {
  const original = request.getMockImplementation()!;
  request.mockImplementation((path: string, init?: RequestInit) =>
    path === "/documents" && !init?.method
      ? [
          { ...row, title: "Mechanics report" },
          {
            ...row,
            id: "ec5f0920-e74e-4834-a7e4-217990c445d4",
            title: "Biology report",
          },
        ]
      : original(path, init),
  );
  setup();
  await screen.findByRole("link", { name: /Mechanics report/ });
  fireEvent.change(screen.getByLabelText("Document title"), {
    target: { value: "My unfinished report" },
  });
  const search = screen.getByRole("searchbox", { name: "Search draft titles" });
  fireEvent.change(search, { target: { value: " MECHANICS " } });
  expect(
    screen.queryByRole("link", { name: /Biology report/ }),
  ).not.toBeInTheDocument();
  fireEvent.change(search, { target: { value: "missing" } });
  expect(screen.getByText(/No matching draft titles/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
  expect(search).toHaveFocus();
  expect(
    screen.getByRole("link", { name: /Biology report/ }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Document title")).toHaveValue(
    "My unfinished report",
  );
});

it("distinguishes draft loading from an empty list and recovers without resetting the brief", async () => {
  const original = request.getMockImplementation()!;
  let rejectList: (cause: unknown) => void = () => {};
  const loading = new Promise((_, reject) => {
    rejectList = reject;
  });
  let attempts = 0;
  request.mockImplementation((path: string, init?: RequestInit) => {
    if (path === "/documents" && !init?.method)
      return ++attempts === 1
        ? loading
        : [{ ...row, title: "Recovered report" }];
    return original(path, init);
  });
  setup();
  expect(screen.getByText("Loading your drafts…")).toBeInTheDocument();
  expect(
    screen.queryByText(/Your saved documents will appear here/),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Document title"), {
    target: { value: "Keep this title" },
  });
  rejectList(new Error("fixture unavailable"));
  await screen.findByRole("alert");
  expect(
    screen.queryByText(/Your saved documents will appear here/),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry drafts" }));
  await screen.findByRole("link", { name: /Recovered report/ });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Document title")).toHaveValue(
    "Keep this title",
  );
});
