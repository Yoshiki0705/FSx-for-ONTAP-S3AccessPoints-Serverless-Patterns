import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { THUMBNAIL_EXTENSIONS, isThumbnailable } from "../../src/hooks/useThumbnails";

const HANDLER = resolve(
  import.meta.dirname,
  "../../functions/thumbnails/handler.py",
);

/**
 * The extensions the client asks about must be the ones the backend can render.
 *
 * Two lists, one per language, and nothing else would notice them disagreeing. An
 * extension only the client believes in costs an invocation that always answers
 * "unsupported type"; one only the backend believes in leaves an icon where a picture
 * belonged. Both are silent.
 *
 * The temptation was to reuse `IMAGE_EXTENSIONS` from FilePreview, which is the list
 * of things the portal can *open*. It includes `.svg`, which Pillow cannot rasterise,
 * and omits `.tif`, which it reads -- so it is wrong in both directions at once.
 */
describe("the thumbnail extension list", () => {
  const backendExtensions = (): string[] => {
    const source = readFileSync(HANDLER, "utf-8");
    const match = source.match(/SUPPORTED_EXTENSIONS\s*=\s*\(([^)]*)\)/);
    expect(match, "SUPPORTED_EXTENSIONS not found in the handler").toBeTruthy();
    return [...match![1].matchAll(/"([^"]+)"/g)].map((found) => found[1]);
  };

  it("finds the tuple in the handler", () => {
    // Guards the reader: an empty result would make the comparison below vacuous.
    expect(backendExtensions().length).toBeGreaterThan(3);
  });

  it("matches what the handler can render", () => {
    expect([...THUMBNAIL_EXTENSIONS].sort()).toEqual(backendExtensions().sort());
  });

  it("does not include a format Pillow cannot rasterise", () => {
    expect(THUMBNAIL_EXTENSIONS).not.toContain(".svg");
  });
});

describe("isThumbnailable", () => {
  it("accepts the formats the backend renders", () => {
    expect(isThumbnailable("holiday.jpg")).toBe(true);
    expect(isThumbnailable("scan.TIFF")).toBe(true);
  });

  it("is case insensitive, because a phone camera writes .JPG", () => {
    expect(isThumbnailable("IMG_5122.JPG")).toBe(true);
  });

  it("rejects everything else", () => {
    expect(isThumbnailable("report.pdf")).toBe(false);
    expect(isThumbnailable("diagram.svg")).toBe(false);
    expect(isThumbnailable("archive.tar.gz")).toBe(false);
    expect(isThumbnailable("no-extension")).toBe(false);
  });

  it("does not match an extension appearing mid-name", () => {
    // `.png` inside the name is not the format of the file.
    expect(isThumbnailable("notes.png.txt")).toBe(false);
  });
});
