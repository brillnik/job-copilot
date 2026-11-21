import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...p
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...p}>
      {children}
    </a>
  ),
}));
const api = vi.hoisted(() => ({ addJob: vi.fn(), uploadImage: vi.fn() }));
vi.mock("./api", () => api);

import { AddJobModal } from "./add-job-modal";
import { apiError, renderWithProviders } from "./test-utils";

function setup() {
  const onClose = vi.fn();
  const view = renderWithProviders(<AddJobModal open onClose={onClose} />);
  return { onClose, ...view };
}

beforeEach(() => vi.clearAllMocks());

describe("AddJobModal", () => {
  it("adds by link and closes", async () => {
    api.addJob.mockResolvedValue({
      job_id: "j1",
      status: "processing",
      duplicate: false,
    });
    const { onClose } = setup();
    await userEvent.type(
      screen.getByLabelText("Job link"),
      " https://x.io/jobs/1 ",
    );
    await userEvent.click(screen.getByRole("button", { name: "Add job" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.addJob).toHaveBeenCalledWith({
      source: "url",
      url: "https://x.io/jobs/1",
    });
  });

  it("says so and links to the existing job on a duplicate", async () => {
    api.addJob.mockResolvedValue({
      job_id: "j7",
      status: null,
      duplicate: true,
    });
    const { onClose } = setup();
    await userEvent.type(
      screen.getByLabelText("Job link"),
      "https://x.io/jobs/1",
    );
    await userEvent.click(screen.getByRole("button", { name: "Add job" }));
    const link = await screen.findByRole("link", {
      name: "Open the existing job",
    });
    expect(link).toHaveAttribute("href", "/jobs/j7");
    expect(screen.getByText(/already added this job/)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("keeps pasted text when the server rejects it", async () => {
    api.addJob.mockRejectedValue(apiError(429, "rate_limited"));
    setup();
    await userEvent.click(screen.getByRole("radio", { name: "Paste text" }));
    const box = screen.getByLabelText("Job description");
    await userEvent.type(box, "Senior engineer wanted");
    await userEvent.click(screen.getByRole("button", { name: "Add job" }));
    expect(await screen.findByText("rate_limited")).toBeInTheDocument();
    expect(box).toHaveValue("Senior engineer wanted");
    expect(api.addJob).toHaveBeenCalledWith({
      source: "text",
      text: "Senior engineer wanted",
    });
  });

  it("validates empty input", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: "Add job" }));
    expect(await screen.findByText("Enter the job link.")).toBeInTheDocument();
    expect(api.addJob).not.toHaveBeenCalled();
  });

  it("uploads the screenshot first, then adds with image_id; rejects wrong types", async () => {
    api.uploadImage.mockResolvedValue("img1");
    api.addJob.mockResolvedValue({
      job_id: "j2",
      status: "processing",
      duplicate: false,
    });
    const { onClose } = setup();
    await userEvent.click(screen.getByRole("radio", { name: "Screenshot" }));
    const input = screen.getByLabelText("Screenshot file");
    await userEvent.upload(
      input,
      new File(["x"], "a.png", { type: "image/png" }),
      {
        applyAccept: false,
      },
    );
    await userEvent.click(screen.getByRole("button", { name: "Add job" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.uploadImage).toHaveBeenCalledTimes(1);
    expect(api.addJob).toHaveBeenCalledWith({
      source: "image",
      image_id: "img1",
    });
  });

  it("rejects a non-image file without calling the API", async () => {
    setup();
    await userEvent.click(screen.getByRole("radio", { name: "Screenshot" }));
    await userEvent.upload(
      screen.getByLabelText("Screenshot file"),
      new File(["x"], "a.gif", { type: "image/gif" }),
      { applyAccept: false },
    );
    await userEvent.click(screen.getByRole("button", { name: "Add job" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/PNG and JPEG/);
    expect(api.uploadImage).not.toHaveBeenCalled();
  });

  it("does not upload twice when only the add step failed", async () => {
    api.uploadImage.mockResolvedValue("img1");
    api.addJob.mockRejectedValueOnce(apiError(500, "server_error"));
    api.addJob.mockResolvedValueOnce({ job_id: "j2", duplicate: false });
    const { onClose } = setup();
    await userEvent.click(screen.getByRole("radio", { name: "Screenshot" }));
    await userEvent.upload(
      screen.getByLabelText("Screenshot file"),
      new File(["x"], "a.png", { type: "image/png" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Add job" }));
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Add job" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.uploadImage).toHaveBeenCalledTimes(1);
  });
});
