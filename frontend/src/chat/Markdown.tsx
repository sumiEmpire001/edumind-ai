import { Children, Component, isValidElement, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { CopyButton } from "./CopyButton";

function textOf(node: ReactNode): string {
  return Children.toArray(node)
    .map((child) =>
      isValidElement<{ children?: ReactNode }>(child)
        ? textOf(child.props.children)
        : typeof child === "string" || typeof child === "number"
          ? String(child)
          : "",
    )
    .join("");
}
function safeUrl(value: string) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}
class FormattingBoundary extends Component<
  { children: ReactNode; text: string },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <>
        <p>Formatting unavailable. Plain text is shown.</p>
        <pre className="plain-answer">{this.props.text}</pre>
      </>
    ) : (
      this.props.children
    );
  }
}
export function Markdown({ text }: { text: string }) {
  return (
    <FormattingBoundary text={text}>
      <div className="answer-markdown">
        <ReactMarkdown
          skipHtml
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[
            [
              rehypeKatex,
              {
                trust: false,
                strict: "ignore",
                throwOnError: false,
                maxExpand: 500,
                maxSize: 10,
              },
            ],
          ]}
          urlTransform={safeUrl}
          disallowedElements={[
            "img",
            "iframe",
            "script",
            "style",
            "form",
            "input",
            "button",
            "audio",
            "video",
          ]}
          components={{
            a: ({ href, children }) =>
              href ? (
                <a href={href} target="_blank" rel="noopener noreferrer">
                  {children}
                </a>
              ) : (
                <span>{children}</span>
              ),
            pre: ({ children }) => (
              <div className="code-frame">
                <CopyButton text={textOf(children)} label="Copy code" />
                <pre>{children}</pre>
              </div>
            ),
          }}
        >
          {text}
        </ReactMarkdown>
      </div>
    </FormattingBoundary>
  );
}
