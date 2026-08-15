/**
 * The Storage Browser write handlers replace the vendor ones because this access
 * point answers a conditional write with 501. These tests pin the two properties
 * that made the first replacement wrong.
 *
 * The first version ran the existence lookup and the upload concurrently. For a
 * small file the PUT finished first, the lookup then found the object the PUT had
 * just written, and the handler reported OVERWRITE_PREVENTED for an upload that
 * had succeeded -- which is what a phone saw as "failed to upload" while the
 * object was in the bucket. Nothing in the type system objects to that ordering,
 * so it is asserted here.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const uploadData = vi.fn();
const list = vi.fn();

vi.mock("@aws-amplify/storage/internals", () => ({
  uploadData: (...args: unknown[]) => uploadData(...args),
  list: (...args: unknown[]) => list(...args),
}));

vi.mock("aws-amplify/storage", () => ({ isCancelError: () => false }));

const { uploadWithoutConditionalWrite, createFolderWithoutConditionalWrite } = await import(
  "../../src/lib/storageBrowserWriteHandlers"
);

const config = {
  bucket: "ap-alias",
  region: "ap-northeast-1",
  accountId: undefined,
  credentials: vi.fn(),
  customEndpoint: undefined,
} as unknown as Parameters<typeof uploadWithoutConditionalWrite>[0]["config"];

const file = { size: 1_816_045, name: "photo.jpeg" } as unknown as File;

const input = (overrides: Record<string, unknown> = {}) =>
  ({
    config,
    data: { key: "uploadtest/photo.jpeg", file, preventOverwrite: true, ...overrides },
    options: {},
  }) as unknown as Parameters<typeof uploadWithoutConditionalWrite>[0];

/** Resolves after `ms`, so a slow lookup can be placed against a fast upload. */
const later = <T,>(value: T, ms: number) =>
  new Promise<T>((resolve) => setTimeout(() => resolve(value), ms));

beforeEach(() => {
  uploadData.mockReset();
  list.mockReset();
  uploadData.mockReturnValue({
    cancel: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    result: Promise.resolve({ path: "uploadtest/photo.jpeg" }),
  });
});

describe("uploadWithoutConditionalWrite", () => {
  it("does not start the upload until the lookup has answered", async () => {
    const order: string[] = [];
    list.mockImplementation(() => {
      order.push("list");
      return later({ items: [] }, 20);
    });
    uploadData.mockImplementation(() => {
      order.push("upload");
      return { cancel: vi.fn(), pause: vi.fn(), resume: vi.fn(), result: Promise.resolve({ path: "uploadtest/photo.jpeg" }) };
    });

    const { result } = uploadWithoutConditionalWrite(input());
    expect(uploadData).not.toHaveBeenCalled();

    await expect(result).resolves.toMatchObject({ status: "COMPLETE" });
    expect(order).toEqual(["list", "upload"]);
  });

  it("reports COMPLETE when a slow lookup finds nothing", async () => {
    // The regression: with the concurrent version the upload had already written
    // the object by the time this resolved, and the handler read its own write as
    // a pre-existing file.
    list.mockReturnValue(later({ items: [] }, 30));

    const { result } = uploadWithoutConditionalWrite(input());
    await expect(result).resolves.toMatchObject({ status: "COMPLETE" });
  });

  it("refuses an existing key without writing", async () => {
    list.mockResolvedValue({ items: [{ path: "uploadtest/photo.jpeg" }] });

    const { result } = uploadWithoutConditionalWrite(input());
    await expect(result).resolves.toMatchObject({ status: "OVERWRITE_PREVENTED" });
    expect(uploadData).not.toHaveBeenCalled();
  });

  it("skips the lookup when overwriting is allowed", async () => {
    const { result } = uploadWithoutConditionalWrite(input({ preventOverwrite: false }));
    await expect(result).resolves.toMatchObject({ status: "COMPLETE" });
    expect(list).not.toHaveBeenCalled();
  });

  it("sends no conditional write or checksum override in the options", async () => {
    list.mockResolvedValue({ items: [] });
    await uploadWithoutConditionalWrite(input()).result;

    const [{ options }] = uploadData.mock.calls[0] as [{ options: Record<string, unknown> }];
    expect(options).not.toHaveProperty("preventOverwrite");
    // The vendor checksum is kept: measured to be accepted by this endpoint.
    expect(options.checksumAlgorithm).toBe("crc-32");
  });

  it("treats a failed lookup as absent rather than blocking the write", async () => {
    list.mockRejectedValue(new Error("network"));

    const { result } = uploadWithoutConditionalWrite(input());
    await expect(result).resolves.toMatchObject({ status: "COMPLETE" });
  });
});

describe("createFolderWithoutConditionalWrite", () => {
  it("refuses an existing folder without writing", async () => {
    list.mockResolvedValue({ items: [{ path: "uploadtest/" }] });

    const { result } = createFolderWithoutConditionalWrite({
      config,
      data: { key: "uploadtest/", preventOverwrite: true },
      options: {},
    } as unknown as Parameters<typeof createFolderWithoutConditionalWrite>[0]);

    await expect(result).resolves.toMatchObject({ status: "OVERWRITE_PREVENTED" });
    expect(uploadData).not.toHaveBeenCalled();
  });

  it("creates a folder that does not exist", async () => {
    list.mockResolvedValue({ items: [] });
    uploadData.mockReturnValue({ result: Promise.resolve({ path: "new/" }) });

    const { result } = createFolderWithoutConditionalWrite({
      config,
      data: { key: "new/", preventOverwrite: true },
      options: {},
    } as unknown as Parameters<typeof createFolderWithoutConditionalWrite>[0]);

    await expect(result).resolves.toMatchObject({ status: "COMPLETE" });
  });
});
