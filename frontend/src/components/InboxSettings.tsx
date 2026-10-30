import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { errorMessage } from "../api/client";

type Credential = {
  id: string;
  name: string;
  expires_at: string;
  revoked: boolean;
  scope: string;
};
export function InboxSettings() {
  const { client } = useAuth();
  const [items, setItems] = useState<Credential[]>([]);
  const [token, setToken] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      setItems(
        (await client.request("/admin/inbox-credentials")) as Credential[],
      );
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }, [client]);
  useEffect(() => {
    void load();
  }, [load]);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    setToken("");
    try {
      const result = (await client.request("/admin/inbox-credentials", {
        method: "POST",
        body: JSON.stringify({
          name: data.get("name"),
          valid_days: Number(data.get("days")),
        }),
      })) as { token: string };
      setToken(result.token);
      setShow(false);
      form.reset();
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: string) {
    setBusy(true);
    setError("");
    try {
      await client.request(`/admin/inbox-credentials/${id}`, {
        method: "DELETE",
      });
      setToken("");
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="knowledge-card">
      <h2>Personal knowledge inbox</h2>
      <p>
        Connect the folder service on your computer with a submission-only
        credential. Every document still awaits administrator approval.
      </p>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      <form onSubmit={(event) => void create(event)}>
        <label>
          Computer or inbox name
          <input
            name="name"
            required
            maxLength={100}
            placeholder="My Windows computer"
          />
        </label>
        <label>
          Valid for (days)
          <input
            type="number"
            name="days"
            min={1}
            max={90}
            defaultValue={30}
            required
          />
        </label>
        <button disabled={busy}>Create inbox credential</button>
      </form>
      {token && (
        <div className="knowledge-notice">
          <p>
            This credential is shown only once. Store it privately for your
            folder service.
          </p>
          <label>
            New inbox credential
            <input
              type={show ? "text" : "password"}
              value={token}
              readOnly
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <button onClick={() => setShow(!show)}>
            {show ? "Hide credential" : "Show credential"}
          </button>
          <button onClick={() => setToken("")}>Dismiss credential</button>
        </div>
      )}
      {items.map((item) => (
        <article key={item.id}>
          <h3>{item.name}</h3>
          <p>
            {item.scope} · expires{" "}
            {new Date(item.expires_at).toLocaleDateString()} ·{" "}
            {item.revoked ? "Revoked" : "Active"}
          </p>
          <button
            disabled={busy || item.revoked}
            onClick={() => void revoke(item.id)}
          >
            Revoke credential
          </button>
        </article>
      ))}
    </section>
  );
}
