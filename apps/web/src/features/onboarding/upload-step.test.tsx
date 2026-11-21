import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/browser", async () => ({ api: (await import("./test-support")).apiMock }));
vi.mock("next/navigation", async () => {
  const { router } = await import("./test-support");
  return { useRouter: () => router };
});

import { apiMock, fail, ok, profileOut, renderWithClient, router } from "./test-support";
import { UploadStep } from "./upload-step";

const pdf = () => new File(["%PDF-1.4 hi"], "cv.pdf", { type: "application/pdf" });
const pick = (f: File) => userEvent.upload(screen.getByLabelText(/drop your resume/i), f, { applyAccept: false });

describe("UploadStep", () => {
  beforeEach(() => {
    Object.values(apiMock).forEach((m) => m.mockReset());
    router.push.mockReset();
  });

  it("rejects images without calling the API and explains why", async () => {
    renderWithClient(<UploadStep />);
    await pick(new File(["x"], "scan.png", { type: "image/png" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/Images aren't supported/);
    expect(screen.getByRole("button", { name: "Read my resume" })).toBeDisabled();
    expect(apiMock.POST).not.toHaveBeenCalled();
  });

  it("uploads a valid file as multipart, shows progress, then goes to review", async () => {
    let resolve!: (v: unknown) => void;
    apiMock.POST.mockReturnValue(new Promise((r) => (resolve = r)));
    renderWithClient(<UploadStep />);
    await pick(pdf());
    await userEvent.click(screen.getByRole("button", { name: "Read my resume" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Reading your resume…");
    const [path, init] = apiMock.POST.mock.calls[0];
    expect(path).toBe("/profile/upload");
    const fd = init.bodySerializer() as FormData;
    expect((fd.get("file") as File).name).toBe("cv.pdf");
    resolve(ok(profileOut()));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/onboarding/review"));
  });

  it("keeps the chosen file and offers retry when the server fails", async () => {
    apiMock.POST.mockResolvedValueOnce(
      fail(502, { code: "extraction_failed", message: "Could not extract a profile from the resume" }),
    ).mockResolvedValueOnce(ok(profileOut()));
    renderWithClient(<UploadStep />);
    await pick(pdf());
    await userEvent.click(screen.getByRole("button", { name: "Read my resume" }));
    expect(await screen.findByText("We couldn't read this resume")).toBeInTheDocument();
    expect(screen.getByText("cv.pdf")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(router.push).toHaveBeenCalled());
    expect(apiMock.POST).toHaveBeenCalledTimes(2);
  });

  it("can start from an empty draft via PUT /profile/draft", async () => {
    apiMock.PUT.mockResolvedValue(ok(profileOut()));
    renderWithClient(<UploadStep />);
    await userEvent.click(screen.getByRole("button", { name: "Start without a resume" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/onboarding/review"));
    expect(apiMock.PUT.mock.calls[0][0]).toBe("/profile/draft");
  });
});
