import { useCallback, useEffect, useState, type FormEvent } from "react";
import { InboxSettings } from "../components/InboxSettings";
import { useAuth } from "../auth/AuthContext";
import { errorMessage } from "../api/client";
import "./Knowledge.css";

type Submission = {
  id: string;
  title: string;
  filename: string;
  description: string;
  discipline: string;
  status: string;
  reason: string | null;
  processing_status: string | null;
  active: boolean;
};
type Application = {
  id: string;
  user_id: string;
  statement: string;
  status: string;
  reason: string | null;
};
type Document = {
  id: string;
  submission_id: string;
  version: number;
  processing_status: string;
  active: boolean;
};
type Member = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
};
type Preview = { text: string; metadata: Record<string, unknown> };
const mimes: Record<string, string> = {
  pdf: "application/pdf",
  txt: "text/plain",
  csv: "text/csv",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
};

export default function Knowledge() {
  const { client, user } = useAuth();
  const admin = user?.role === "admin";
  const contributor = user?.role === "contributor" || admin;
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [mine, setMine] = useState<Application | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [statistics, setStatistics] = useState<Record<string, unknown> | null>(
    null,
  );
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [storageAvailable, setStorageAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const capabilities = (await client.request(
        "/knowledge/capabilities",
      )) as { storage_available: boolean };
      setStorageAvailable(capabilities.storage_available);
      const result = (await client.request(
        `/knowledge/submissions?offset=${offset}`,
      )) as Submission[];
      setSubmissions(result);
      if (admin) {
        const [a, d, u, s] = await Promise.all([
          client.request("/admin/contributor-applications"),
          client.request("/admin/knowledge"),
          client.request("/admin/users?limit=100"),
          client.request("/admin/statistics"),
        ]);
        setApplications(a as Application[]);
        setDocuments(d as Document[]);
        setMembers((u as { items: Member[] }).items);
        setStatistics(s as Record<string, unknown>);
      } else
        setMine(
          (await client.request(
            "/contributor/application",
          )) as Application | null,
        );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  }, [client, admin, offset]);
  useEffect(() => {
    void load();
  }, [load]);

  async function action(fn: () => Promise<unknown>, message: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      setNotice(message);
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!storageAvailable) {
      setError("Private document storage is not configured yet.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("file") as File;
    if (!file?.size || file.size > 3 * 1024 * 1024) {
      setError("Choose a document up to 3 MB.");
      return;
    }
    const mime = mimes[file.name.split(".").pop()?.toLowerCase() || ""];
    if (!mime) {
      setError("Choose a PDF, DOCX, TXT, CSV or PPTX file.");
      return;
    }
    const query = new URLSearchParams({
      title: String(data.get("title")),
      filename: file.name,
      description: String(data.get("description")),
      discipline: String(data.get("discipline")),
    });
    await action(async () => {
      await client.request(
        `/knowledge/submissions?${query}`,
        { method: "POST", headers: { "Content-Type": mime }, body: file },
        45000,
      );
      form.reset();
    }, "Submitted for administrator review. It is not searchable yet.");
  }
  function review(path: string, id: string, decision: "approved" | "rejected") {
    const reason = reasons[id] || "";
    if (decision === "rejected" && !reason.trim()) {
      setError("Enter a rejection reason first.");
      return;
    }
    void action(
      () =>
        client.request(path, {
          method: "POST",
          body: JSON.stringify({ decision, reason }),
        }),
      decision === "approved"
        ? "Approved. Documents become searchable only after processing succeeds."
        : "Rejected with your reason.",
    );
  }
  if (!user) return null;
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="workspace-main knowledge-page"
    >
      <p className="eyebrow">THE KNOWLEDGE LIBRARY</p>
      <div className="knowledge-heading">
        <div>
          <h1>{admin ? "Review. Verify. Share." : "Help knowledge grow."}</h1>
          <p>
            Academic materials become part of EduMind only after review and
            successful processing.
          </p>
        </div>
        <button disabled={busy || loading} onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="knowledge-notice">
          {notice}
        </p>
      )}
      {loading && <p role="status">Loading knowledge workspace…</p>}
      {!contributor && (
        <section className="knowledge-card">
          <h2>Become a contributor</h2>
          {mine ? (
            <>
              <p>
                Application: <strong>{mine.status}</strong>
              </p>
              {mine.reason && <p>{mine.reason}</p>}
              <p>
                After approval, sign in again to activate your contributor
                permissions.
              </p>
            </>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const data = new FormData(e.currentTarget);
                void action(
                  () =>
                    client.request("/contributor/application", {
                      method: "POST",
                      body: JSON.stringify({
                        statement: data.get("statement"),
                      }),
                    }),
                  "Your application is awaiting review.",
                );
              }}
            >
              <label>
                What materials would you like to contribute?
                <textarea
                  name="statement"
                  required
                  minLength={20}
                  maxLength={2000}
                />
              </label>
              <button className="button" disabled={busy}>
                Apply to contribute
              </button>
            </form>
          )}
        </section>
      )}
      {contributor && (
        <section className="knowledge-card">
          <h2>Submit learning material</h2>
          <p>
            PDF, DOCX, TXT, CSV or PPTX · up to 3 MB · text-based documents only
          </p>
          {!storageAvailable && (
            <p role="status">
              Private document storage is awaiting configuration. Uploads will
              open when it is connected.
            </p>
          )}
          <form onSubmit={(e) => void upload(e)} className="knowledge-upload">
            <label>
              Title
              <input name="title" required maxLength={200} />
            </label>
            <label>
              Discipline
              <input
                name="discipline"
                maxLength={100}
                placeholder="e.g. Physics"
              />
            </label>
            <label>
              Description
              <textarea name="description" maxLength={2000} />
            </label>
            <label>
              Document
              <input
                name="file"
                type="file"
                required
                accept=".pdf,.docx,.txt,.csv,.pptx"
              />
            </label>
            <button className="button" disabled={busy || !storageAvailable}>
              {busy ? "Working…" : "Submit for review"}
            </button>
          </form>
        </section>
      )}
      {admin && (
        <section className="knowledge-card">
          <h2>Platform overview</h2>
          {statistics && (
            <div className="knowledge-metrics">
              <p>
                <strong>{String(statistics.users)}</strong> users
              </p>
              <p>
                <strong>{String(statistics.submissions)}</strong> submissions
              </p>
              <p>
                <strong>{String(statistics.active_documents)}</strong>{" "}
                searchable documents
              </p>
            </div>
          )}
        </section>
      )}
      <section className="knowledge-card">
        <h2>{admin ? "Knowledge inbox" : "Your submissions"}</h2>
        {!loading && submissions.length === 0 && (
          <p>No submissions here yet.</p>
        )}
        <div className="knowledge-items">
          {submissions.map((s) => (
            <article key={s.id}>
              <div className="knowledge-item-title">
                <h3>{s.title}</h3>
                <span className="knowledge-status">{s.status}</span>
              </div>
              <p>
                {s.filename} · {s.discipline || "Discipline not supplied"}
              </p>
              <p>{s.description}</p>
              {s.processing_status && (
                <p>
                  Processing: <strong>{s.processing_status}</strong> ·{" "}
                  {s.active ? "Searchable" : "Not searchable"}
                </p>
              )}
              {s.reason && <p>Review reason: {s.reason}</p>}
              <button
                disabled={busy}
                onClick={() =>
                  void action(
                    async () =>
                      setPreview(
                        (await client.request(
                          `/knowledge/submissions/${s.id}/preview-data`,
                          {},
                          45000,
                        )) as Preview,
                      ),
                    "Preview opened below.",
                  )
                }
              >
                Preview document text
              </button>
              {admin && s.status === "pending" && (
                <div className="knowledge-review">
                  <label>
                    Rejection reason
                    <textarea
                      aria-label={`Reason for ${s.title}`}
                      value={reasons[s.id] || ""}
                      onChange={(e) =>
                        setReasons({ ...reasons, [s.id]: e.target.value })
                      }
                      maxLength={1000}
                    />
                  </label>
                  <button
                    disabled={busy}
                    onClick={() =>
                      review(
                        `/admin/submissions/${s.id}/review`,
                        s.id,
                        "approved",
                      )
                    }
                  >
                    Approve
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      review(
                        `/admin/submissions/${s.id}/review`,
                        s.id,
                        "rejected",
                      )
                    }
                  >
                    Reject
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
        <div className="knowledge-actions">
          <button
            disabled={!offset || busy}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous
          </button>
          <button
            disabled={submissions.length < 50 || busy}
            onClick={() => setOffset(offset + 50)}
          >
            Next
          </button>
        </div>
      </section>
      {preview && (
        <section className="knowledge-card">
          <div className="knowledge-item-title">
            <h2>Document preview</h2>
            <button onClick={() => setPreview(null)}>Close preview</button>
          </div>
          <dl>
            {Object.entries(preview.metadata).map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll("_", " ")}</dt>
                <dd>{String(value)}</dd>
              </div>
            ))}
          </dl>
          <pre className="knowledge-preview">{preview.text}</pre>
        </section>
      )}
      {admin && (
        <>
          <InboxSettings />
          <section className="knowledge-card">
            <h2>Contributor applications</h2>
            {applications.length === 0 && <p>No applications yet.</p>}
            {applications.map((a) => (
              <article className="knowledge-application" key={a.id}>
                <p>{a.statement}</p>
                <p>Status: {a.status}</p>
                {a.status === "pending" && (
                  <>
                    <label>
                      Rejection reason
                      <input
                        value={reasons[a.id] || ""}
                        onChange={(e) =>
                          setReasons({ ...reasons, [a.id]: e.target.value })
                        }
                      />
                    </label>
                    <div className="knowledge-actions">
                      <button
                        disabled={busy}
                        onClick={() =>
                          review(
                            `/admin/contributor-applications/${a.id}/review`,
                            a.id,
                            "approved",
                          )
                        }
                      >
                        Approve contributor
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          review(
                            `/admin/contributor-applications/${a.id}/review`,
                            a.id,
                            "rejected",
                          )
                        }
                      >
                        Reject application
                      </button>
                    </div>
                  </>
                )}
                {a.reason && <p>{a.reason}</p>}
              </article>
            ))}
          </section>
          <section className="knowledge-card">
            <h2>Approved knowledge & processing</h2>
            {documents.length === 0 && <p>No approved documents yet.</p>}
            {documents.map((d) => (
              <article key={d.id}>
                <h3>
                  {submissions.find((s) => s.id === d.submission_id)?.title ||
                    "Approved document"}
                </h3>
                <p>
                  Version {d.version} · {d.processing_status} ·{" "}
                  {d.active ? "Searchable" : "Excluded"}
                </p>
                <div className="knowledge-actions">
                  <button
                    disabled={
                      busy ||
                      ["queued", "processing"].includes(d.processing_status)
                    }
                    onClick={() =>
                      void action(
                        () =>
                          client.request(`/admin/knowledge/${d.id}/reindex`, {
                            method: "POST",
                          }),
                        "Re-indexing queued; prior version excluded.",
                      )
                    }
                  >
                    Re-index
                  </button>
                  <button
                    disabled={busy || d.processing_status === "failed"}
                    onClick={() => {
                      if (
                        window.confirm(
                          "Remove this document from student retrieval?",
                        )
                      )
                        void action(
                          () =>
                            client.request(`/admin/knowledge/${d.id}`, {
                              method: "DELETE",
                            }),
                          "Removed from retrieval.",
                        );
                    }}
                  >
                    Remove from retrieval
                  </button>
                </div>
              </article>
            ))}
          </section>
          <section className="knowledge-card">
            <h2>User management</h2>
            {members.map((m) => (
              <article key={m.id}>
                <h3>{m.full_name}</h3>
                <p>
                  {m.email} · {m.role} · {m.is_active ? "Active" : "Disabled"}
                </p>
                {m.role !== "admin" && (
                  <div className="knowledge-actions">
                    <button
                      disabled={busy}
                      onClick={() =>
                        void action(
                          () =>
                            client.request(`/admin/users/${m.id}`, {
                              method: "PATCH",
                              body: JSON.stringify({ is_active: !m.is_active }),
                            }),
                          "Account updated; existing sessions revoked.",
                        )
                      }
                    >
                      {m.is_active ? "Disable account" : "Enable account"}
                    </button>
                  </div>
                )}
              </article>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
