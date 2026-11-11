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
  saveDownload(data.base64, "application/pdf", "pdf", "%PDF-");
  return { pages: data.page_count, words: data.word_count };
}

const wordType = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export async function downloadWord(client: SessionClient, path: string) {
  const data = await client.request(path, { method: "POST" }, 45000) as {
    media_type?: string;
    base64?: string;
  };
  if (data.media_type !== wordType || typeof data.base64 !== "string" || data.base64.length > 12_000_000)
    throw new ApiError(502);
  saveDownload(data.base64, wordType, "docx", "PK\x03\x04");
}

function saveDownload(base64: string, mime: string, extension: string, signature: string) {
  let raw: string;
  try {
    raw = atob(base64);
  } catch {
    throw new ApiError(502);
  }
  if (!raw.startsWith(signature)) throw new ApiError(502);
  const bytes = Uint8Array.from(raw, (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(
    new Blob([bytes], { type: mime }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `EduMind-document.${extension}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
