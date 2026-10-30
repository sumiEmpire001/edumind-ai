import { ApiError } from "../api/client";
import type { SessionClient } from "../auth/session";

export async function downloadPdf(
  client: SessionClient,
  path: string,
  body: object = {},
) {
  const data = (await client.request(
    path,
    { method: "POST", body: JSON.stringify(body) },
    45000,
  )) as {
    base64?: string;
    media_type?: string;
    page_count?: number;
    word_count?: number;
  };
  if (
    data.media_type !== "application/pdf" ||
    typeof data.base64 !== "string" ||
    data.base64.length > 12_000_000 ||
    !Number.isInteger(data.page_count)
  )
    throw new ApiError(502);
  let raw: string;
  try {
    raw = atob(data.base64);
  } catch {
    throw new ApiError(502);
  }
  if (!raw.startsWith("%PDF-")) throw new ApiError(502);
  const bytes = Uint8Array.from(raw, (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(
    new Blob([bytes], { type: "application/pdf" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "EduMind-document.pdf";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return { pages: data.page_count, words: data.word_count };
}
