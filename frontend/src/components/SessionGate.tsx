import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
export function SessionGate() {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "loading")
    return (
      <main id="main-content" tabIndex={-1} className="state-page">
        <p role="status">Checking your session…</p>
      </main>
    );
  if (auth.status === "unavailable")
    return (
      <main id="main-content" tabIndex={-1} className="state-page">
        <span className="eyebrow">Connection interrupted</span>
        <h1>Let’s reconnect.</h1>
        <p>
          We could not check your session. Your workspace will be available once
          the connection is restored.
        </p>
        <button
          className="button"
          onClick={() => {
            void auth.client.recover().catch(() => {});
          }}
        >
          Try again
        </button>
      </main>
    );
  if (auth.status === "anonymous")
    return (
      <Navigate to="/login" replace state={{ returnTo: location.pathname }} />
    );
  return <Outlet />;
}
