import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
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
  {
    icon: "book",
    title: "Knowledge library",
    description:
      "Contribute learning material and follow its review in one place.",
    to: "/app/knowledge",
    label: "Explore the library",
  },
];
export function Overview() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <main id="main-content" tabIndex={-1} className="workspace-main dashboard">
      <div className="workspace-page-title">
        <div>
          <p className="eyebrow">Your learning workspace</p>
          <h1>
            Hello, {user.full_name.split(" ")[0]}
            <span className="greeting-dot">.</span>
          </h1>
          <p>What would you like to work on today?</p>
        </div>
        <div className="dashboard-heading-actions">
          <span className="account-status">
            {user.role === "admin"
              ? "Administrator"
              : user.role === "contributor"
                ? "Contributor"
                : "Student"}
          </span>
          <Link className="button" to="/app/chat">
            Start a conversation <Icon name="arrow" />
          </Link>
        </div>
      </div>
      <section className="dashboard-banner">
        <div>
          <span className="banner-label">
            <Icon name="spark" /> A little curiosity goes a long way
          </span>
          <h2>
            Your next breakthrough
            <br />
            starts with a question.
          </h2>
          <p>
            A space to think clearly, build understanding and bring your ideas
            together.
          </p>
        </div>
        <div className="banner-motif" aria-hidden="true">
          <span>?</span>
          <span>✦</span>
          <span>↗</span>
        </div>
      </section>
      <div className="dashboard-section-heading">
        <h2>Make room for good work</h2>
        <span>Choose a tool to get started</span>
      </div>
      <section className="tool-grid" aria-label="Learning tools">
        {tools.map((tool) => (
          <Link
            to={tool.to}
            className={`tool-card tool-${tool.icon}`}
            key={tool.to}
          >
            <span className="tool-icon">
              <Icon name={tool.icon} />
            </span>
            <h3>{tool.title}</h3>
            <p>{tool.description}</p>
            <span className="tool-action">
              {tool.label}
              <Icon name="arrow" />
            </span>
          </Link>
        ))}
      </section>
      <section
        className="getting-started"
        aria-labelledby="getting-started-title"
      >
        <div>
          <p className="eyebrow">A useful starting point</p>
          <h2 id="getting-started-title">Better context. Clearer answers.</h2>
          <p>
            Share your topic, what you already know and the part you’re finding
            difficult. Review AI responses and check important facts before
            using them.
          </p>
        </div>
        <Link className="text-link" to="/app/account">
          Manage your account <span aria-hidden="true">→</span>
        </Link>
      </section>
    </main>
  );
}
