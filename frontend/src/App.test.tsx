import { StrictMode } from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import App from "./App";
import { SessionClient } from "./auth/session";
import { bundle, json, pathOf, user } from "./test-fixtures";

function setup(
  path = "/",
  fetcher = vi.fn().mockResolvedValue(json({}, 401)),
  strict = false,
) {
  vi.stubGlobal("fetch", fetcher);
  const client = new SessionClient();
  const app = (
    <MemoryRouter initialEntries={[path]}>
      <App client={client} />
    </MemoryRouter>
  );
  render(strict ? <StrictMode>{app}</StrictMode> : app);
  return fetcher;
}
function fields() {
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: user.email },
  });
  fireEvent.change(screen.getByLabelText("Password", { exact: true }), {
    target: { value: "A long learning passphrase!" },
  });
}

it("renders the landing page with working registration navigation", async () => {
  setup();
  expect(
    screen.getByRole("heading", { name: /Learn the why/ }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("link", { name: /Create your account/ }));
  expect(
    await screen.findByRole("heading", { name: "Create your account" }),
  ).toBeInTheDocument();
});
it("redirects an anonymous visitor away from a protected deep link", async () => {
  setup("/app/account");
  expect(
    await screen.findByRole("heading", { name: "Sign in" }),
  ).toBeInTheDocument();
});
it("does not redirect an outage to a misleading signed-out state", async () => {
  setup("/app", vi.fn().mockResolvedValue(json({}, 503)));
  expect(await screen.findByText("Let’s reconnect.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
});
it("validates registration before sending an API mutation", async () => {
  const fetcher = setup("/register");
  fireEvent.click(screen.getByRole("button", { name: /Create account/ }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Check the highlighted fields.",
  );
  expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
  expect(
    fetcher.mock.calls.some(([path]) => String(path).endsWith("/register")),
  ).toBe(false);
});
it("registers and directs the student to sign in with a confirmation", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(async (input) =>
      pathOf(input).endsWith("/register") ? json(user, 201) : json({}, 401),
    );
  setup("/register", fetcher);
  fields();
  fireEvent.change(screen.getByLabelText("Full name"), {
    target: { value: user.full_name },
  });
  fireEvent.change(screen.getByLabelText("Confirm password"), {
    target: { value: "A long learning passphrase!" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Create account/ }));
  expect(
    await screen.findByText(
      "Account created. Sign in to enter your workspace.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Email address")).toHaveValue(user.email);
  const mutation = fetcher.mock.calls.find(([path]) =>
    String(path).endsWith("/register"),
  );
  expect(JSON.parse(mutation![1].body)).toEqual({
    email: user.email,
    full_name: user.full_name,
    password: "A long learning passphrase!",
  });
});
it("signs in and shows the actual account workspace", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(async (input) =>
      pathOf(input).endsWith("/login") ? json(bundle()) : json({}, 401),
    );
  setup("/login", fetcher);
  fields();
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(
    await screen.findByRole("heading", { name: /Hello, Test/ }),
  ).toBeInTheDocument();
  expect(screen.getByText(user.email)).toBeInTheDocument();
});
it("prevents duplicate submissions while a login request is pending", async () => {
  let resolve!: (value: Response) => void;
  const fetcher = vi.fn().mockImplementation(async (input) =>
    pathOf(input).endsWith("/login")
      ? new Promise<Response>((r) => {
          resolve = r;
        })
      : json({}, 401),
  );
  setup("/login", fetcher);
  fields();
  fireEvent.submit(
    screen.getByRole("button", { name: "Sign in" }).closest("form")!,
  );
  fireEvent.submit(
    screen.getByRole("button", { name: /Signing in/ }).closest("form")!,
  );
  await waitFor(() => expect(resolve).toBeDefined());
  expect(
    fetcher.mock.calls.filter(([path]) => String(path).endsWith("/login")),
  ).toHaveLength(1);
  resolve(json(bundle()));
  expect(
    await screen.findByRole("heading", { name: /Hello, Test/ }),
  ).toBeInTheDocument();
});
it("shows a safe login failure without rendering backend internals", async () => {
  setup(
    "/login",
    vi
      .fn()
      .mockImplementation(async (input) =>
        json(
          { detail: "internal-private-detail" },
          pathOf(input).endsWith("/login") ? 401 : 401,
        ),
      ),
  );
  fields();
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Incorrect email or password.",
  );
  expect(screen.queryByText(/internal-private-detail/)).not.toBeInTheDocument();
});
it("restores a protected account route after a fresh page load", async () => {
  setup(
    "/app/account",
    vi
      .fn()
      .mockImplementation(async (input) =>
        pathOf(input).endsWith("/csrf")
          ? json({ csrf_token: "test-csrf" })
          : json(bundle()),
      ),
  );
  expect(
    await screen.findByRole("heading", { name: "Account details" }),
  ).toBeInTheDocument();
  expect(screen.getAllByText(user.full_name).length).toBeGreaterThan(0);
});
it("logs out through the backend and removes the protected view", async () => {
  setup(
    "/app",
    vi.fn().mockImplementation(async (input) => {
      const path = pathOf(input);
      if (path.endsWith("/csrf")) return json({ csrf_token: "test-csrf" });
      if (path.endsWith("/logout-all"))
        return new Response(null, { status: 204 });
      return json(bundle());
    }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Sign out on all devices" }),
  );
  expect(
    await screen.findByRole("heading", { name: "Sign in" }),
  ).toBeInTheDocument();
});
it("does not replay refresh when React StrictMode runs effects twice", async () => {
  const fetcher = setup(
    "/login",
    vi.fn().mockResolvedValue(json({}, 401)),
    true,
  );
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
});
it("supports an explicit password visibility toggle", () => {
  setup("/login");
  const input = screen.getByLabelText("Password", { exact: true });
  expect(input).toHaveAttribute("type", "password");
  fireEvent.click(screen.getByRole("button", { name: "Show password" }));
  expect(input).toHaveAttribute("type", "text");
  fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
  expect(input).toHaveAttribute("type", "password");
});
it("renders unknown routes with a working home link", () => {
  setup("/missing");
  expect(screen.getByText("Page not found.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back to EduMind" })).toHaveAttribute(
    "href",
    "/",
  );
});
