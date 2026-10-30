import { afterEach, expect, it, vi } from "vitest";
import { SessionClient } from "./session";
import { bundle, json, pathOf, user } from "../test-fixtures";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it("coalesces repeated bootstrap calls including StrictMode re-entry", async () => {
  const fetcher = vi.fn().mockResolvedValue(json({}, 401));
  vi.stubGlobal("fetch", fetcher);
  const client = new SessionClient();
  await Promise.all([client.initialize(), client.initialize()]);
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(client.getSnapshot().status).toBe("anonymous");
});
it("distinguishes a service outage from a signed-out session", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 503)));
  const client = new SessionClient();
  await client.initialize();
  expect(client.getSnapshot().status).toBe("unavailable");
});
it("recovers through the CSRF and refresh cookie handshake", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(async (input) =>
      pathOf(input).endsWith("/csrf")
        ? json({ csrf_token: "test-csrf" })
        : json(bundle()),
    );
  vi.stubGlobal("fetch", fetcher);
  const client = new SessionClient();
  await client.initialize();
  expect(client.getSnapshot()).toEqual({ status: "authenticated", user });
  expect(fetcher.mock.calls[1][1]).toMatchObject({
    method: "POST",
    headers: { "X-CSRF-Token": "test-csrf" },
    credentials: "include",
  });
});
it("coalesces refresh when simultaneous protected requests receive 401", async () => {
  let refreshed = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (input, init) => {
      const path = pathOf(input);
      if (path.endsWith("/login")) return json(bundle("old-access"));
      if (path.endsWith("/csrf")) return json({ csrf_token: "test-csrf" });
      if (path.endsWith("/refresh")) {
        refreshed++;
        return json(bundle("new-access"));
      }
      return init.headers.Authorization === "Bearer old-access"
        ? json({}, 401)
        : json(user);
    }),
  );
  const client = new SessionClient();
  await client.login({ email: user.email, password: "test passphrase" });
  const values = await Promise.all([client.getMe(), client.getMe()]);
  expect(values).toEqual([user, user]);
  expect(refreshed).toBe(1);
});
it("does not report successful logout after network failure", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (input) => {
      if (pathOf(input).endsWith("/login")) return json(bundle());
      throw new TypeError("offline");
    }),
  );
  const client = new SessionClient();
  await client.login({ email: user.email, password: "test passphrase" });
  await expect(client.logout()).rejects.toMatchObject({ status: 0 });
  expect(client.getSnapshot().status).toBe("authenticated");
});
it("does not resurrect user data from a stale response after logout", async () => {
  let resolveMe!: (value: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (input) => {
      const path = pathOf(input);
      if (path.endsWith("/login")) return json(bundle());
      if (path.endsWith("/users/me"))
        return new Promise<Response>((resolve) => {
          resolveMe = resolve;
        });
      return new Response(null, { status: 204 });
    }),
  );
  const client = new SessionClient();
  await client.login({ email: user.email, password: "test passphrase" });
  const pending = client.getMe();
  await client.logout();
  resolveMe(json(user));
  await pending;
  expect(client.getSnapshot().status).toBe("anonymous");
});
it("never writes access credentials to browser storage", async () => {
  const local = vi.spyOn(Storage.prototype, "setItem");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(bundle())));
  const client = new SessionClient();
  await client.login({ email: user.email, password: "test passphrase" });
  expect(local).not.toHaveBeenCalled();
});
it("rejects malformed or inactive user data before unlocking the UI", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        json({ ...bundle(), user: { ...user, is_active: false } }),
      ),
  );
  const client = new SessionClient();
  await expect(
    client.login({ email: user.email, password: "test passphrase" }),
  ).rejects.toMatchObject({ status: 502 });
  expect(client.getSnapshot().status).not.toBe("authenticated");
});
it("ignores refresh completion after a cross-tab sign-out event", async () => {
  const channels: { onmessage: ((event: { data: string }) => void) | null }[] =
    [];
  class Channel {
    onmessage = null;
    constructor() {
      channels.push(this);
    }
    postMessage() {}
    close() {}
  }
  vi.stubGlobal("BroadcastChannel", Channel);
  let resolveRefresh!: (value: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (input) => {
      if (pathOf(input).endsWith("/csrf"))
        return json({ csrf_token: "test-csrf" });
      return new Promise<Response>((resolve) => {
        resolveRefresh = resolve;
      });
    }),
  );
  const client = new SessionClient();
  const disconnect = client.connect();
  const pending = client.initialize();
  await vi.waitFor(() => expect(resolveRefresh).toBeDefined());
  channels[0].onmessage?.({ data: "signed-out" });
  resolveRefresh(json(bundle()));
  await pending;
  expect(client.getSnapshot().status).toBe("anonymous");
  disconnect();
});

it("unlocks a loading screen when the browser lock cannot be acquired", async () => {
  vi.stubGlobal("navigator", {
    locks: {
      request: vi
        .fn()
        .mockRejectedValue(new DOMException("timed out", "AbortError")),
    },
  });
  const client = new SessionClient();
  await client.initialize();
  expect(client.getSnapshot().status).toBe("unavailable");
});
