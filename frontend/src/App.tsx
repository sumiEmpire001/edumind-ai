import { useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { getReadiness } from "./api/client";

function Foundation() {
  const [status, setStatus] = useState("Connection not checked");
  const [checking, setChecking] = useState(false);
  async function check() {
    if (checking) return;
    setChecking(true);
    setStatus("Checking backend and database…");
    try {
      await getReadiness();
      setStatus("Backend and database are ready");
    } catch {
      setStatus(
        "Service unavailable. Check the backend, database, and migrations.",
      );
    } finally {
      setChecking(false);
    }
  }
  return (
    <>
      <header>
        <Link className="brand" to="/">
          <span className="mark">E</span> EduMind <span className="ai">AI</span>
        </Link>
        <span className="badge">Phase 01 · Foundation</span>
      </header>
      <main>
        <section className="intro">
          <p className="eyebrow">A clearer path to understanding</p>
          <h1>
            Learn the why.
            <br />
            <span>Build the understanding.</span>
          </h1>
          <p className="lead">
            An academic companion built to help you work through ideas, connect
            concepts, and learn with confidence.
          </p>
          <div className="principle">
            <span aria-hidden="true">↗</span>
            <p>
              Our philosophy
              <strong>Teach students, not just answer questions.</strong>
            </p>
          </div>
        </section>
        <section className="foundation" aria-labelledby="foundation-title">
          <p className="eyebrow">Development workspace</p>
          <h2 id="foundation-title">
            Good learning starts
            <br />
            with a strong foundation.
          </h2>
          <p>
            This initial milestone establishes the frontend, API, and database
            setup. Student accounts, AI conversations, and document review will
            arrive in later phases.
          </p>
          <div className="status">
            <span className="status-label">System connection</span>
            <p role="status" aria-live="polite">
              {status}
            </p>
            <button onClick={check} disabled={checking}>
              {checking ? "Checking…" : "Check connection"}
              <span aria-hidden="true"> ↗</span>
            </button>
          </div>
          <p className="note">
            This is a development foundation. Academic AI features are not
            available yet.
          </p>
        </section>
        <section className="pillars" aria-label="Platform principles">
          {[
            [
              "01",
              "Understand deeply",
              "Clear explanations, worked steps, and meaningful follow-up.",
            ],
            [
              "02",
              "Learn from sources",
              "Academic materials reviewed before they enter the knowledge base.",
            ],
            [
              "03",
              "Built with care",
              "Role permissions, private documents, and verified development.",
            ],
          ].map(([n, t, d]) => (
            <article key={n}>
              <span>{n}</span>
              <h2>{t}</h2>
              <p>{d}</p>
            </article>
          ))}
        </section>
      </main>
      <footer>
        <span>EduMind AI</span>
        <span>Thoughtful learning. From the ground up.</span>
      </footer>
    </>
  );
}
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Foundation />} />
      <Route
        path="*"
        element={
          <main>
            <h1>Page not found</h1>
            <Link to="/">Return to EduMind AI</Link>
          </main>
        }
      />
    </Routes>
  );
}
