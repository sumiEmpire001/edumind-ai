import { useState } from "react";
export function CopyButton({ text, label }: { text: string; label: string }) {
  const [status, setStatus] = useState("");
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setStatus("Copied");
    } catch {
      setStatus("Copy unavailable. Select and copy the text manually.");
    }
  }
  return (
    <span className="copy-control">
      <button
        type="button"
        className="copy-button"
        onClick={copy}
        aria-label={label}
      >
        {label}
      </button>
      <span role="status" className="copy-status">
        {status}
      </span>
    </span>
  );
}
