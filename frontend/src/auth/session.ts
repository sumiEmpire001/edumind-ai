import { ApiError, apiJson } from "../api/client";

export type Role = "student" | "contributor" | "admin";
export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}
export interface Credentials {
  email: string;
  password: string;
}
export interface Registration extends Credentials {
  full_name: string;
}
type State =
  | { status: "loading" | "anonymous" | "unavailable"; user: null }
  | { status: "authenticated"; user: User };

export function parseUser(value: unknown): User {
  if (!value || typeof value !== "object") throw new ApiError(502);
  const u = value as Partial<User>;
  if (
    typeof u.id !== "string" ||
    typeof u.email !== "string" ||
    typeof u.full_name !== "string" ||
    typeof u.created_at !== "string" ||
    !["student", "contributor", "admin"].includes(u.role || "") ||
    u.is_active !== true
  )
    throw new ApiError(502);
  return u as User;
}

export class SessionClient {
  private state: State = { status: "loading", user: null };
  private token: string | null = null;
  private version = 0;
  private expires = 0;
  private listeners = new Set<() => void>();
  private boot: Promise<void> | null = null;
  private flight: Promise<void> | null = null;
  private tail: Promise<void> = Promise.resolve();
  private channel: BroadcastChannel | null = null;
  getSnapshot = (): State => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  private publish(state: State) {
    this.state = state;
    this.listeners.forEach((l) => l());
  }
  private clear() {
    this.version++;
    this.token = null;
    this.expires = 0;
    this.publish({ status: "anonymous", user: null });
  }
  private broadcast(event: "signed-out" | "changed") {
    this.channel?.postMessage(event);
  }

  connect(): () => void {
    if (typeof BroadcastChannel !== "undefined") {
      this.channel = new BroadcastChannel("edumind-session");
      this.channel.onmessage = (event) => {
        if (event.data === "signed-out") this.clear();
        if (event.data === "changed") {
          this.version++;
          this.token = null;
          this.expires = 0;
          this.publish({ status: "loading", user: null });
          void (this.flight || Promise.resolve())
            .catch(() => {})
            .then(() => this.recover())
            .catch(() => {});
        }
      };
    }
    const focus = () => {
      if (this.state.status === "authenticated")
        void this.getMe().catch(() => {});
    };
    window.addEventListener("focus", focus);
    return () => {
      this.channel?.close();
      this.channel = null;
      window.removeEventListener("focus", focus);
    };
  }

  private cookieOperation<T>(task: () => Promise<T>): Promise<T> {
    const run = async (): Promise<T> => {
      if (navigator.locks?.request)
        return await navigator.locks.request(
          "edumind-auth-cookies",
          { signal: AbortSignal.timeout(20000) },
          task,
        );
      return task();
    };
    const result = this.tail.then(run, run);
    this.tail = result.then(
      () => {},
      () => {},
    );
    return result;
  }

  initialize(): Promise<void> {
    if (!this.boot) this.boot = this.recover().catch(() => {});
    return this.boot;
  }

  private establish(value: unknown) {
    if (!value || typeof value !== "object") throw new ApiError(502);
    const data = value as Record<string, unknown>;
    const user = parseUser(data.user);
    if (
      typeof data.access_token !== "string" ||
      !data.access_token ||
      data.token_type !== "bearer" ||
      typeof data.expires_in !== "number" ||
      data.expires_in < 1 ||
      data.expires_in > 1800 ||
      typeof data.csrf_token !== "string" ||
      !data.csrf_token
    )
      throw new ApiError(502);
    this.version++;
    this.token = data.access_token;
    this.expires = Date.now() + data.expires_in * 1000;
    this.publish({ status: "authenticated", user });
  }

  recover(): Promise<void> {
    if (this.flight) return this.flight;
    const entryVersion = this.version;
    this.flight = this.cookieOperation(async () => {
      const version = this.version;
      try {
        const csrf = await apiJson("/auth/csrf");
        if (
          !csrf ||
          typeof csrf !== "object" ||
          !("csrf_token" in csrf) ||
          typeof csrf.csrf_token !== "string"
        )
          throw new ApiError(502);
        // Fetch CSRF after acquiring the cross-tab lock; the browser sends its CURRENT cookies.
        const result = await apiJson("/auth/refresh", {
          method: "POST",
          headers: { "X-CSRF-Token": csrf.csrf_token },
        });
        if (version === this.version) this.establish(result);
      } catch (error) {
        if (version !== this.version) throw error;
        this.token = null;
        this.expires = 0;
        if (error instanceof ApiError && error.status === 401) this.clear();
        else this.publish({ status: "unavailable", user: null });
        throw error;
      }
    })
      .catch((error) => {
        if (!(error instanceof ApiError)) {
          if (entryVersion === this.version) {
            this.token = null;
            this.expires = 0;
            this.publish({ status: "unavailable", user: null });
          }
          throw new ApiError(0);
        }
        throw error;
      })
      .finally(() => {
        this.flight = null;
      });
    return this.flight;
  }

  register(data: Registration) {
    return this.cookieOperation(async () => {
      parseUser(
        await apiJson("/auth/register", {
          method: "POST",
          body: JSON.stringify(data),
        }),
      );
    });
  }

  login(data: Credentials) {
    return this.cookieOperation(async () => {
      this.establish(
        await apiJson("/auth/login", {
          method: "POST",
          body: JSON.stringify(data),
        }),
      );
      this.broadcast("changed");
    });
  }

  private async authorized(
    path: string,
    init: RequestInit = {},
    timeoutMs = 12000,
  ): Promise<unknown> {
    if (!this.token || this.expires <= Date.now() + 30000) await this.recover();
    if (!this.token) throw new ApiError(401);
    const previous = this.token;
    try {
      return await apiJson(
        path,
        {
          ...init,
          headers: { ...init.headers, Authorization: `Bearer ${previous}` },
        },
        timeoutMs,
      );
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      // Only retry a rejected authentication request, never a timeout or network failure.
      if (this.token === previous) await this.recover();
      if (!this.token) throw new ApiError(401);
      const retryToken = this.token;
      try {
        return await apiJson(
          path,
          {
            ...init,
            headers: { ...init.headers, Authorization: `Bearer ${retryToken}` },
          },
          timeoutMs,
        );
      } catch (retryError) {
        if (
          retryError instanceof ApiError &&
          retryError.status === 401 &&
          this.token === retryToken
        )
          this.clear();
        throw retryError;
      }
    }
  }

  request(path: string, init: RequestInit = {}, timeoutMs = 12000) {
    return this.authorized(path, init, timeoutMs);
  }

  async getMe() {
    const version = this.version;
    const user = parseUser(await this.authorized("/users/me"));
    if (version === this.version && this.token)
      this.publish({ status: "authenticated", user });
    return user;
  }

  private async authenticatedCookieMutation(path: string, body?: string) {
    // Renew before taking the cookie lock; nesting refresh under that lock would deadlock.
    if (!this.token || this.expires <= Date.now() + 30000) await this.recover();
    return this.cookieOperation(async () => {
      const token = this.token;
      if (!token) throw new ApiError(401);
      try {
        await apiJson(path, {
          method: "POST",
          body,
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch (error) {
        if (
          error instanceof ApiError &&
          error.status === 401 &&
          this.token === token
        )
          this.clear();
        throw error;
      }
      this.clear();
      this.broadcast("signed-out");
    });
  }

  logout() {
    return this.authenticatedCookieMutation("/auth/logout-all");
  }

  changePassword(current_password: string, new_password: string) {
    return this.authenticatedCookieMutation(
      "/auth/password",
      JSON.stringify({ current_password, new_password }),
    );
  }
}

export const sessionClient = new SessionClient();
