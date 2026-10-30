import { useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Brand } from "./Brand";

export function PublicHeader() {
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const { status } = useAuth();
  const location = useLocation();
  return (
    <header className="public-header">
      <div className="public-header-inner">
        <Brand />
        <button
          type="button"
          ref={toggle}
          className="menu-toggle"
          aria-expanded={open}
          aria-controls="public-nav"
          onClick={() => setOpen(!open)}
        >
          Menu <span aria-hidden="true">{open ? "−" : "+"}</span>
        </button>
        <nav
          id="public-nav"
          aria-label="Main navigation"
          className={open ? "public-nav is-open" : "public-nav"}
          onKeyDown={(e) => {
            if (e.key === "Escape" && open) {
              setOpen(false);
              toggle.current?.focus();
            }
          }}
        >
          <Link to="/#approach" onClick={() => setOpen(false)}>
            Our approach
          </Link>
          {status === "authenticated" ? (
            <Link
              className="button button-small"
              to="/app"
              onClick={() => setOpen(false)}
            >
              My workspace <span aria-hidden="true">↗</span>
            </Link>
          ) : (
            <>
              <Link
                className={location.pathname === "/login" ? "active" : ""}
                to="/login"
                onClick={() => setOpen(false)}
              >
                Sign in
              </Link>
              <Link
                className="button button-small"
                to="/register"
                onClick={() => setOpen(false)}
              >
                Get started <span aria-hidden="true">↗</span>
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
