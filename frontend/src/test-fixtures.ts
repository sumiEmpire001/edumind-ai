import type { User } from "./auth/session";
export const user: User = {
  id: "cfd1cbe6-fd15-421e-aef2-382abbef23d1",
  email: "learner@example.com",
  full_name: "Test Learner",
  role: "student",
  is_active: true,
  created_at: "2026-10-30T12:00:00Z",
};
export const bundle = (token = "test-access") => ({
  access_token: token,
  token_type: "bearer",
  expires_in: 600,
  csrf_token: "test-csrf",
  user,
});
export function json(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}
export const pathOf = (input: string | URL | Request) =>
  new URL(
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : input.url,
    "http://localhost",
  ).pathname;
