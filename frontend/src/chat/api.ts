import { ApiError } from "../api/client";
import type { SessionClient } from "../auth/session";
export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}
export interface Message {
  id: string;
  request_id: string;
  sequence: number;
  role: "user" | "assistant";
  content: string;
  provider: string | null;
  created_at: string;
}
export interface QuestionRequest {
  id: string;
  status: "pending" | "succeeded" | "failed";
  error_code: string | null;
  deadline_at: string;
}
export interface Detail {
  conversation: Conversation;
  messages: Message[];
  requests: QuestionRequest[];
  has_older: boolean;
}
export interface Capabilities {
  available: boolean;
  mode: "unconfigured" | "verification";
  timeout_seconds: number;
}
export const validId = (id: string) =>
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
const bad = (): never => {
  throw new ApiError(502);
};
function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : bad();
}
function date(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}
export function conversation(value: unknown): Conversation {
  const c = record(value);
  if (
    typeof c.id !== "string" ||
    !validId(c.id) ||
    typeof c.title !== "string" ||
    !date(c.created_at) ||
    !date(c.updated_at)
  )
    return bad();
  return c as unknown as Conversation;
}
export function message(value: unknown): Message {
  const m = record(value);
  if (
    typeof m.id !== "string" ||
    !validId(m.id) ||
    typeof m.request_id !== "string" ||
    !validId(m.request_id) ||
    !Number.isInteger(m.sequence) ||
    Number(m.sequence) < 1 ||
    !["user", "assistant"].includes(String(m.role)) ||
    typeof m.content !== "string" ||
    m.content.length > 12000 ||
    !(m.provider === null || typeof m.provider === "string") ||
    !date(m.created_at)
  )
    return bad();
  return m as unknown as Message;
}
function questionRequest(value: unknown): QuestionRequest {
  const q = record(value);
  if (
    typeof q.id !== "string" ||
    !validId(q.id) ||
    !["pending", "succeeded", "failed"].includes(String(q.status)) ||
    !(q.error_code === null || typeof q.error_code === "string") ||
    !date(q.deadline_at)
  )
    return bad();
  return q as unknown as QuestionRequest;
}
export function detail(value: unknown): Detail {
  const d = record(value);
  if (
    !Array.isArray(d.messages) ||
    !Array.isArray(d.requests) ||
    typeof d.has_older !== "boolean"
  )
    return bad();
  return {
    conversation: conversation(d.conversation),
    messages: d.messages.map(message),
    requests: d.requests.map(questionRequest),
    has_older: d.has_older,
  };
}
export class ChatApi {
  constructor(private client: SessionClient) {}
  async capabilities(): Promise<Capabilities> {
    const c = record(await this.client.request("/chat/capabilities"));
    if (
      typeof c.available !== "boolean" ||
      !["unconfigured", "verification"].includes(String(c.mode)) ||
      typeof c.timeout_seconds !== "number" ||
      c.timeout_seconds <= 0 ||
      c.timeout_seconds > 60
    )
      return bad();
    return c as unknown as Capabilities;
  }
  async list(offset = 0) {
    const p = record(
      await this.client.request(`/conversations?offset=${offset}&limit=30`),
    );
    if (
      !Array.isArray(p.items) ||
      !Number.isInteger(p.total) ||
      Number(p.total) < 0
    )
      return bad();
    return { items: p.items.map(conversation), total: Number(p.total) };
  }
  async create(client_id: string) {
    return conversation(
      await this.client.request("/conversations", {
        method: "POST",
        body: JSON.stringify({ client_id }),
      }),
    );
  }
  async get(id: string, before?: number) {
    const d = detail(
      await this.client.request(
        `/conversations/${encodeURIComponent(id)}${before ? `?before_sequence=${before}` : ""}`,
      ),
    );
    if (d.conversation.id !== id) return bad();
    return d;
  }
  async rename(id: string, title: string) {
    return conversation(
      await this.client.request(`/conversations/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      }),
    );
  }
  remove(id: string) {
    return this.client.request(`/conversations/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  }
  async send(id: string, request_id: string, content: string, timeout: number) {
    const r = record(
      await this.client.request(
        `/conversations/${encodeURIComponent(id)}/messages`,
        { method: "POST", body: JSON.stringify({ request_id, content }) },
        (timeout + 15) * 1000,
      ),
    );
    if (!Array.isArray(r.messages) || typeof r.replayed !== "boolean")
      return bad();
    return {
      request: questionRequest(r.request),
      messages: r.messages.map(message),
      replayed: r.replayed,
    };
  }
}
