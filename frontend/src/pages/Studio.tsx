import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiError, errorMessage } from "../api/client";
import { Markdown } from "../chat/Markdown";
import { downloadPdf } from "../studio/download";
import "./Studio.css";

type Section = {
  title: string;
  content: string;
  last_request_id: string | null;
};
type Draft = {
  id: string;
  title: string;
  brief: string;
  revision: number;
  target_pages: number;
  sections: Section[];
  word_count: number;
  target_words: number;
  pending: {
    request_id: string;
    index: number;
    revision: number;
    expires_at: string;
    mode: "replace" | "append";
  } | null;
};
const outline = [
  "Introduction",
  "Background and context",
  "Key concepts",
  "Related approaches",
  "Methods and framework",
  "Detailed analysis",
  "Worked examples",
  "Applications",
  "Limitations and discussion",
  "Conclusion and next steps",
].join("\n");
function friendly(cause: unknown) {
  return cause instanceof ApiError && cause.status === 409
    ? "This draft changed or a section is still processing. Reload it before continuing."
    : errorMessage(cause);
}

function SectionEditor({
  section,
  busy,
  onDirty,
  onSave,
}: {
  section: Section;
  busy: boolean;
  onDirty: (value: boolean) => void;
  onSave: (title: string, content: string) => Promise<void>;
}) {
  const [title, setTitle] = useState(section.title);
  const [content, setContent] = useState(section.content);
  const [preview, setPreview] = useState(false);
  return (
    <div className="studio-editor">
      <div className="studio-editor-tools">
        <h2>Section editor</h2>
        <button type="button" onClick={() => setPreview(!preview)}>
          {preview ? "Edit text" : "Preview formatting"}
        </button>
      </div>
      <label>
        Section heading
        <input
          value={title}
          maxLength={100}
          disabled={busy}
          onChange={(e) => {
            setTitle(e.target.value);
            onDirty(
              e.target.value !== section.title || content !== section.content,
            );
          }}
        />
      </label>
      {preview ? (
        <div className="studio-preview">
          <Markdown text={content || "No text drafted yet."} />
        </div>
      ) : (
        <label>
          Section text
          <textarea
            rows={20}
            value={content}
            maxLength={30000}
            disabled={busy}
            onChange={(e) => {
              setContent(e.target.value);
              onDirty(
                e.target.value !== section.content || title !== section.title,
              );
            }}
            placeholder="Generate this section or write your own text. Markdown headings, tables and code are supported."
          />
        </label>
      )}
      <div className="studio-editor-tools">
        <small>
          {content.trim().split(/\s+/).filter(Boolean).length.toLocaleString()}{" "}
          words
        </small>
        <button
          className="button"
          disabled={busy || !title.trim()}
          onClick={() => {
            void onSave(title, content);
          }}
        >
          Save section
        </button>
      </div>
    </div>
  );
}

export default function Studio() {
  const { client } = useAuth();
  const { documentId } = useParams();
  const navigate = useNavigate();
  const selected = useRef(documentId);
  selected.current = documentId;
  const [documents, setDocuments] = useState<Draft[]>([]);
  const [doc, setDoc] = useState<Draft | null>(null);
  const [index, setIndex] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const guard = useRef(false);
  const stop = useRef(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [title, setTitle] = useState("");
  const [brief, setBrief] = useState("");
  const [pages, setPages] = useState(30);
  const [headings, setHeadings] = useState(outline);
  const [available, setAvailable] = useState(false);
  const createId = useRef<string | null>(null);
  const loadList = useCallback(async () => {
    const rows = (await client.request("/documents")) as Draft[];
    if (!Array.isArray(rows)) throw new ApiError(502);
    setDocuments(rows);
  }, [client]);
  useEffect(() => {
    void loadList().catch((e) => setError(friendly(e)));
  }, [loadList]);
  useEffect(() => {
    let active = true;
    void client
      .request("/chat/capabilities")
      .then((c) => {
        if (active) setAvailable(!!(c as { available?: boolean }).available);
      })
      .catch((e) => {
        if (active) setError(friendly(e));
      });
    return () => {
      active = false;
    };
  }, [client]);
  useEffect(() => {
    let active = true;
    setDoc(null);
    setIndex(0);
    setDirty(false);
    setError("");
    setNotice("");
    stop.current = true;
    if (documentId)
      void client
        .request(`/documents/${encodeURIComponent(documentId)}`)
        .then((row) => {
          if (active) setDoc(row as Draft);
        })
        .catch((e) => {
          if (active) setError(friendly(e));
        });
    return () => {
      active = false;
      stop.current = true;
    };
  }, [client, documentId]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  function leave() {
    return !dirty || window.confirm("Leave without saving your section edits?");
  }
  async function create(event: FormEvent) {
    event.preventDefault();
    if (guard.current) return;
    const lines = headings
      .split("\n")
      .map((h) => h.trim())
      .filter(Boolean);
    if (
      lines.length < 3 ||
      lines.length > 18 ||
      lines.some((h) => h.length > 100)
    ) {
      setError(
        "Use 3–18 section headings, one per line, up to 100 characters each.",
      );
      return;
    }
    guard.current = true;
    setBusy(true);
    setError("");
    createId.current ||= crypto.randomUUID();
    try {
      const row = (await client.request("/documents", {
        method: "POST",
        body: JSON.stringify({
          client_id: createId.current,
          title,
          brief,
          target_pages: pages,
          outline: lines,
        }),
      })) as Draft;
      createId.current = null;
      navigate(`/app/studio/${row.id}`);
      await loadList();
    } catch (cause) {
      setError(friendly(cause));
    } finally {
      guard.current = false;
      setBusy(false);
    }
  }
  async function reload() {
    if (!documentId || !leave()) return;
    try {
      setDoc((await client.request(`/documents/${documentId}`)) as Draft);
      setDirty(false);
      setError("");
    } catch (cause) {
      setError(friendly(cause));
    }
  }
  async function save(sectionTitle: string, content: string) {
    if (!doc || guard.current) return;
    guard.current = true;
    setBusy(true);
    setError("");
    try {
      const row = (await client.request(
        `/documents/${doc.id}/sections/${index}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            revision: doc.revision,
            title: sectionTitle,
            content,
          }),
        },
      )) as Draft;
      if (selected.current === doc.id) {
        setDoc(row);
        setDirty(false);
        setNotice("Section saved.");
      }
      await loadList();
    } catch (cause) {
      setError(friendly(cause));
    } finally {
      guard.current = false;
      setBusy(false);
    }
  }
  async function generate(all = false, mode: "replace" | "append" = "replace") {
    if (!doc || guard.current || dirty || !available) return;
    if (
      !all &&
      mode === "replace" &&
      doc.sections[index].content &&
      !doc.pending &&
      !window.confirm("Replace this saved section with a new AI draft?")
    )
      return;
    const id = doc.id;
    guard.current = true;
    stop.current = false;
    setBusy(true);
    setError("");
    let current = doc;
    try {
      const targets = doc.pending
        ? [doc.pending.index]
        : all
          ? doc.sections.flatMap((s, i) => (s.content.trim() ? [] : [i]))
          : [index];
      for (const target of targets) {
        if (stop.current || selected.current !== id) break;
        setIndex(target);
        setNotice(`Drafting section ${target + 1} of ${doc.sections.length}…`);
        const pending = current.pending;
        const data = {
          request_id: pending?.request_id || crypto.randomUUID(),
          revision: pending?.revision || current.revision,
          mode: pending?.mode || mode,
        };
        for (let poll = 0; poll < 35; poll++) {
          current = (await client.request(
            `/documents/${id}/sections/${target}/generate`,
            {
              method: "POST",
              body: JSON.stringify(data),
            },
            45000,
          )) as Draft;
          if (selected.current !== id) return;
          setDoc(current);
          if (!current.pending) break;
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }
        if (current.pending) {
          setNotice(
            "This section is still processing. Use Resume section to recover it.",
          );
          break;
        }
        if (stop.current) break;
      }
      if (selected.current === id)
        setNotice(
          current.pending
            ? "Use Resume section to recover saved progress."
            : stop.current
              ? "Stopped after the current section. Your draft is saved."
              : "Drafting finished. Review and edit the saved text before exporting.",
        );
      await loadList();
    } catch (cause) {
      if (selected.current === id) {
        setError(friendly(cause));
        try {
          setDoc((await client.request(`/documents/${id}`)) as Draft);
        } catch {
          /* Retain the visible draft. */
        }
      }
    } finally {
      guard.current = false;
      setBusy(false);
    }
  }
  async function exportPdf() {
    if (!doc || guard.current || dirty) return;
    guard.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await downloadPdf(client, `/documents/${doc.id}/export`);
      if (selected.current === doc.id)
        setNotice(
          `PDF downloaded: ${result.pages} actual pages, ${result.words?.toLocaleString()} words. Target length is guidance, not a guarantee.`,
        );
    } catch (cause) {
      setError(friendly(cause));
    } finally {
      guard.current = false;
      setBusy(false);
    }
  }
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="workspace-main studio-main"
    >
      <header className="studio-intro">
        <p className="eyebrow">EDUMIND STUDIO</p>
        <h1>From an idea to a document.</h1>
        <p>
          Plan a substantial report, write it section by section, and download a
          formatted PDF.
        </p>
      </header>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      <div className="studio-layout">
        <aside className="studio-drafts">
          <h2>Your drafts</h2>
          <Link
            className="button"
            to="/app/studio"
            onClick={(e) => {
              if (busy || !leave()) e.preventDefault();
            }}
          >
            New document
          </Link>
          {documents.map((d) => (
            <Link
              key={d.id}
              to={`/app/studio/${d.id}`}
              aria-current={d.id === documentId ? "page" : undefined}
              onClick={(e) => {
                if (busy || !leave()) e.preventDefault();
              }}
            >
              {d.title}
              <small>
                {d.word_count.toLocaleString()} words · target {d.target_pages}{" "}
                pages
              </small>
            </Link>
          ))}
        </aside>
        <section className="studio-document" aria-label="Document workspace">
          {!documentId ? (
            <form onSubmit={create} className="studio-create">
              <h2>Start with a clear brief</h2>
              <label>
                Document title
                <input
                  required
                  maxLength={160}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label>
                What should this report cover?
                <textarea
                  required
                  minLength={10}
                  maxLength={1200}
                  rows={5}
                  value={brief}
                  onChange={(e) => setBrief(e.target.value)}
                  placeholder="Describe the topic, audience, required sections and facts or sources you already have."
                />
              </label>
              <label>
                Target length
                <select
                  value={pages}
                  onChange={(e) => setPages(Number(e.target.value))}
                >
                  {[10, 20, 30, 35, 40, 45].map((p) => (
                    <option key={p} value={p}>
                      {p} pages
                    </option>
                  ))}
                </select>
              </label>
              <p className="field-hint">
                A writing budget of about 350 words per target page. The
                exported PDF reports its actual page count; no blank-page
                padding.
              </p>
              <label>
                Outline · one section heading per line
                <textarea
                  rows={12}
                  value={headings}
                  maxLength={1818}
                  onChange={(e) => setHeadings(e.target.value)}
                  required
                />
              </label>
              <button
                className="button"
                disabled={busy || !title.trim() || brief.trim().length < 10}
              >
                {busy ? "Creating…" : "Create document"}
              </button>
            </form>
          ) : !doc ? (
            <p role="status">Opening your document…</p>
          ) : (
            <>
              <div className="studio-document-header">
                <h2>{doc.title}</h2>
                <p>
                  {doc.word_count.toLocaleString()} words /{" "}
                  {doc.target_words.toLocaleString()} target · revision{" "}
                  {doc.revision}
                </p>
                <div className="studio-controls">
                  <button
                    disabled={busy}
                    onClick={() => {
                      void reload();
                    }}
                  >
                    Reload draft
                  </button>
                  <button
                    disabled={busy || dirty || !doc.word_count}
                    onClick={() => {
                      void exportPdf();
                    }}
                  >
                    Download PDF
                  </button>
                  <button
                    disabled={busy || dirty || !available}
                    onClick={() => {
                      void generate(false);
                    }}
                  >
                    {doc.pending
                      ? "Resume section"
                      : "Generate selected section"}
                  </button>
                  <button
                    disabled={
                      busy ||
                      dirty ||
                      !!doc.pending ||
                      !available ||
                      !doc.sections[index].content.trim()
                    }
                    onClick={() => {
                      void generate(false, "append");
                    }}
                  >
                    Expand selected section
                  </button>
                  <button
                    disabled={busy || dirty || !!doc.pending || !available}
                    onClick={() => {
                      void generate(true);
                    }}
                  >
                    Draft remaining sections
                  </button>
                  {busy && (
                    <button
                      onClick={() => {
                        stop.current = true;
                        setNotice("Stopping after the current operation…");
                      }}
                    >
                      Stop after this section
                    </button>
                  )}
                </div>
                {dirty && (
                  <p role="status">
                    Unsaved changes. Save this section before generating or
                    exporting.
                  </p>
                )}
                {!available && (
                  <p>
                    AI drafting is unavailable. You can still write, save and
                    export your own text.
                  </p>
                )}
                <p className="field-hint">
                  Each AI section uses a separate provider request. Saved
                  sections are kept if you stop. Review facts and citations
                  before sharing.
                </p>
              </div>
              <nav className="studio-sections" aria-label="Document sections">
                {doc.sections.map((s, i) => (
                  <button
                    key={i}
                    disabled={busy}
                    aria-current={i === index ? "step" : undefined}
                    onClick={() => {
                      if (leave()) {
                        setIndex(i);
                        setDirty(false);
                      }
                    }}
                  >
                    {i + 1}. {s.title}{" "}
                    <small>
                      {s.content.trim() ? "Drafted" : "Not drafted"}
                    </small>
                  </button>
                ))}
              </nav>
              <SectionEditor
                key={`${doc.id}-${index}-${doc.revision}`}
                section={doc.sections[index]}
                busy={busy || !!doc.pending}
                onDirty={setDirty}
                onSave={save}
              />
            </>
          )}
          <p className="studio-boundary">
            PDF export includes text, tables and code. Complex equations retain
            their source notation. Image generation is not enabled in this
            release.
          </p>
        </section>
      </div>
    </main>
  );
}
