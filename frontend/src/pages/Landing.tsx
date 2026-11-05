import { Icon } from "../components/Icon";
import { Link } from "react-router-dom";
import { PublicHeader } from "../components/PublicHeader";
export function Landing() {
  return (
    <>
      <PublicHeader />
      <main id="main-content" tabIndex={-1}>
        <section className="hero page-width">
          <div className="hero-copy">
            <div className="launch-label">
              <span aria-hidden="true" /> Your academic companion
            </div>
            <h1>
              Learn the why.
              <br />
              <em>Go further.</em>
            </h1>
            <p className="hero-lead">
              Ask better questions. Build thoughtful documents. Bring your
              learning together in one focused workspace.
            </p>
            <div className="hero-actions">
              <Link className="button" to="/register">
                Create your account <Icon name="arrow" />
              </Link>
              <Link className="text-link" to="/login">
                I already have an account <span aria-hidden="true">→</span>
              </Link>
            </div>
            <p className="early-note">
              Study chat · Document Studio · PDF exports
            </p>
          </div>
          <div
            className="study-visual"
            aria-label="How EduMind helps you learn"
          >
            <div className="study-tab">
              A workspace for your next idea <span aria-hidden="true">✦</span>
            </div>
            <div className="study-paper">
              <span className="paper-label">LEARN. CREATE. REFINE.</span>
              <p className="paper-title">
                Good work starts
                <br />
                with a little <em>clarity.</em>
              </p>
              <div className="learning-step">
                <span>01</span>
                <div>
                  <strong>Explore with study chat</strong>
                  <p>Keep questions and follow-ups together.</p>
                </div>
              </div>
              <div className="learning-step">
                <span>02</span>
                <div>
                  <strong>Create in Document Studio</strong>
                  <p>Organize your ideas, one section at a time.</p>
                </div>
              </div>
              <div className="learning-step">
                <span>03</span>
                <div>
                  <strong>Take your work with you</strong>
                  <p>Review your draft and export it as a PDF.</p>
                </div>
              </div>
              <div className="paper-bottom">
                <span>Curiosity → Clarity</span>
                <Icon name="arrow" />
              </div>
            </div>
            <div className="visual-caption">
              Made for the way your mind works.
            </div>
          </div>
        </section>
        <section className="approach-section" id="approach">
          <div className="page-width">
            <div className="section-heading">
              <p className="eyebrow">Learning, with intention</p>
              <h2>
                Understanding is
                <br />
                the whole point.
              </h2>
              <p>
                From a difficult concept to a structured report, keep your
                attention on the work that matters.
              </p>
            </div>
            <div className="principles">
              {[
                [
                  "01",
                  "A conversation that stays with you",
                  "Ask questions, attach an image or text note, and return to your saved conversations. AI availability depends on the service limits.",
                ],
                [
                  "02",
                  "Room for your bigger ideas",
                  "Plan a document, edit its outline and develop each section at your own pace in Document Studio.",
                ],
                [
                  "03",
                  "Ready to review and share",
                  "Export answers and documents as PDFs. Always review the content, calculations and references before sharing.",
                ],
              ].map(([n, t, d]) => (
                <article key={n}>
                  <span className="principle-number">{n}</span>
                  <h3>{t}</h3>
                  <p>{d}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="welcome-strip page-width">
          <div>
            <p className="eyebrow">Your next chapter</p>
            <h2>
              A little curiosity.
              <br />A lot of possibility.
            </h2>
          </div>
          <Link className="button" to="/register">
            Find your space <Icon name="arrow" />
          </Link>
        </section>
      </main>
      <footer className="public-footer page-width">
        <span>EduMind AI</span>
        <span>Thoughtful learning. From the ground up.</span>
      </footer>
    </>
  );
}
