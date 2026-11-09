import { useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Markdown } from "../chat/Markdown";
import { Icon } from "../components/Icon";
import "./Research.css";

type WebLink = { title: string; url: string };
type ResearchResult = { answer: string; sources: WebLink[]; suggestions: WebLink[] };

const prompts = [
  "What does LAUTECH publish about undergraduate admissions? Find official university pages and date any deadlines.",
  "Find the latest publicly available academic calendar on the official LAUTECH website. Which session does it cover?",
  "Find recent primary sources explaining how Nigeria regulates personal data protection.",
];

function Links({ items }: { items: WebLink[] }) {
  return (
    <ul className="research-links">
      {items.map(({ title, url }) => (
        <li key={url}>
          <a href={url} target="_blank" rel="noopener noreferrer">
            {title} <span aria-hidden="true">↗</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

export default function Research() {
  const { client, user } = useAuth();
  const admin = user?.role === "admin";
  const [params] = useSearchParams();
  const [question, setQuestion] = useState(params.get("topic") === "lautech" ? prompts[0] : "");
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reviewStatus, setReviewStatus] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [submitted, setSubmitted] = useState("");
  const inFlight = useRef(false);

  async function search(event: FormEvent) {
    event.preventDefault();
    const query = question.trim();
    if (query.length < 5 || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    setResult(null);
    setReviewStatus("");
    setSubmitted(query);
    try {
      const reply = await client.request("/research", {
        method: "POST",
        body: JSON.stringify({ question: query }),
      }, 55_000) as ResearchResult;
      setResult(reply);
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 424
          ? "The search returned no verifiable sources. Try adding a website, date, or exact topic."
          : cause instanceof ApiError && cause.status === 504
            ? "The search took too long. Try a more specific question."
            : errorMessage(cause),
      );
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function suggest() {
    if (reviewBusy || !submitted || !result) return;
    setReviewBusy(true);
    setReviewStatus("");
    try {
      // Keep complete URLs and only include links that fit the evidence field.
      const evidence: string[] = [];
      for (const source of result.sources) {
        const entry = `${source.title} — ${source.url}`;
        if ([...evidence, entry].join("\n").length <= 2000) evidence.push(entry);
      }
      const saveDraft = admin && evidence.length > 0 && result.answer.length >= 20;
      await client.request(saveDraft ? "/admin/learning/drafts" : "/learning/examples", {
        method: "POST",
        body: JSON.stringify(saveDraft
          ? { question: submitted, answer: result.answer, evidence: evidence.join("\n") }
          : { question: submitted, consent_to_share: true }),
      });
      setReviewStatus(saveDraft
        ? "Draft and sources saved. Verify them in the Knowledge API review queue."
        : "Question sent to the Knowledge API review queue.");
    } catch (cause) {
      setReviewStatus(
        cause instanceof ApiError && cause.status === 409
          ? "This question is already in the review queue."
          : errorMessage(cause),
      );
    } finally {
      setReviewBusy(false);
    }
  }

  return (
    <main id="main-content" tabIndex={-1} className="workspace-main research-page">
      <header className="research-hero">
        <span className="eyebrow"><Icon name="search" /> Live web search</span>
        <h1>Web research</h1>
        <p>Look up current information and follow the sources behind the answer.</p>
      </header>
      <form className="research-card research-form" onSubmit={search}>
        <label htmlFor="research-question">What do you want to research?</label>
        <textarea
          id="research-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a question or name a topic, place, and date"
          rows={4}
          required
          minLength={5}
          maxLength={2000}
          disabled={busy}
        />
        <div className="research-actions">
          <span>Search sends this question to Google Gemini.</span>
          <button className="button" disabled={busy || reviewBusy || question.trim().length < 5}>
            <Icon name="search" /> {busy ? "Searching…" : "Search the web"}
          </button>
        </div>
      </form>
      {busy && <p role="status" className="research-card">Searching the web and checking sources…</p>}
      {error && <p role="alert" className="error-banner">{error}</p>}
      {result ? (
        <article className="research-card research-result" aria-label="Research result">
          <p className="eyebrow">Search result</p>
          <h2>{submitted}</h2>
          <Markdown text={result.answer} allowLinks={false} />
          <section aria-labelledby="research-sources">
            <h3 id="research-sources">Sources returned by web search</h3>
            <Links items={result.sources} />
          </section>
          {result.suggestions.length > 0 && (
            <section aria-labelledby="research-related">
              <h3 id="research-related">Related searches on Google</h3>
              <Links items={result.suggestions} />
            </section>
          )}
          <div className="research-share">
            <button className="button button-secondary" type="button" onClick={() => void suggest()} disabled={reviewBusy}>
              {reviewBusy ? "Sending…" : admin ? "Save research draft for review" : "Share question for review"}
            </button>
            <p>
              {admin ? "Review the answer and source links before approving it for search." : "Only the question is sent to the Knowledge API review queue."}
              {" "}<Link to="/app/learning">Open Knowledge API</Link>
            </p>
            {reviewStatus && <p role="status">{reviewStatus}</p>}
          </div>
        </article>
      ) : !busy && (
        <section className="research-card" aria-labelledby="research-examples">
          <h2 id="research-examples">Research starting points</h2>
          <ul className="research-prompts">
            {prompts.map((prompt) => (
              <li key={prompt}><button type="button" onClick={() => setQuestion(prompt)}>{prompt} <Icon name="arrow" /></button></li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
