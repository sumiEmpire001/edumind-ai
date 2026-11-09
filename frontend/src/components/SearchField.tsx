import { useId, useRef } from "react";
import { Icon } from "./Icon";

export function SearchField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="list-search">
      <label htmlFor={id}>{label}</label>
      <div className="list-search-input">
        <Icon name="search" />
        <input
          id={id}
          ref={input}
          type="search"
          value={value}
          maxLength={160}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby={hint ? `${id}-hint` : undefined}
          autoComplete="off"
          spellCheck={false}
        />
      </div>
      {hint && (
        <p id={`${id}-hint`} className="list-search-hint">
          {hint}
        </p>
      )}
      {!!value && (
        <button
          className="clear-search"
          type="button"
          onClick={() => {
            onChange("");
            input.current?.focus();
          }}
        >
          Clear search
        </button>
      )}
    </div>
  );
}
