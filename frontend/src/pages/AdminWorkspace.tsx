import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/Icon";

export function AdminWorkspace() {
  const { user } = useAuth();

  if (user?.role !== "admin") {
    return (
      <main id="main-content" tabIndex={-1} className="workspace-main">
        <p className="eyebrow">Restricted access</p>
        <h1>Administrator access required</h1>
        <p>
          To open this workspace, sign out and sign in with an administrator
          account.
        </p>
        <Link className="button" to="/app">
          Back to your workspace
        </Link>
      </main>
    );
  }

  return (
    <main id="main-content" tabIndex={-1} className="workspace-main dashboard">
      <div className="workspace-page-title">
        <div>
          <p className="eyebrow">EduMind administration</p>
          <h1>Admin workspace</h1>
          <p>Review learning resources and monitor the Knowledge API.</p>
        </div>
        <span className="account-status">Administrator</span>
      </div>
      <section className="tool-grid" aria-label="Administrator tools">
        <Link to="/app/knowledge" className="tool-card tool-book">
          <span className="tool-icon">
            <Icon name="book" />
          </span>
          <h2>Knowledge library</h2>
          <p>Review contributions and track document processing.</p>
          <span className="tool-action">
            Open library <Icon name="arrow" />
          </span>
        </Link>
        <Link to="/app/learning" className="tool-card tool-book">
          <span className="tool-icon">
            <Icon name="book" />
          </span>
          <h2>Knowledge API</h2>
          <p>Review learning examples and check Gemini replacement readiness.</p>
          <span className="tool-action">
            Open Knowledge API <Icon name="arrow" />
          </span>
        </Link>
      </section>
    </main>
  );
}
