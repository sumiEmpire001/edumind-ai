import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { errorMessage } from "../api/client";
import { PasswordField } from "../components/PasswordField";
export function Account() {
  const { user, client } = useAuth();
  const navigate = useNavigate();
  const pending = useRef(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  if (!user) return null;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending.current) return;
    const errors: Record<string, string> = {};
    if (!current) errors.current = "Enter your current password.";
    if (Array.from(next).length < 15)
      errors.next = "Use at least 15 characters.";
    if (next === current) errors.next = "Choose a different password.";
    if (next !== confirm) errors.confirm = "Your passwords do not match.";
    setFields(errors);
    setError("");
    if (Object.keys(errors).length) return;
    pending.current = true;
    setBusy(true);
    try {
      await client.changePassword(current, next);
      navigate("/login", {
        replace: true,
        state: {
          notice: "Password changed. Sign in again with your new password.",
        },
      });
    } catch (cause) {
      setError(errorMessage(cause, "password"));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <main id="main-content" tabIndex={-1} className="workspace-main">
      <div className="workspace-page-title">
        <div>
          <p className="eyebrow">Your details, in one place</p>
          <h1>My account</h1>
          <p>A little care for your personal space.</p>
        </div>
      </div>
      <div className="account-layout">
        <section className="info-card account-details">
          <h2>Account details</h2>
          <dl>
            <div>
              <dt>Full name</dt>
              <dd>{user.full_name}</dd>
            </div>
            <div>
              <dt>Email address</dt>
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
            <div>
              <dt>Status</dt>
              <dd>Active</dd>
            </div>
          </dl>
          <p className="muted-note">
            Contact your platform administrator if your account details need
            correcting.
          </p>
        </section>
        <section
          className="info-card password-card"
          aria-labelledby="password-title"
        >
          <h2 id="password-title">Change password</h2>
          <p>
            Choose a new passphrase that’s just for you. Changing it signs you
            out on every device.
          </p>
          {error && (
            <p className="error-banner" role="alert">
              {error}
            </p>
          )}
          <form noValidate onSubmit={submit}>
            {Object.keys(fields).length > 0 && (
              <p role="alert" className="field-summary">
                Check the highlighted fields.
              </p>
            )}
            <fieldset disabled={busy}>
              <PasswordField
                label="Current password"
                value={current}
                onChange={setCurrent}
                error={fields.current}
                autoComplete="current-password"
              />
              <PasswordField
                label="New password"
                value={next}
                onChange={setNext}
                error={fields.next}
                hint="15–128 characters."
              />
              <PasswordField
                label="Confirm new password"
                value={confirm}
                onChange={setConfirm}
                error={fields.confirm}
              />
              <button type="submit" disabled={busy} className="button">
                {busy ? "Changing password…" : "Change password"}
                <span aria-hidden="true">↗</span>
              </button>
            </fieldset>
          </form>
        </section>
      </div>
    </main>
  );
}
