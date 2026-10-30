import { useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { errorMessage } from "../api/client";
import { PublicHeader } from "../components/PublicHeader";
import { PasswordField } from "../components/PasswordField";

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const registering = mode === "register";
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const pending = useRef(false);
  const routeState = location.state as {
    email?: string;
    notice?: string;
    returnTo?: string;
  } | null;
  const [email, setEmail] = useState(routeState?.email || "");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const returnTo = routeState?.returnTo || "";
  const destination =
    ["/app/account", "/app/chat"].includes(returnTo) ||
    /^\/app\/chat\/[0-9a-f-]{36}$/i.test(returnTo)
      ? returnTo
      : "/app";
  if (auth.status === "authenticated")
    return <Navigate to={destination} replace />;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending.current) return;
    const errors: Record<string, string> = {};
    if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
      errors.email = "Enter a valid email address.";
    if (!password) errors.password = "Enter your password.";
    if (registering && Array.from(password).length < 15)
      errors.password = "Use at least 15 characters.";
    if (registering && !name.trim()) errors.name = "Enter your full name.";
    if (registering && password !== confirmation)
      errors.confirmation = "Your passwords do not match.";
    setFields(errors);
    setError("");
    if (Object.keys(errors).length) return;
    pending.current = true;
    setBusy(true);
    try {
      if (registering) {
        await auth.client.register({
          email: email.trim(),
          full_name: name.trim(),
          password,
        });
        setPassword("");
        setConfirmation("");
        navigate("/login", {
          replace: true,
          state: {
            email: email.trim(),
            notice: "Account created. Sign in to enter your workspace.",
          },
        });
      } else {
        await auth.client.login({ email: email.trim(), password });
        navigate(destination, { replace: true });
      }
    } catch (cause) {
      setError(errorMessage(cause, mode));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <PublicHeader />
      <main id="main-content" tabIndex={-1} className="auth-layout page-width">
        <aside className="auth-aside">
          <p className="eyebrow">Your space to grow</p>
          <h1>
            {registering ? (
              <>
                A curious mind.
                <br />A fresh <em>start.</em>
              </>
            ) : (
              <>
                Welcome back
                <br />
                to your <em>space.</em>
              </>
            )}
          </h1>
          <p>
            {registering
              ? "Create an account and make room for your next moment of understanding."
              : "Pick up where curiosity left off. Your personal workspace is right here."}
          </p>
          <div className="auth-quote">
            <span aria-hidden="true">✦</span>
            <p>
              Teach students,
              <br />
              <strong>not just answer questions.</strong>
            </p>
          </div>
        </aside>
        <section className="auth-card" aria-labelledby="form-title">
          <p className="eyebrow">
            {registering ? "A new beginning" : "Good to see you"}
          </p>
          <h2 id="form-title">
            {registering ? "Create your account" : "Sign in"}
          </h2>
          <p className="form-intro">
            {registering
              ? "Start with a few details about you."
              : "Enter your details to continue."}
          </p>
          {routeState?.notice && !registering && (
            <p className="notice" role="status">
              {routeState.notice}
            </p>
          )}
          {error && (
            <p className="error-banner" role="alert">
              {error}
            </p>
          )}
          <form onSubmit={submit} noValidate>
            {Object.keys(fields).length > 0 && (
              <p role="alert" className="field-summary">
                Check the highlighted fields.
              </p>
            )}
            <fieldset disabled={busy}>
              {registering && (
                <div className="field">
                  <label htmlFor="full-name">Full name</label>
                  <input
                    id="full-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="name"
                    maxLength={100}
                    required
                    aria-invalid={!!fields.name}
                    aria-describedby={fields.name ? "name-error" : undefined}
                  />
                  {fields.name && (
                    <p id="name-error" className="field-error">
                      {fields.name}
                    </p>
                  )}
                </div>
              )}
              <div className="field">
                <label htmlFor="email">Email address</label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  inputMode="email"
                  maxLength={254}
                  required
                  aria-invalid={!!fields.email}
                  aria-describedby={fields.email ? "email-error" : undefined}
                />
                {fields.email && (
                  <p id="email-error" className="field-error">
                    {fields.email}
                  </p>
                )}
              </div>
              <PasswordField
                label="Password"
                value={password}
                onChange={setPassword}
                error={fields.password}
                autoComplete={registering ? "new-password" : "current-password"}
                hint={
                  registering
                    ? "15–128 characters. A memorable passphrase works well."
                    : undefined
                }
              />
              {registering && (
                <PasswordField
                  label="Confirm password"
                  value={confirmation}
                  onChange={setConfirmation}
                  error={fields.confirmation}
                />
              )}
              <button
                className="button button-full"
                type="submit"
                disabled={busy}
              >
                {busy
                  ? registering
                    ? "Creating your account…"
                    : "Signing in…"
                  : registering
                    ? "Create account"
                    : "Sign in"}
                <span aria-hidden="true">↗</span>
              </button>
            </fieldset>
          </form>
          <p className="form-switch">
            {registering ? "Already have an account? " : "New to EduMind? "}
            <Link to={registering ? "/login" : "/register"}>
              {registering ? "Sign in" : "Create an account"}
            </Link>
          </p>
        </section>
      </main>
    </>
  );
}
