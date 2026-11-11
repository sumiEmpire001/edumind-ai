import { useRef, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { canAccessKnowledgeApi, roleLabels } from "../auth/roles";
import { errorMessage } from "../api/client";
import { Brand } from "./Brand";
import { Icon } from "./Icon";
export function WorkspaceLayout() {
  const { client, user } = useAuth();
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!user) return null;
  const knowledgeAccess = canAccessKnowledgeApi(user.role);
  const closeMenu = () => setOpen(false);
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
        <span className="workspace-tag">Think clearly. Learn deeply.</span>
      </header>
      <aside
        className={open ? "workspace-sidebar is-open" : "workspace-sidebar"}
        onKeyDown={(e) => {
          if (e.key === "Escape" && open) {
            setOpen(false);
            toggle.current?.focus();
          }
        }}
      >
        <nav id="workspace-nav" aria-label="Workspace navigation">
          <p className="nav-caption">Study workspace</p>
          <NavLink to="/app" end onClick={closeMenu}>
            <Icon name="home" /> Overview
          </NavLink>
          <NavLink to="/app/chat" onClick={closeMenu}>
            <Icon name="chat" /> Study chat
          </NavLink>
          <NavLink to="/app/studio" onClick={closeMenu}>
            <Icon name="document" /> Document Studio
          </NavLink>
          <p className="nav-caption">Contributions</p>
          <NavLink to="/app/knowledge" onClick={closeMenu}>
            <Icon name="book" /> {knowledgeAccess ? "Knowledge library" : "Become a contributor"}
          </NavLink>
          {knowledgeAccess && (
            <NavLink to="/app/learning" onClick={closeMenu}>
              <Icon name="search" /> Knowledge API
            </NavLink>
          )}
          <p className="nav-caption">Account</p>
          <NavLink to="/app/account" onClick={closeMenu}>
            <Icon name="user" /> My account
          </NavLink>
          {user.role === "admin" && (
            <NavLink to="/app/admin" onClick={closeMenu}>
              <Icon name="user" /> Administration
            </NavLink>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="user-chip">
            <span className="avatar" aria-hidden="true">
              {Array.from(user.full_name)[0]?.toUpperCase()}
            </span>
            <div>
              <strong>{user.full_name}</strong>
              <span>{roleLabels[user.role]}</span>
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
      {open && (
        <button
          type="button"
          className="nav-scrim"
          aria-label="Close workspace menu"
          onClick={() => {
            setOpen(false);
            toggle.current?.focus();
          }}
        />
      )}
      <div className="workspace-content">
        <Outlet />
      </div>
    </div>
  );
}
