import { describe, it, expect } from "vitest";
import { oneOf } from "../../src/utils/oneOf";

/**
 * `oneOf` exists because a `<select>` hands back `string` however few options it has.
 * Widening the state to `string` to make that compile is what let `snaplockType`
 * reach ONTAP misspelled, where it produced a volume with no SnapLock rather than an
 * error, so the narrowing has to happen at the DOM boundary.
 */
describe("oneOf", () => {
  it("keeps a value that is in the set", () => {
    expect(oneOf(["unix", "ntfs", "mixed"], "ntfs", "unix")).toBe("ntfs");
  });

  it("falls back when the value is not in the set", () => {
    expect(oneOf(["unix", "ntfs", "mixed"], "unxi", "unix")).toBe("unix");
  });

  it("falls back on an empty value, which a cleared select produces", () => {
    expect(oneOf(["GOVERNANCE", "COMPLIANCE"], "", "GOVERNANCE")).toBe("GOVERNANCE");
  });

  it("is case sensitive, matching how the actions compare", () => {
    // ONTAP compares these exactly; accepting "compliance" for "COMPLIANCE" here
    // would move the failure to the API instead of the form.
    expect(oneOf(["GOVERNANCE", "COMPLIANCE"], "compliance", "GOVERNANCE")).toBe("GOVERNANCE");
  });

  it("does not treat a prototype property as a member", () => {
    expect(oneOf(["unix"], "toString", "unix")).toBe("unix");
  });
});
