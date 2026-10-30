import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
export function Overview() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <main id="main-content" tabIndex={-1} className="workspace-main">
      <div className="workspace-page-title">
        <div>
          <p className="eyebrow">A little space for possibility</p>
          <h1>
            Hello, {user.full_name.split(" ")[0]}
            <span className="greeting-dot">.</span>
          </h1>
          <p>Welcome to your EduMind workspace.</p>
        </div>
        <span className="account-status">
          <span aria-hidden="true" /> Active account
        </span>
      </div>
      <section className="welcome-card">
        <div>
          <span className="eyebrow">One idea at a time</span>
          <h2>
            Keep your curiosity.
            <br />
            <em>We’ll build the clarity.</em>
          </h2>
          <p>
            Your conversation workspace is ready. Keep your questions together
            and check the availability of answers in study chat.
          </p>
          <Link className="button" to="/app/chat">
            Start a conversation <span aria-hidden="true">↗</span>
          </Link>
        </div>
        <div className="welcome-art" aria-hidden="true">
          <span>?</span>
          <span>↗</span>
          <span>✦</span>
        </div>
      </section>
      <div className="workspace-card-grid">
        <section className="info-card">
          <p className="eyebrow">Your account</p>
          <h2>Make yourself at home.</h2>
          <dl className="compact-details">
            <div>
              <dt>Signed in as</dt>
              <dd>{user.email}</dd>
            </div>
            <div>
              <dt>Account type</dt>
              <dd>
                {user.role === "admin"
                  ? "Administrator"
                  : user.role === "contributor"
                    ? "Contributor"
                    : "Student"}
              </dd>
            </div>
          </dl>
          <Link className="text-link" to="/app/account">
            Account details <span aria-hidden="true">→</span>
          </Link>
        </section>
        <section className="info-card learning-note">
          <span className="small-symbol" aria-hidden="true">
            ✦
          </span>
          <p className="eyebrow">Worth remembering</p>
          <h2>
            Understanding begins
            <br />
            with a question.
          </h2>
          <p>There’s no small question when you’re learning something new.</p>
        </section>
      </div>
    </main>
  );
}
