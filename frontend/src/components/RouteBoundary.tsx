import { Component, type ReactNode } from "react";
import { Link } from "react-router-dom";
export class RouteBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <main id="main-content" tabIndex={-1} className="state-page">
        <h1>We couldn’t open this page.</h1>
        <p>Check your connection, then reload to try again.</p>
        <button className="button" onClick={() => window.location.reload()}>
          Reload page
        </button>
        <p>
          <Link to="/app">Back to your workspace</Link>
        </p>
      </main>
    ) : (
      this.props.children
    );
  }
}
