import { lazy, Suspense, useEffect } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { SessionClient } from "./auth/session";
import { SessionGate } from "./components/SessionGate";
import { WorkspaceLayout } from "./components/WorkspaceLayout";
import { Landing } from "./pages/Landing";
import { AuthPage } from "./pages/AuthPage";
import { Overview } from "./pages/Overview";
import { Account } from "./pages/Account";
import { RouteBoundary } from "./components/RouteBoundary";
const Chat = lazy(() => import("./pages/Chat"));
function ChatRoute() {
  const location = useLocation();
  return (
    <RouteBoundary key={location.pathname}>
      <Suspense
        fallback={
          <main id="main-content" className="workspace-main" role="status">
            Opening study chat…
          </main>
        }
      >
        <Chat />
      </Suspense>
    </RouteBoundary>
  );
}

function RouteEffects() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    const titles: Record<string, string> = {
      "/": "A clearer way to learn",
      "/login": "Sign in",
      "/register": "Create an account",
      "/app": "Your workspace",
      "/app/account": "My account",
    };
    document.title = `${titles[pathname] || (pathname.startsWith("/app/chat") ? "Study chat" : "Page not found")} · EduMind AI`;
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView?.();
    else {
      window.scrollTo?.(0, 0);
      document.getElementById("main-content")?.focus({ preventScroll: true });
    }
  }, [pathname, hash]);
  return null;
}
export default function App({ client }: { client?: SessionClient }) {
  return (
    <AuthProvider client={client}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <RouteEffects />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route
          path="/register"
          element={<AuthPage key="register" mode="register" />}
        />
        <Route path="/login" element={<AuthPage key="login" mode="login" />} />
        <Route element={<SessionGate />}>
          <Route path="/app" element={<WorkspaceLayout />}>
            <Route index element={<Overview />} />
            <Route path="account" element={<Account />} />
            <Route path="chat" element={<ChatRoute />} />
            <Route path="chat/:conversationId" element={<ChatRoute />} />
          </Route>
        </Route>
        <Route
          path="*"
          element={
            <main id="main-content" tabIndex={-1} className="state-page">
              <p className="eyebrow">A different path</p>
              <h1>Page not found.</h1>
              <p>Let’s get you back to a familiar place.</p>
              <Link className="button" to="/">
                Back to EduMind
              </Link>
            </main>
          }
        />
      </Routes>
    </AuthProvider>
  );
}
