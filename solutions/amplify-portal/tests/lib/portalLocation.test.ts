import { describe, it, expect } from "vitest";
import { hashFor, locationFromHash, SECTIONS } from "../../src/lib/portalLocation";

describe("hashFor", () => {
  it("names the section alone when there is no folder", () => {
    expect(hashFor("files", "")).toBe("files");
    expect(hashFor("audit", "")).toBe("audit");
  });

  it("ignores a folder for sections that have none", () => {
    // Only the explorer is addressed by folder. Appending a prefix elsewhere
    // would produce an address that reads as meaningful and is not.
    expect(hashFor("process", "dept/legal/")).toBe("process");
  });

  it("keeps separators readable and drops the trailing one", () => {
    expect(hashFor("files", "dept/legal/")).toBe("files/dept/legal");
  });

  it("encodes a segment so it cannot forge a level", () => {
    // A folder whose name contains a slash must stay one segment, or the address
    // would describe a deeper path than the one it came from.
    expect(hashFor("files", "a/b/")).not.toBe(hashFor("files", "a%2Fb/"));
    expect(locationFromHash(hashFor("files", "we/ird/"))?.prefix).toBe("we/ird/");
  });
});

describe("locationFromHash", () => {
  it("reads a bare section", () => {
    expect(locationFromHash("#resources")).toEqual({ section: "resources", prefix: "" });
  });

  it("accepts a hash with or without the leading marker", () => {
    expect(locationFromHash("files")).toEqual(locationFromHash("#files"));
  });

  it("restores the trailing separator a prefix needs", () => {
    expect(locationFromHash("#files/dept/legal")).toEqual({
      section: "files",
      prefix: "dept/legal/",
    });
  });

  it("tolerates a trailing separator in the address", () => {
    expect(locationFromHash("#files/dept/")?.prefix).toBe("dept/");
  });

  it("refuses a hash that names no section", () => {
    expect(locationFromHash("#nonsense")).toBeNull();
    expect(locationFromHash("#nonsense/dept")).toBeNull();
    expect(locationFromHash("")).toBeNull();
    expect(locationFromHash("#")).toBeNull();
  });

  it("round-trips every section", () => {
    for (const section of SECTIONS) {
      expect(locationFromHash(`#${hashFor(section, "")}`)).toEqual({ section, prefix: "" });
    }
  });

  it("round-trips folders with characters that need encoding", () => {
    for (const prefix of ["dept/legal/", "a b/c+d/", "日本語/資料/", "with#hash/", "100%/"]) {
      expect(locationFromHash(`#${hashFor("files", prefix)}`)).toEqual({
        section: "files",
        prefix,
      });
    }
  });

  it("hands the trash prefix back unchanged", () => {
    // The trash is a folder like any other, so it has to survive the address.
    expect(locationFromHash(`#${hashFor("files", ".trash/")}`)?.prefix).toBe(".trash/");
  });
});
