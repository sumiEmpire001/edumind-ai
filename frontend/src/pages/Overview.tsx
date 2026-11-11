import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { canAccessKnowledgeApi, roleLabels } from "../auth/roles";
import { Icon, type IconName } from "../components/Icon";
const tools: {
  icon: IconName;
  title: string;
  description: string;
  to: string;
  label: string;
}[] = [
  {
    icon: "chat",
    title: "Study chat",
    description:
      "Work through a question, explore an idea, or get a step-by-step explanation.",
    to: "/app/chat",
    label: "Open study chat",
  },
  {
    icon: "document",
    title: "Document Studio",
    description:
      "Turn a brief into an outline. Draft, refine and export your work as a PDF.",
    to: "/app/studio",
    label: "Create a document",
  },
];
const contributionTools: typeof tools = [
  {
    icon: "book",
    title: "Knowledge library",
    description: "Submit learning materials and track their review and processing.",
    to: "/app/knowledge",
    label: "Open the library",
  },
  {
    icon: "search",
    title: "Knowledge API",
    description: "Search approved sources and suggest academic questions for review.",
    to: "/app/learning",
    label: "Open Knowledge API",
  },
];
export function Overview() {
  const { user } = useAuth();
  if (!user) return null;
  const knowledgeAccess = canAccessKnowledgeApi(user.role);
  const sections = [
    { title: "Study tools", items: tools },
    ...(knowledgeAccess ? [{ title: "Contribution tools", items: contributionTools }] : []),
  ];
  return (
    <main id="main-content" tabIndex={-1} className="workspace-main dashboard">
      <header className="workspace-page-title">
        <div>
          <h1>Hello, {user.full_name.trim().split(/\s+/)[0]}<span className="greeting-dot">.</span></h1>
          <p>Choose what you’d like to work on today.</p>
        </div>
        <span className="account-status">{roleLabels[user.role]}</span>
      </header>
      {sections.map(({ title, items }) => (
        <section className="dashboard-tools" key={title} aria-label={title}>
          <div className="dashboard-section-heading"><h2>{title}</h2></div>
          <div className="tool-grid">
            {items.map((tool) => (
              <Link to={tool.to} className={`tool-card tool-${tool.icon}`} key={tool.to}>
                <span className="tool-icon"><Icon name={tool.icon} /></span>
                <h3>{tool.title}</h3>
                <p>{tool.description}</p>
                <span className="tool-action">{tool.label}<Icon name="arrow" /></span>
              </Link>
            ))}
          </div>
        </section>
      ))}
      {user.role === "student" && (
        <section className="getting-started" aria-labelledby="contribute-title">
          <div>
            <h2 id="contribute-title">Share learning materials</h2>
            <p>Apply for contributor access to submit materials for review.</p>
          </div>
          <Link className="text-link" to="/app/knowledge">
            Contributor application <Icon name="arrow" />
          </Link>
        </section>
      )}
    </main>
  );
}
