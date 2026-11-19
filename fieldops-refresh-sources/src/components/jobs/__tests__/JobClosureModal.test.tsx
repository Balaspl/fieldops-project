import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import { JobClosureModal } from "../JobClosureModal";
import { closeJob } from "../../../services/planningService";

vi.mock("../../../services/planningService", () => ({
  closeJob: vi.fn(),
}));

const mockedCloseJob = vi.mocked(closeJob);

class MockFileReader {
  result: string | null = null;
  onload: ((event: ProgressEvent<FileReader>) => void) | null = null;
  onloadend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onprogress: ((event: ProgressEvent<FileReader>) => void) | null = null;

  readAsDataURL(_file: File) {
    this.result = "data:image/jpeg;base64,TEST_IMAGE";

    this.onprogress?.({
      lengthComputable: true,
      loaded: 50,
      total: 100,
    } as ProgressEvent<FileReader>);

    this.onload?.({
      target: this,
    } as unknown as ProgressEvent<FileReader>);

    this.onloadend?.();
  }
}

class MockImage {
  width = 1200;
  height = 800;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;

  set src(_value: string) {
    this.onload?.();
  }
}

const realCreateElement = Document.prototype.createElement;

const setupBrowserImageMocks = () => {
  vi.stubGlobal("FileReader", MockFileReader);
  vi.stubGlobal("Image", MockImage);

  vi.spyOn(document, "createElement").mockImplementation((tagName, options) => {
    if (tagName === "canvas") {
      const canvas = realCreateElement.call(
        document,
        "canvas",
        options,
      ) as HTMLCanvasElement;

      vi.spyOn(canvas, "getContext").mockReturnValue({
        drawImage: vi.fn(),
      } as unknown as CanvasRenderingContext2D);

      vi.spyOn(canvas, "toDataURL").mockReturnValue(
        "data:image/jpeg;base64,COMPRESSED_IMAGE",
      );

      return canvas;
    }

    return realCreateElement.call(document, tagName, options);
  });
};

const createImageFile = (
  name = "after-photo.jpg",
  type = "image/jpeg",
) => new File(["image-content"], name, { type });

const fillRequiredFields = () => {
  fireEvent.change(screen.getByTestId("work-report-summary"), {
    target: { value: "Replaced faulty component and verified operation." },
  });

  const numberInputs = screen
    .getAllByRole("spinbutton")
    .filter(
      (input) =>
        !(input as HTMLInputElement).hasAttribute("data-testid") ||
        (input as HTMLInputElement).getAttribute("data-testid") ===
          null,
    );

  const serviceChargeInput = numberInputs[0] as HTMLInputElement;
  const materialCostInput = numberInputs[1] as HTMLInputElement;

  fireEvent.change(serviceChargeInput, {
    target: { value: "500" },
  });

  fireEvent.change(materialCostInput, {
    target: { value: "150" },
  });
};

const getFileInputs = () =>
  Array.from(
    document.querySelectorAll('input[type="file"]'),
  ) as HTMLInputElement[];

describe("JobClosureModal - Photo Upload Screen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupBrowserImageMocks();

    mockedCloseJob.mockResolvedValue({
      data: { id: 9001 },
    } as Awaited<ReturnType<typeof closeJob>>);
  });

  it("renders before and after photo upload controls", () => {
    render(
      <JobClosureModal
        jobId={1001}
        isOpen
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    expect(screen.getByText("Before Images (Optional)")).toBeTruthy();
    expect(screen.getByText("After Images (Min 1)")).toBeTruthy();

    const fileInputs = getFileInputs();
    expect(fileInputs).toHaveLength(2);
    expect(fileInputs[0].accept).toBe("image/*");
    expect(fileInputs[1].accept).toBe("image/*");
  });

  it("rejects a non-image file and reports the validation failure", async () => {
    render(
      <JobClosureModal
        jobId={1002}
        isOpen
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    const beforeInput = getFileInputs()[0];

    fireEvent.change(beforeInput, {
      target: {
        files: [createImageFile("notes.txt", "text/plain")],
      },
    });

    expect(
      await screen.findByText(
        '"notes.txt" is not a supported image file.',
      ),
    ).toBeTruthy();

    expect(screen.getByText("No photos were added.")).toBeTruthy();
    expect(document.querySelectorAll('img[alt^="Before"]').length).toBe(0);
  });

  it("prepares a selected image, shows the preview, and reports the upload result", async () => {
    render(
      <JobClosureModal
        jobId={1003}
        isOpen
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    const afterInput = getFileInputs()[1];

    fireEvent.change(afterInput, {
      target: {
        files: [createImageFile()],
      },
    });

    expect(
      await screen.findByAltText("After 1"),
    ).toBeTruthy();

    expect(
      await screen.findByText(
        "1 photo ready for completion upload.",
      ),
    ).toBeTruthy();

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not submit without at least one after image", async () => {
    render(
      <JobClosureModal
        jobId={1004}
        isOpen
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    fillRequiredFields();

    fireEvent.click(
      screen.getByTestId("submit-job-closure"),
    );

    expect(
      await screen.findByText(
        "At least one after image is required.",
      ),
    ).toBeTruthy();

    expect(mockedCloseJob).not.toHaveBeenCalled();
  });

  it("maps prepared before and after photos into the existing completion payload", async () => {
    const onSuccess = vi.fn();
    const onClose = vi.fn();

    render(
      <JobClosureModal
        jobId={1005}
        isOpen
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    fillRequiredFields();

    const fileInputs = getFileInputs();

    fireEvent.change(fileInputs[0], {
      target: {
        files: [createImageFile("before-photo.jpg")],
      },
    });

    fireEvent.change(fileInputs[1], {
      target: {
        files: [
          createImageFile("after-photo-1.jpg"),
          createImageFile("after-photo-2.jpg"),
        ],
      },
    });

    expect(await screen.findByAltText("Before 1")).toBeTruthy();
    expect(await screen.findByAltText("After 1")).toBeTruthy();
    expect(await screen.findByAltText("After 2")).toBeTruthy();

    fireEvent.click(
      screen.getByTestId("submit-job-closure"),
    );

    await waitFor(() => {
      expect(mockedCloseJob).toHaveBeenCalledTimes(1);
    });

    const [jobId, payload] = mockedCloseJob.mock.calls[0];

    expect(jobId).toBe(1005);
    expect(payload).toEqual(
      expect.objectContaining({
        before_images: [
          "data:image/jpeg;base64,COMPRESSED_IMAGE",
        ],
        after_images: [
          "data:image/jpeg;base64,COMPRESSED_IMAGE",
          "data:image/jpeg;base64,COMPRESSED_IMAGE",
        ],
        labour_cost: 500,
        material_cost: 150,
      }),
    );

    expect(payload.work_summary).toContain(
      "Work Summary: Replaced faulty component and verified operation.",
    );

    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows backend upload/completion errors without exposing internal details", async () => {
    mockedCloseJob.mockRejectedValueOnce({
      response: {
        status: 403,
        data: {
          detail: "Photo upload not permitted for this job.",
        },
      },
    });

    render(
      <JobClosureModal
        jobId={1006}
        isOpen
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    fillRequiredFields();

    fireEvent.change(getFileInputs()[1], {
      target: {
        files: [createImageFile()],
      },
    });

    expect(await screen.findByAltText("After 1")).toBeTruthy();

    fireEvent.click(
      screen.getByTestId("submit-job-closure"),
    );

    expect(
      await screen.findByText(
        "Photo upload not permitted for this job.",
      ),
    ).toBeTruthy();

    expect(
      screen.queryByText("FORBIDDEN_INTERNAL_PERMISSION_DATA"),
    ).toBeNull();
  });
});
