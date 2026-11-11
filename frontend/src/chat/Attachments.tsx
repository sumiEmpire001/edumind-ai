import { useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { errorMessage } from "../api/client";
import type { SessionClient } from "../auth/session";
import "./Attachments.css";

const attachmentTypes = new Map([
  ["txt", "text/plain"],
  ["pdf", "application/pdf"],
  ["png", "image/png"],
  ["jpg", "image/jpeg"],
  ["jpeg", "image/jpeg"],
]);

export type Attachment = {
  id: string;
  filename: string;
  mime: string;
  size: number;
};

export function ImagePreview({
  client,
  conversationId,
  item,
}: {
  client: SessionClient;
  conversationId: string;
  item: Attachment;
}) {
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function preview() {
    if (busy) return;
    if (source) {
      setSource("");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = (await client.request(
        `/conversations/${conversationId}/attachments/${item.id}/preview`,
      )) as { mime: string; base64: string };
      if (
        result.mime !== "image/jpeg" ||
        typeof result.base64 !== "string" ||
        result.base64.length > 500000
      )
        throw new Error();
      setSource(`data:image/jpeg;base64,${result.base64}`);
    } catch {
      setError("Image preview is unavailable.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="attachment-preview">
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          void preview();
        }}
      >
        {source ? "Hide image" : `Preview image ${item.filename}`}
      </button>
      {source && (
        <img src={source} alt={`Attachment: ${item.filename}`} width={180} />
      )}
      {error && <small role="status">{error}</small>}
    </div>
  );
}

export function PdfCitation({
  client,
  conversationId,
  attachmentId,
  page,
  label,
}: {
  client: SessionClient;
  conversationId: string;
  attachmentId: string;
  page: number;
  label: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [excerpt, setExcerpt] = useState<{ filename: string; text: string }>();
  const [error, setError] = useState("");
  async function show() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    setError("");
    if (excerpt || loading) return;
    setLoading(true);
    try {
      const result = await client.request(
        `/conversations/${conversationId}/attachments/${attachmentId}/pages/${page}`,
      ) as { filename: string; text: string };
      setExcerpt(result);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  }

  return (
    <span className="pdf-citation">
      <button type="button" aria-expanded={open} onClick={() => void show()}>
        {label}
      </button>
      {open && (
        <span className="pdf-citation-excerpt" role="status">
          {excerpt ? (
            <>
              <strong>{excerpt.filename} · Page {page}</strong>
              <span>{excerpt.text}</span>
            </>
          ) : error || "Loading cited page…"}
        </span>
      )}
    </span>
  );
}

export function Attachments({
  client,
  conversationId,
  available,
  disabled,
  value,
  onChange,
  onBusy,
}: {
  client: SessionClient;
  conversationId: string;
  available: boolean;
  disabled: boolean;
  value: Attachment[];
  onChange: (items: Attachment[]) => void;
  onBusy: (busy: boolean) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const guard = useRef(false);
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (guard.current || !files.length) return;
    if (files.length + value.length > 2) {
      setError("Attach up to two files per question.");
      return;
    }
    if (files.some((f) => f.size > 1024 * 1024)) {
      setError("Each file must be at most 1 MB.");
      return;
    }
    guard.current = true;
    setBusy(true);
    onBusy(true);
    setError("");
    const items = [...value];
    try {
      for (const file of files) {
        const ext = file.name.split(".").pop()?.toLowerCase();
        const mime = attachmentTypes.get(ext ?? "");
        if (!mime) throw new Error("Use PNG, JPEG, UTF-8 TXT or text-based PDF files.");
        const item = (await client.request(
          `/conversations/${conversationId}/attachments?filename=${encodeURIComponent(file.name)}`,
          { method: "POST", headers: { "Content-Type": mime }, body: file },
          30000,
        )) as Attachment;
        if (!item.id || !item.filename)
          throw new Error("Attachment upload was not confirmed.");
        items.push(item);
        onChange([...items]);
      }
    } catch (cause) {
      setError(
        cause instanceof Error && !("status" in cause)
          ? cause.message
          : errorMessage(cause),
      );
    } finally {
      guard.current = false;
      setBusy(false);
      onBusy(false);
    }
  }
  async function remove(item: Attachment) {
    if (guard.current) return;
    guard.current = true;
    setBusy(true);
    onBusy(true);
    setError("");
    try {
      await client.request(
        `/conversations/${conversationId}/attachments/${item.id}`,
        { method: "DELETE" },
      );
      onChange(value.filter((v) => v.id !== item.id));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      guard.current = false;
      setBusy(false);
      onBusy(false);
    }
  }
  return (
    <div className="chat-attachments">
      <label className="attachment-label">
        Attach an image, note or PDF
        <input
          aria-label="Attach an image, note or PDF"
          type="file"
          accept=".png,.jpg,.jpeg,.txt,.pdf"
          multiple
          disabled={!available || disabled || busy || value.length >= 2}
          onChange={(e) => {
            void upload(e);
          }}
        />
      </label>
      <small>
        {available
          ? "PNG, JPEG, TXT or text-based PDF · two files · 1 MB each. PDFs can have up to 20 pages and 12,000 text characters."
          : "Attachments will be available after private file storage is configured."}
      </small>
      {value.map((item) => (
        <div key={item.id} className="attachment-chip">
          <span>{item.filename}</span>
          {item.mime.startsWith("image/") && (
            <ImagePreview
              client={client}
              conversationId={conversationId}
              item={item}
            />
          )}
          <button
            type="button"
            disabled={busy || disabled}
            onClick={() => {
              void remove(item);
            }}
            aria-label={`Remove attachment ${item.filename}`}
          >
            Remove
          </button>
        </div>
      ))}
      {busy && <p role="status">Saving your private attachment…</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
