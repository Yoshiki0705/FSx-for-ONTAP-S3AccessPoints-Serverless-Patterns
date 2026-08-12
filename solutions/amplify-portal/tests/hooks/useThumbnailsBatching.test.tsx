import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement, ReactNode } from "react";

const thumbnailQuery = vi.fn();
vi.mock("../../src/lib/dispatch", () => ({
  thumbnailQuery: (call: unknown) => thumbnailQuery(call),
  // FilePreview reaches for these; they are not exercised here.
  dispatch: vi.fn(),
  adminMutate: vi.fn(),
}));

import { useThumbnails } from "../../src/hooks/useThumbnails";
import { FilePreview } from "../../src/components/FilePreview";
import { I18nProvider } from "../../src/i18n";

const wrapper = ({ children }: { children: ReactNode }) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
};

const renderUi = (ui: ReactElement) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
};

beforeEach(() => {
  thumbnailQuery.mockReset();
  thumbnailQuery.mockResolvedValue({ thumbnails: {}, pending: [], skipped: {} });
});

/** The keys sent in the one request the hook should make. */
const requestedKeys = (): string[] =>
  (thumbnailQuery.mock.calls[0]?.[0] as { params: { keys: string[] } }).params.keys;

describe("useThumbnails", () => {
  // The whole reason this path exists. A presigned URL per row costs an invocation
  // per row; a hundred-file page would be a hundred calls before anything rendered.
  it("makes one request for a page of images, not one per file", async () => {
    const keys = Array.from({ length: 40 }, (_, index) => `photos/${index}.jpg`);

    renderHook(() => useThumbnails(keys), { wrapper });

    await waitFor(() => expect(thumbnailQuery).toHaveBeenCalledTimes(1));
    expect(requestedKeys()).toHaveLength(40);
  });

  it("asks only about files it could render", async () => {
    renderHook(
      () => useThumbnails(["a.jpg", "notes.pdf", "b.png", "diagram.svg", "c.tiff"]),
      { wrapper },
    );

    await waitFor(() => expect(thumbnailQuery).toHaveBeenCalled());
    expect(requestedKeys().sort()).toEqual(["a.jpg", "b.png", "c.tiff"]);
  });

  it("does not call the endpoint for a page with no images", async () => {
    renderHook(() => useThumbnails(["notes.pdf", "data.csv", "archive.zip"]), { wrapper });

    // Nothing to ask about, so the query stays disabled. A request here would be one
    // invocation per folder of documents, for no thumbnails.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(thumbnailQuery).not.toHaveBeenCalled();
  });

  it("does not call the endpoint for an empty page", async () => {
    renderHook(() => useThumbnails([]), { wrapper });

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(thumbnailQuery).not.toHaveBeenCalled();
  });

  it("returns the URL for a key the backend rendered", async () => {
    thumbnailQuery.mockResolvedValue({
      thumbnails: { "photos/a.jpg": "https://example.test/a" },
      pending: [],
      skipped: {},
    });

    const { result } = renderHook(() => useThumbnails(["photos/a.jpg"]), { wrapper });

    await waitFor(() => expect(result.current.urlFor("photos/a.jpg")).toBe("https://example.test/a"));
  });

  it("returns nothing for a key the backend skipped", async () => {
    thumbnailQuery.mockResolvedValue({
      thumbnails: {},
      pending: [],
      skipped: { "photos/huge.png": "larger than 26214400 bytes" },
    });

    const { result } = renderHook(() => useThumbnails(["photos/huge.png"]), { wrapper });

    await waitFor(() => expect(thumbnailQuery).toHaveBeenCalled());
    expect(result.current.urlFor("photos/huge.png")).toBeUndefined();
  });

  it("survives a failure without taking the listing with it", async () => {
    // A thumbnail is decoration. If the endpoint is broken the rows must still render.
    thumbnailQuery.mockResolvedValue(null);

    const { result } = renderHook(() => useThumbnails(["photos/a.jpg"]), { wrapper });

    await waitFor(() => expect(thumbnailQuery).toHaveBeenCalled());
    expect(result.current.urlFor("photos/a.jpg")).toBeUndefined();
  });

  it("sends the same request once for two renders of the same page", async () => {
    // The key is the sorted list, so a re-render with the files in another order is
    // the same page and must not be a second invocation.
    const { rerender } = renderHook(({ keys }) => useThumbnails(keys), {
      wrapper,
      initialProps: { keys: ["b.jpg", "a.jpg"] },
    });

    await waitFor(() => expect(thumbnailQuery).toHaveBeenCalledTimes(1));
    rerender({ keys: ["a.jpg", "b.jpg"] });
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(thumbnailQuery).toHaveBeenCalledTimes(1);
  });
});

describe("FilePreview with a thumbnail", () => {
  it("shows the picture instead of the glyph", () => {
    renderUi(
      <FilePreview fileKey="photos/a.jpg" fileName="a.jpg" thumbnailUrl="https://example.test/a" />,
    );

    const image = document.querySelector("img.file-thumbnail") as HTMLImageElement;
    expect(image).toBeTruthy();
    expect(image.src).toBe("https://example.test/a");
    // The button already carries the file name, so the image must not repeat it.
    expect(image.alt).toBe("");
    // The attribute, not `image.loading`: jsdom does not implement that IDL property
    // and returns undefined for it, so the property form passes on any value.
    expect(image.getAttribute("loading")).toBe("lazy");
  });

  it("keeps the glyph when there is no thumbnail", () => {
    renderUi(<FilePreview fileKey="photos/a.jpg" fileName="a.jpg" />);

    expect(document.querySelector("img.file-thumbnail")).toBeNull();
  });

  it("falls back to the glyph if the URL stops working", () => {
    // A signed URL can expire while the page is open, and a cache entry can be
    // deleted underneath it. Either way a broken-image icon is worse than the glyph.
    renderUi(
      <FilePreview fileKey="photos/a.jpg" fileName="a.jpg" thumbnailUrl="https://example.test/a" />,
    );

    fireEvent.error(document.querySelector("img.file-thumbnail")!);

    expect(document.querySelector("img.file-thumbnail")).toBeNull();
    expect(screen.getByRole("button")).toBeTruthy();
  });
});
