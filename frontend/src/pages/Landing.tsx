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
              <span aria-hidden="true" /> A fresh space for curious minds
            </div>
            <h1>
              Learn the why.
              <br />
              <em>Go further.</em>
            </h1>
            <p className="hero-lead">
              Big questions deserve a little clarity. Make room for deeper
              understanding, one idea at a time.
            </p>
            <div className="hero-actions">
              <Link className="button" to="/register">
                Create your account <span aria-hidden="true">↗</span>
              </Link>
              <Link className="text-link" to="/login">
                I already have an account <span aria-hidden="true">→</span>
              </Link>
            </div>
            <p className="early-note">
              Accounts are open. AI learning tools are coming soon.
            </p>
          </div>
          <div className="study-visual" aria-label="Our learning philosophy">
            <div className="study-tab">
              A moment of understanding <span aria-hidden="true">✦</span>
            </div>
            <div className="study-paper">
              <span className="paper-label">THE EDUMIND WAY</span>
              <p className="paper-title">
                A better answer starts
                <br />
                with a better <em>why.</em>
              </p>
              <div className="learning-step">
                <span>01</span>
                <div>
                  <strong>Start with what you know</strong>
                  <p>Give your curiosity a starting point.</p>
                </div>
              </div>
              <div className="learning-step">
                <span>02</span>
                <div>
                  <strong>Work through the steps</strong>
                  <p>Make the complex feel approachable.</p>
                </div>
              </div>
              <div className="learning-step">
                <span>03</span>
                <div>
                  <strong>Make it make sense</strong>
                  <p>Understanding stays with you.</p>
                </div>
              </div>
              <div className="paper-bottom">
                <span>Curiosity → Clarity</span>
                <span aria-hidden="true">↗</span>
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
                We’re building an academic companion that teaches students, not
                just answers questions.
              </p>
            </div>
            <div className="principles">
              {[
                [
                  "01",
                  "Clarity over shortcuts",
                  "An approach built around explanations, meaningful steps, and the reasoning behind the result.",
                ],
                [
                  "02",
                  "Curiosity across subjects",
                  "A place designed for the questions that connect mathematics, science, programming, and more.",
                ],
                [
                  "03",
                  "Knowledge with care",
                  "Academic references will be reviewed before they become part of the learning experience.",
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
            Find your space <span aria-hidden="true">↗</span>
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
