import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Icon, type IconName } from "../components/Icon";
import "./AdminWorkspace.css";

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

  return <AdminOverview />;
}

type Platform = { users: number; submissions: number; active_documents: number };
type Learning = { training_examples: number; searchable_chunks: number; examples: { pending: number } };

const tools: { path: string; icon: IconName; title: string; description: string; action: string }[] = [
  {
    path: "/app/knowledge",
    icon: "book",
    title: "Knowledge library",
    description: "Review submissions, manage contributors and track document processing.",
    action: "Open library",
  },
  {
    path: "/app/learning",
    icon: "document",
    title: "Knowledge API",
    description: "Review suggested questions and track the searchable collection.",
    action: "Open Knowledge API",
  },
  {
    path: "/app/research?topic=lautech",
    icon: "search",
    title: "LAUTECH research",
    description: "Find public university sources and share useful questions for review.",
    action: "Research LAUTECH",
  },
];

function AdminOverview() {
  const { client, user } = useAuth();
  const [refresh, setRefresh] = useState(0);
  const [snapshot, setSnapshot] = useState<{
    platform: Platform | null;
    learning: Learning | null;
  } | null>(null);

  useEffect(() => {
    let active = true;
    void Promise.allSettled([
      client.request("/admin/statistics") as Promise<Platform>,
      client.request("/admin/learning/overview") as Promise<Learning>,
    ]).then(([platform, learning]) => {
      if (!active) return;
      setSnapshot({
        platform: platform.status === "fulfilled" ? platform.value : null,
        learning: learning.status === "fulfilled" ? learning.value : null,
      });
    });
    return () => { active = false; };
  }, [client, refresh]);

  const metrics = [
    { name: "Registered users", value: snapshot?.platform?.users, icon: "user" },
    { name: "Resource submissions", value: snapshot?.platform?.submissions, icon: "document" },
    { name: "Active documents", value: snapshot?.platform?.active_documents, icon: "book" },
    { name: "Questions awaiting review", value: snapshot?.learning?.examples?.pending, icon: "chat" },
    { name: "Approved training examples", value: snapshot?.learning?.training_examples, icon: "spark" },
    { name: "Searchable passages", value: snapshot?.learning?.searchable_chunks, icon: "search" },
  ] as const;
  const incomplete = snapshot && (!snapshot.platform || !snapshot.learning);

  return (
    <main id="main-content" tabIndex={-1} className="workspace-main admin-page">
      <header className="admin-hero">
        <div>
          <p className="eyebrow">EduMind administration</p>
          <h1>Admin workspace</h1>
          <p>Welcome, {user?.full_name}. Review resources and monitor what’s available to learners.</p>
        </div>
        <span className="admin-role"><Icon name="user" /> Administrator</span>
      </header>
      <section aria-labelledby="admin-platform">
        <div className="admin-heading">
          <div><h2 id="admin-platform">Platform overview</h2><p>Current counts from the EduMind API</p></div>
          <button type="button" className="button button-secondary" disabled={!snapshot} onClick={() => {
            setSnapshot(null);
            setRefresh((value) => value + 1);
          }}>Refresh metrics</button>
        </div>
        {!snapshot && <p role="status" className="admin-note">Loading platform metrics…</p>}
        {incomplete && <p role="status" className="admin-note">Some metrics are unavailable. Refresh to try again.</p>}
        <dl className="admin-metrics">
          {metrics.map(({ name, value, icon }) => (
            <div key={name} className="admin-metric">
              <span className="admin-icon"><Icon name={icon} /></span>
              <dt>{name}</dt>
              <dd>{typeof value === "number" ? value.toLocaleString() : snapshot ? "Unavailable" : "…"}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section aria-labelledby="admin-tools">
        <div className="admin-heading"><div><h2 id="admin-tools">Manage EduMind</h2><p>Open a workspace to review content or research new sources.</p></div></div>
        <div className="admin-tools">
          {tools.map(({ path, icon, title, description, action }) => (
            <Link key={path} to={path} className="admin-tool">
              <span className="admin-icon"><Icon name={icon} /></span>
              <h3>{title}</h3>
              <p>{description}</p>
              <span className="admin-tool-action">{action} <Icon name="arrow" /></span>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
