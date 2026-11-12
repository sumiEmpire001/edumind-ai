import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { errorMessage } from "../api/client";

type Draft = { original_pdf_base64: string; version: number; pages: { page: number; text: string }[] };
export function HandwritingReview({ id, pending, processing, onChange }: {
  id: string; pending: boolean; processing: boolean; onChange: () => Promise<void>;
}) {
  const { client } = useAuth();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }
  const unresolved = draft?.pages.some(p => p.text.toLowerCase().includes("[unclear]"));
  return <div className="handwriting-review">
    {error && <p role="alert">{error}</p>}
    {pending ? <>
      <p><strong>Handwriting draft awaiting review — not searchable.</strong></p>
      <button disabled={busy || processing} onClick={() => void run(async () => {
        setDraft(await client.request(`/admin/knowledge/${id}/handwriting`) as Draft);
      })}>Review transcription</button>
    </> : <details>
      <summary>Handwritten PDF?</summary>
      <p>Read up to 10 pages using Gemini vision. Page images are sent to your configured Gemini service and use its API quota. The document stays out of search until an admin checks the transcription.</p>
      <button disabled={busy || processing} onClick={() => void run(async () => {
        await client.request(`/admin/knowledge/${id}/handwriting`, { method: "POST" });
        setDraft(null); await onChange();
      })}>Read handwriting</button>
    </details>}
    {draft && pending && <form onSubmit={event => {
      event.preventDefault();
      void run(async () => {
        await client.request(`/admin/knowledge/${id}/handwriting/approve`, {
          method: "POST", body: JSON.stringify({ version: draft.version, pages: draft.pages }),
        });
        setDraft(null); await onChange();
      });
    }}>
      <a download="original-handwritten-document.pdf" href={`data:application/pdf;base64,${draft.original_pdf_base64}`}>Download original PDF for comparison</a>
      <p>Compare every page with the original PDF. Correct words, numbers and equations. Replace all [unclear] markers with verified text before approving.</p>
      {draft.pages.map((page, index) => <label key={page.page}>
        Page {page.page}
        <textarea rows={8} maxLength={20000} value={page.text} disabled={busy}
          onChange={event => setDraft({ ...draft, pages: draft.pages.map((p, i) => i === index ? { ...p, text: event.target.value } : p) })} />
      </label>)}
      {unresolved && <p role="status">There are still [unclear] markers to resolve.</p>}
      <button disabled={busy || unresolved || !draft.pages.some(p => p.text.trim())}>Approve checked transcription</button>
      <button type="button" disabled={busy} onClick={() => setDraft(null)}>Close</button>
    </form>}
  </div>;
}
