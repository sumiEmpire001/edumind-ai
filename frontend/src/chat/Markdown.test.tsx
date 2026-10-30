import { render, screen, fireEvent } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Markdown } from "./Markdown";
import { CopyButton } from "./CopyButton";
afterEach(() => vi.unstubAllGlobals());
it("renders steps, tables, equations and code without raw LaTeX", () => {
  const { container } = render(
    <Markdown
      text={
        "### Solution\n1. Known values\n2. Calculate $F = ma$\n\n| Quantity | Value |\n| --- | --- |\n| Force | 6 N |\n\n```python\nforce = 2 * 3\n```"
      }
    />,
  );
  expect(screen.getByRole("heading", { name: "Solution" })).toBeInTheDocument();
  expect(screen.getByRole("table")).toHaveTextContent("Force");
  expect(container.querySelector(".katex")).not.toBeNull();
  expect(screen.getByRole("button", { name: "Copy code" })).toBeInTheDocument();
});
it("does not execute HTML, javascript URLs or remote tracking images", () => {
  const { container } = render(
    <Markdown
      text={
        '<script>alert(1)</script>\n\n<img src="https://tracker.invalid/pixel">\n\n[Unsafe](javascript:alert%281%29)\n\n![Tracking](https://tracker.invalid/image)'
      }
    />,
  );
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("img")).toBeNull();
  expect(container.querySelector("a")).toBeNull();
});
it("does not trust unsafe KaTeX commands", () => {
  const { container } = render(
    <Markdown text={"$\\href{javascript:alert(1)}{unsafe}$"} />,
  );
  expect(container.querySelector("a")).toBeNull();
});
it("opens safe links with isolation and without a referrer", () => {
  render(<Markdown text={"[Documentation](https://example.com/reference)"} />);
  expect(screen.getByRole("link")).toHaveAttribute(
    "rel",
    "noopener noreferrer",
  );
  expect(screen.getByRole("link")).toHaveAttribute("target", "_blank");
});
it("copies the actual code rather than its copy-control label", async () => {
  const write = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText: write } });
  render(<Markdown text={"```python\nforce = 2 * 3\n```"} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy code" }));
  expect(await screen.findByText("Copied")).toBeInTheDocument();
  expect(write).toHaveBeenCalledWith("force = 2 * 3\n");
});
it("reports clipboard denial rather than claiming success", async () => {
  vi.stubGlobal("navigator", {
    clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
  });
  render(<CopyButton text="Question" label="Copy question" />);
  fireEvent.click(screen.getByRole("button"));
  expect(
    await screen.findByText(
      "Copy unavailable. Select and copy the text manually.",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText("Copied")).not.toBeInTheDocument();
});
