import { expect, it, vi } from "vitest";
import { SessionClient } from "../auth/session";
import { downloadPdf } from "./download";

it("rejects an HTML response instead of downloading it as PDF", async () => {
  const client = new SessionClient();
  vi.spyOn(client, "request").mockResolvedValue({
    media_type: "application/pdf",
    base64: btoa("<html>error</html>"),
    page_count: 1,
  });
  await expect(
    downloadPdf(client, "/documents/test/export"),
  ).rejects.toMatchObject({ status: 502 });
});
it("downloads validated PDF bytes and reports their actual page count", async () => {
  vi.useFakeTimers();
  const client = new SessionClient();
  vi.spyOn(client, "request").mockResolvedValue({
    media_type: "application/pdf",
    base64: btoa("%PDF-1.4\nfixture"),
    page_count: 3,
    word_count: 25,
  });
  const create = vi.fn().mockReturnValue("blob:fixture");
  vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: vi.fn() });
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  try {
    expect(await downloadPdf(client, "/documents/test/export")).toEqual({
      pages: 3,
      words: 25,
    });
    expect(create).toHaveBeenCalled();
    expect(click).toHaveBeenCalledOnce();
    await vi.runAllTimersAsync();
  } finally {
    click.mockRestore();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  }
});
