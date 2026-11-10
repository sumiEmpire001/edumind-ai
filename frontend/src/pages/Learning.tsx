import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { errorMessage } from "../api/client";
import "./Knowledge.css";
import "./Learning.css";

type Example = {
  id: string;
  question: string;
  answer: string;
  evidence: string;
  status: string;
  split: string;
  reviewed: boolean;
  updated_at: string;
};
type Overview = {
  examples: Record<string, number>;
  training_examples: number;
  evaluation_examples: number;
  searchable_chunks: number;
  queries: number;
  queries_with_sources: number;
  p95_latency_ms: number | null;
  measurement_window: string;
  gates: { name: string; status: string }[];
};
type Result = {
  status: string;
  message: string;
  duration_ms: number;
  sources: {
    id: string;
    title: string;
    excerpt: string;
    location: string;
    kind: string;
  }[];
};

function ReviewForm({
  example,
  busy,
  onSubmit,
}: {
  example: Example;
  busy: boolean;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
}) {
  const [decision, setDecision] = useState(
    example.status === "rejected" ? "rejected" : "approved",
  );
  return (
    <form onSubmit={onSubmit}>
      <label>
        Verified answer
        <textarea
          name="answer"
          required={decision === "approved"}
          minLength={20}
          defaultValue={example.answer}
          maxLength={12000}
        />
      </label>
      <label>
        Evidence and source reference
        <textarea
          name="evidence"
          required={decision === "approved"}
          defaultValue={example.evidence}
          maxLength={2000}
        />
      </label>
      <label>
        Dataset purpose
        <select
          name="split"
          aria-label="Dataset purpose"
          defaultValue={example.split}
          disabled={example.reviewed}
        >
          <option value="train">Training and knowledge search</option>
          <option value="evaluation">Held-out evaluation only</option>
        </select>
      </label>
      {example.reviewed && (
        <input type="hidden" name="split" value={example.split} />
      )}
      <label className="learning-check">
        <input
          type="checkbox"
          name="rights"
          required={decision === "approved"}
        />
        I verified accuracy, removed personal data and confirmed permission to
        reuse this content.
      </label>
      <label>
        Decision
        <select
          name="decision"
          aria-label="Decision"
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
        >
          <option value="approved">Approve</option>
          <option value="rejected">Reject / withdraw from use</option>
        </select>
      </label>
      <button disabled={busy}>Save review</button>
    </form>
  );
}

export default function Learning() {
  const { client, user } = useAuth();
  const admin = user?.role === "admin";
  const [examples, setExamples] = useState<Example[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [offset, setOffset] = useState(0);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [items, stats] = await Promise.all([
        client.request(`/learning/examples?offset=${offset}`),
        admin
          ? client.request("/admin/learning/overview")
          : Promise.resolve(null),
      ]);
      setExamples(items as Example[]);
      setOverview(stats as Overview | null);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  }, [admin, client, offset]);
  useEffect(() => {
    void load();
  }, [load]);
  async function action(work: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  async function nominate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    await action(async () => {
      await client.request("/learning/examples", {
        method: "POST",
        body: JSON.stringify({
          question: data.get("question"),
          consent_to_share: data.get("consent") === "on",
        }),
      });
      form.reset();
      await load();
      setNotice("Question submitted for review. It is not searchable yet.");
    });
  }
  async function review(e: FormEvent<HTMLFormElement>, example: Example) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    await action(async () => {
      await client.request(`/admin/learning/examples/${example.id}/review`, {
        method: "POST",
        body: JSON.stringify({
          status: data.get("decision"),
          answer: data.get("answer"),
          evidence: data.get("evidence"),
          split: data.get("split"),
          rights_confirmed: data.get("rights") === "on",
        }),
      });
      await load();
      setNotice("Review saved. Only approved training answers enter search.");
    });
  }
  async function download(split: string) {
    await action(async () => {
      // Deliberately bounded pages; each download includes its own manifest.
      const page = (await client.request(
        `/admin/learning/dataset?split=${split}&offset=0&limit=500`,
      )) as {
        jsonl: string;
        sha256: string;
        count: number;
        total: number;
        next_offset: number | null;
      };
      if (!page.count) {
        setNotice("No approved examples in this dataset yet.");
        return;
      }
      const blob = new Blob([page.jsonl], { type: "application/x-ndjson" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `edumind-${split}-${page.sha256.slice(0, 12)}.jsonl`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setNotice(
        `Downloaded ${page.count} of ${page.total} reviewed ${split} examples. SHA-256: ${page.sha256}${page.next_offset !== null ? `. More examples are available through the paginated dataset API from offset ${page.next_offset}.` : ""}`,
      );
    });
  }
  if (!user) return null;
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="workspace-main knowledge-page learning-page"
    >
      <p className="eyebrow">EDUMIND KNOWLEDGE API</p>
      <div className="knowledge-heading">
        <div>
          <h1>Knowledge that grows with you.</h1>
          <p>
            Turn useful questions and verified materials into reusable academic
            knowledge.
          </p>
        </div>
        <button className="button button-secondary page-refresh" disabled={busy || loading} onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="knowledge-notice" role="status">
          {notice}
        </p>
      )}
      {loading && <p role="status">Loading learning workspace…</p>}
      <section className="knowledge-card learning-stage">
        <span className="knowledge-status">Foundation · in development</span>
        <h2>An independent knowledge layer</h2>
        <p>
          This API searches reviewed answers and successfully indexed documents
          without Gemini. It returns source excerpts, not newly generated
          answers. Model training and a full Gemini replacement are not active.
        </p>
      </section>
      {admin && overview && (
        <section className="knowledge-card" aria-label="API progress">
          <h2>Progress you can measure</h2>
          <div className="learning-metrics">
            <p>
              <strong>{overview.training_examples}</strong>Approved training
              answers
            </p>
            <p>
              <strong>{overview.evaluation_examples}</strong>Held-out evaluation
              answers
            </p>
            <p>
              <strong>{overview.searchable_chunks}</strong>Searchable document
              passages
            </p>
            <p>
              <strong>{overview.examples.pending}</strong>Questions awaiting
              review
            </p>
          </div>
          <h3>Search observations</h3>
          <p>
            {overview.measurement_window}. Completed requests only; this is not
            a load test or an answer-accuracy score.
          </p>
          <dl className="learning-observations">
            <div>
              <dt>Completed searches</dt>
              <dd>{overview.queries}</dd>
            </div>
            <div>
              <dt>Searches returning sources</dt>
              <dd>{overview.queries_with_sources}</dd>
            </div>
            <div>
              <dt>Search latency, p95</dt>
              <dd>
                {overview.p95_latency_ms === null
                  ? "Not measured"
                  : `${overview.p95_latency_ms} ms`}
              </dd>
            </div>
          </dl>
          <h3>Before replacing Gemini</h3>
          <ul className="learning-gates">
            {overview.gates.map((g) => (
              <li key={g.name}>
                <span>{g.name}</span>
                <strong>{g.status.replaceAll("_", " ")}</strong>
              </li>
            ))}
          </ul>
          <p>
            No automatic switch. A growing document count does not prove model
            accuracy, token capacity or stability.
          </p>
          <div className="knowledge-actions">
            <button disabled={busy} onClick={() => void download("train")}>
              Download training JSONL
            </button>
            <button disabled={busy} onClick={() => void download("evaluation")}>
              Download evaluation JSONL
            </button>
          </div>
          <p>
            Exports contain reviewed question–answer pairs only, up to 500 per
            download. Evaluation examples stay out of search and training
            exports.
          </p>
        </section>
      )}
      <section className="knowledge-card">
        <h2>Try the knowledge API</h2>
        <p>
          Search approved sources directly. Your search text is not saved in API
          metrics or added to training data.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            setResult(null);
            void action(async () => {
              setResult(
                (await client.request("/learning/query", {
                  method: "POST",
                  body: JSON.stringify({ question: data.get("search") }),
                })) as Result,
              );
            });
          }}
        >
          <label>
            Search question
            <input
              name="search"
              required
              minLength={5}
              maxLength={2000}
              placeholder="e.g. Explain Newton’s second law"
            />
          </label>
          <button className="button" disabled={busy}>
            Search knowledge
          </button>
        </form>
        {result && (
          <div role="status" className="learning-results">
            <p>{result.message}</p>
            {result.sources.map((source) => (
              <article key={source.id}>
                <h3>{source.title}</h3>
                <p>
                  {source.kind === "document"
                    ? "Document passage"
                    : "Reviewed answer"}{" "}
                  · {source.location}
                </p>
                <blockquote>{source.excerpt}</blockquote>
              </article>
            ))}
          </div>
        )}
      </section>
      <section className="knowledge-card">
        <h2>Suggest a valuable question</h2>
        <p>
          Share a general academic question, with personal details removed.
          Private chats and attachments are never collected automatically. An
          administrator must verify an answer before reuse.
        </p>
        <form onSubmit={(e) => void nominate(e)}>
          <label>
            Academic question
            <textarea name="question" required minLength={5} maxLength={2000} />
          </label>
          <label className="learning-check">
            <input type="checkbox" name="consent" required />I agree to share
            this question for reviewed knowledge and future model development.
          </label>
          <button className="button" disabled={busy}>
            Submit question for review
          </button>
        </form>
      </section>
      <section className="knowledge-card">
        <h2>{admin ? "Learning review queue" : "Your suggested questions"}</h2>
        {!loading && examples.length === 0 && <p>No questions here yet.</p>}
        <div className="knowledge-items">
          {examples.map((example) => (
            <article key={`${example.id}-${example.updated_at}`}>
              <div className="knowledge-item-title">
                <h3>{example.question}</h3>
                <span className="knowledge-status">{example.status}</span>
              </div>
              {admin ? (
                <ReviewForm
                  example={example}
                  busy={busy}
                  onSubmit={(e) => void review(e, example)}
                />
              ) : (
                <>
                  <p>{example.answer || "Awaiting a verified answer."}</p>
                  <p>{example.evidence}</p>
                </>
              )}
            </article>
          ))}
        </div>
        <div className="knowledge-actions">
          <button
            disabled={offset === 0 || busy || loading}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous questions
          </button>
          <button
            disabled={examples.length < 50 || busy || loading}
            onClick={() => setOffset(offset + 50)}
          >
            Next questions
          </button>
        </div>
      </section>
    </main>
  );
}
