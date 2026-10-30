import { useRef, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { errorMessage } from "../api/client";
import { Brand } from "./Brand";
export function WorkspaceLayout() {
  const { client, user } = useAuth();
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!user) return null;
  async function logout() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await client.logout();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="workspace-shell">
      <header className="workspace-header">
        <Brand />
        <button
          ref={toggle}
          className="menu-toggle"
          aria-controls="workspace-nav"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          Menu <span aria-hidden="true">{open ? "−" : "+"}</span>
        </button>
        <span className="workspace-tag">Your learning space</span>
      </header>
      <aside
        className={open ? "workspace-sidebar is-open" : "workspace-sidebar"}
      >
        <nav
          id="workspace-nav"
          aria-label="Workspace navigation"
          onKeyDown={(e) => {
            if (e.key === "Escape" && open) {
              setOpen(false);
              toggle.current?.focus();
            }
          }}
        >
          <p className="nav-caption">YOUR WORKSPACE</p>
          <NavLink to="/app" end onClick={() => setOpen(false)}>
            <span aria-hidden="true">⌂</span> Overview
          </NavLink>
          <NavLink to="/app/chat" onClick={() => setOpen(false)}>
            <span aria-hidden="true">✦</span> Study chat
          </NavLink>
          <NavLink to="/app/knowledge" onClick={() => setOpen(false)}>
            <span aria-hidden="true">▤</span> Knowledge library
          </NavLink>
          <NavLink to="/app/account" onClick={() => setOpen(false)}>
            <span aria-hidden="true">◎</span> My account
          </NavLink>
        </nav>
        <div className="sidebar-bottom">
          <div className="user-chip">
            <span className="avatar" aria-hidden="true">
              {Array.from(user.full_name)[0]?.toUpperCase()}
            </span>
            <div>
              <strong>{user.full_name}</strong>
              <span>
                {user.role === "admin"
                  ? "Administrator"
                  : user.role === "contributor"
                    ? "Contributor"
                    : "Student"}
              </span>
            </div>
          </div>
          <button
            type="button"
            className="logout-button"
            onClick={logout}
            disabled={busy}
            aria-label="Sign out on all devices"
          >
            {busy ? "Signing out…" : "Sign out"}
            <span aria-hidden="true">↗</span>
          </button>
          <p className="logout-hint">Closes your sessions on all devices.</p>
          {error && (
            <p className="error-banner" role="alert">
              {error}
            </p>
          )}
          <Link className="back-home" to="/">
            ← EduMind home
          </Link>
        </div>
      </aside>
      <div className="workspace-content">
        <Outlet />
      </div>
    </div>
  );
}
