import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dropzone } from "./dropzone";
import { LongTaskStatus } from "./long-task-status";

describe("Dropzone", () => {
  it("is a labelled native file input and reports the chosen file", async () => {
    const onFile = vi.fn();
    const { container } = render(
      <Dropzone
        label="Upload your resume"
        hint="PDF or DOCX"
        onFile={onFile}
      />,
    );
    const input = screen.getByLabelText(/upload your resume/i);
    expect(input).toHaveAttribute("type", "file");
    const file = new File(["x"], "cv.pdf", { type: "application/pdf" });
    await userEvent.upload(input, file);
    expect(onFile).toHaveBeenCalledWith(file);
    expect(
      await axe(container, { rules: { "color-contrast": { enabled: false } } }),
    ).toHaveNoViolations();
  });
  it("accepts a dropped file and announces errors", () => {
    const onFile = vi.fn();
    render(<Dropzone label="Resume" error="Too big" onFile={onFile} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Too big");
    const file = new File(["x"], "cv.docx");
    fireEvent.drop(screen.getByText("Resume").closest("label")!, {
      dataTransfer: { files: [file] },
    });
    expect(onFile).toHaveBeenCalledWith(file);
  });
  it("ignores drops while disabled", () => {
    const onFile = vi.fn();
    render(<Dropzone label="Resume" disabled onFile={onFile} />);
    fireEvent.drop(screen.getByText("Resume").closest("label")!, {
      dataTransfer: { files: [new File(["x"], "cv.pdf")] },
    });
    expect(onFile).not.toHaveBeenCalled();
  });
});

describe("LongTaskStatus", () => {
  afterEach(() => vi.useRealTimers());
  it("shows an honest label, a visual-only timer and a delayed live message", () => {
    vi.useFakeTimers();
    render(
      <LongTaskStatus
        label="Reading your resume…"
        slowAfterSeconds={5}
        slowMessage="Still working."
      />,
    );
    const live = screen.getByRole("status");
    expect(live).toHaveTextContent("Reading your resume…");
    expect(live).not.toHaveTextContent("Still working.");
    expect(screen.getByText(/0:00 elapsed/)).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    act(() => vi.advanceTimersByTime(6000));
    expect(screen.getByText(/0:06 elapsed/)).toBeInTheDocument();
    expect(live).toHaveTextContent("Still working.");
  });
});
