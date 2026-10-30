import { expect, it, vi } from "vitest";
import { ChatApi, detail, message } from "./api";
import { SessionClient } from "../auth/session";
const cid = "e94f285d-5bb8-46bf-bfd7-f7d94bdab421";
it("rejects malformed messages and details before displaying them", () => {
  expect(() =>
    message({ id: cid, content: "<script>bad</script>", role: "system" }),
  ).toThrow();
  expect(() =>
    detail({ conversation: {}, messages: [], requests: [], has_older: false }),
  ).toThrow();
});
it("preserves the request ID and uses a provider-aware timeout", async () => {
  const client = new SessionClient();
  const rid = "e94f285d-5bb8-46bf-bfd7-f7d94bdab422";
  const request = vi
    .spyOn(client, "request")
    .mockResolvedValue({
      request: {
        id: rid,
        status: "pending",
        error_code: null,
        deadline_at: "2026-10-30T12:00:00Z",
      },
      messages: [],
      replayed: true,
    });
  await new ChatApi(client).send(cid, rid, "Question", 20);
  expect(request).toHaveBeenCalledWith(
    `/conversations/${cid}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ request_id: rid, content: "Question", attachment_ids: [] }),
    },
    35000,
  );
});
