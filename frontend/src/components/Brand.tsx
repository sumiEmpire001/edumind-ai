import { Link } from "react-router-dom";
export function Brand() {
  return (
    <Link className="brand" to="/" aria-label="EduMind AI home">
      <span className="brand-mark" aria-hidden="true">
        e<span>•</span>
      </span>
      <span>
        EduMind<span className="brand-ai"> AI</span>
      </span>
    </Link>
  );
}
