import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, it, expect } from "vitest";
import { HandwritingReview } from "./HandwritingReview";
const request = vi.fn();
vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ client: { request } }) }));

it("requires correction of unclear words and sends only reviewed text and version", async () => {
  request.mockReset();
  request.mockResolvedValueOnce({ version: 2, pages: [{ page: 1, text: "Force is [unclear]." }], original_pdf_base64: "JVBERi0=" });
  request.mockResolvedValueOnce({ status: "searchable" });
  const onChange = vi.fn().mockResolvedValue(undefined);
  render(<HandwritingReview id="doc" pending processing={false} onChange={onChange} />);
  fireEvent.click(screen.getByRole("button", { name: "Review transcription" }));
  const field = await screen.findByLabelText("Page 1");
  expect(screen.getByRole("button", { name: "Approve checked transcription" })).toBeDisabled();
  expect(screen.getByRole("link", { name: /Download original/ })).toHaveAttribute("download");
  fireEvent.change(field, { target: { value: "Force is six newtons." } });
  fireEvent.click(screen.getByRole("button", { name: "Approve checked transcription" }));
  await waitFor(() => expect(onChange).toHaveBeenCalled());
  expect(JSON.parse(request.mock.calls[1][1].body)).toEqual({ version: 2, pages: [{ page: 1, text: "Force is six newtons." }] });
});

it("discloses Gemini processing before queuing and disables a running job", () => {
  render(<HandwritingReview id="doc" pending={false} processing onChange={vi.fn()} />);
  expect(screen.getByText(/Page images are sent/)).toBeInTheDocument();
  expect(screen.getByText("Retry with vision")).toBeDisabled();
});
