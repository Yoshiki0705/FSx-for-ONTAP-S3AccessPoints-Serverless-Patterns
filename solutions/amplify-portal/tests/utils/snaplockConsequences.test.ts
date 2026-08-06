import { describe, it, expect } from "vitest";
import {
  SNAPLOCK_CONFIRM_KEYWORD,
  addPeriod,
  confirmationLevel,
  describeConsequences,
  intentSubject,
  isZeroPeriod,
  lockedUntil,
  parseIsoPeriod,
  type SnaplockIntent,
} from "../../src/utils/snaplockConsequences";

/** Fixed clock so the expected dates are literals rather than arithmetic. */
const NOW = new Date("2026-08-06T00:00:00.000Z");

describe("parseIsoPeriod", () => {
  it("parses each component and combinations", () => {
    expect(parseIsoPeriod("P30D")).toEqual({ years: 0, months: 0, days: 30 });
    expect(parseIsoPeriod("P6M")).toEqual({ years: 0, months: 6, days: 0 });
    expect(parseIsoPeriod("P1Y")).toEqual({ years: 1, months: 0, days: 0 });
    expect(parseIsoPeriod("P1Y6M15D")).toEqual({ years: 1, months: 6, days: 15 });
  });

  it("treats P0D as zero rather than invalid", () => {
    // The retention forms use P0D to mean no retention, so it has to parse.
    expect(parseIsoPeriod("P0D")).toEqual({ years: 0, months: 0, days: 0 });
    expect(isZeroPeriod(parseIsoPeriod("P0D")!)).toBe(true);
  });

  it("rejects a period with no components", () => {
    expect(parseIsoPeriod("P")).toBeNull();
  });

  it("rejects a time part rather than silently dropping it", () => {
    // Ignoring the T would understate the period, which is the one direction
    // this module must never round in.
    expect(parseIsoPeriod("P1DT12H")).toBeNull();
    expect(parseIsoPeriod("PT12H")).toBeNull();
  });

  it("rejects values that are not periods", () => {
    expect(parseIsoPeriod("")).toBeNull();
    expect(parseIsoPeriod("30D")).toBeNull();
    expect(parseIsoPeriod("custom")).toBeNull();
  });

  it("tolerates surrounding whitespace", () => {
    expect(parseIsoPeriod("  P7D  ")).toEqual({ years: 0, months: 0, days: 7 });
  });
});

describe("addPeriod", () => {
  it("adds days", () => {
    expect(addPeriod(NOW, { years: 0, months: 0, days: 30 }).toISOString()).toBe(
      "2026-09-05T00:00:00.000Z"
    );
  });

  it("adds calendar months, not 30-day blocks", () => {
    // Six calendar months from 6 August is 6 February, which is what ONTAP
    // reports as expiry_time. 180 days would land on 2 February and would not
    // match what the operator sees in the console.
    expect(addPeriod(NOW, { years: 0, months: 6, days: 0 }).toISOString()).toBe(
      "2027-02-06T00:00:00.000Z"
    );
  });

  it("rolls the year over", () => {
    expect(addPeriod(NOW, { years: 1, months: 0, days: 0 }).toISOString()).toBe(
      "2027-08-06T00:00:00.000Z"
    );
  });

  it("does not mutate its argument", () => {
    const before = NOW.toISOString();
    addPeriod(NOW, { years: 2, months: 3, days: 4 });
    expect(NOW.toISOString()).toBe(before);
  });
});

describe("lockedUntil", () => {
  it("uses the ceiling for volume creation, not the default", () => {
    // The default applies per file at commit time, so it does not bound when the
    // volume stops being deletable. Only the maximum does.
    const until = lockedUntil(
      {
        kind: "createSnaplockVolume",
        volumeName: "v",
        snaplockType: "enterprise",
        retentionDefault: "P30D",
        retentionMax: "P1Y",
      },
      NOW
    );
    expect(until?.toISOString()).toBe("2027-08-06T00:00:00.000Z");
  });

  it("is null when nothing dated would be locked", () => {
    expect(
      lockedUntil({ kind: "enableSnapshotLocking", volumeName: "v" }, NOW)
    ).toBeNull();
    expect(
      lockedUntil({ kind: "lockSnapshot", snapshotName: "s", retentionDays: 0 }, NOW)
    ).toBeNull();
    expect(
      lockedUntil(
        { kind: "updateSnaplockRetention", volumeName: "v", retentionDefault: "P0D" },
        NOW
      )
    ).toBeNull();
  });

  it("is null when the period cannot be parsed", () => {
    expect(
      lockedUntil(
        { kind: "updateSnaplockRetention", volumeName: "v", retentionDefault: "nonsense" },
        NOW
      )
    ).toBeNull();
  });
});

describe("describeConsequences", () => {
  const createIntent = (
    snaplockType: "compliance" | "enterprise"
  ): SnaplockIntent => ({
    kind: "createSnaplockVolume",
    volumeName: "worm_vol",
    snaplockType,
    retentionDefault: "P30D",
    retentionMax: "P1Y",
  });

  it("leads with what cannot be undone", () => {
    // An operator who reads only the first line should read the irreversible
    // part, so ordering is asserted rather than left to chance.
    const [first] = describeConsequences(createIntent("compliance"), NOW);
    expect(first.severity).toBe("irreversible");
    expect(first.messageKey).toBe("slcTypeImmutable");
  });

  it("says nobody can delete under compliance", () => {
    const keys = describeConsequences(createIntent("compliance"), NOW).map(
      (c) => c.messageKey
    );
    expect(keys).toContain("slcComplianceNoDelete");
    expect(keys).not.toContain("slcEnterprisePrivilegedDelete");
  });

  it("mentions privileged delete under enterprise instead", () => {
    const keys = describeConsequences(createIntent("enterprise"), NOW).map(
      (c) => c.messageKey
    );
    expect(keys).toContain("slcEnterprisePrivilegedDelete");
    expect(keys).not.toContain("slcComplianceNoDelete");
  });

  it("states that the lock reaches the SVM and file system", () => {
    // This is the consequence the incident turned on: the volume was not the
    // thing that mattered, the file system was.
    const keys = describeConsequences(createIntent("enterprise"), NOW).map(
      (c) => c.messageKey
    );
    expect(keys).toContain("slcWormBlocksParents");
    expect(keys).toContain("slcBillingContinues");
  });

  it("says an empty volume is still deletable", () => {
    const keys = describeConsequences(createIntent("enterprise"), NOW).map(
      (c) => c.messageKey
    );
    expect(keys).toContain("slcEmptyStillDeletable");
  });

  it("passes the resolved date through for substitution", () => {
    const dated = describeConsequences(createIntent("enterprise"), NOW).find(
      (c) => c.messageKey === "slcWormMaxUntil"
    );
    expect(dated?.values?.date).toBe("2027-08-06T00:00:00.000Z");
    expect(dated?.values?.period).toBe("P1Y");
  });

  it("distinguishes a zero retention update from a real one", () => {
    const zero = describeConsequences(
      { kind: "updateSnaplockRetention", volumeName: "v", retentionDefault: "P0D" },
      NOW
    ).map((c) => c.messageKey);
    expect(zero).toContain("slcRetentionZero");
    expect(zero).not.toContain("slcWormBlocksParents");

    const real = describeConsequences(
      { kind: "updateSnaplockRetention", volumeName: "v", retentionDefault: "P30D" },
      NOW
    ).map((c) => c.messageKey);
    expect(real).toContain("slcRetentionNewFileUntil");
    expect(real).toContain("slcWormBlocksParents");
  });

  it("says enabling locking locks nothing yet", () => {
    // Conflating "can be locked" with "is locked" is the standing confusion in
    // this area, so the dialog has to say both halves.
    const keys = describeConsequences(
      { kind: "enableSnapshotLocking", volumeName: "v" },
      NOW
    ).map((c) => c.messageKey);
    expect(keys).toContain("slcLockingCannotDisable");
    expect(keys).toContain("slcLockingLocksNothingYet");
  });

  it("scopes a snapshot lock to that snapshot", () => {
    const keys = describeConsequences(
      { kind: "lockSnapshot", snapshotName: "snap1", retentionDays: 7 },
      NOW
    ).map((c) => c.messageKey);
    expect(keys).toContain("slcSnapshotExtendOnly");
    expect(keys).toContain("slcSnapshotScope");
    expect(keys).not.toContain("slcWormBlocksParents");
  });

  it("separates S3 compliance from governance", () => {
    const compliance = describeConsequences(
      { kind: "s3ObjectLock", bucket: "b", mode: "COMPLIANCE", days: 14 },
      NOW
    );
    expect(compliance[0].severity).toBe("irreversible");
    expect(compliance.map((c) => c.messageKey)).toContain("slcS3ComplianceNoChange");

    const governance = describeConsequences(
      { kind: "s3ObjectLock", bucket: "b", mode: "GOVERNANCE", days: 14 },
      NOW
    );
    expect(governance.every((c) => c.severity !== "irreversible")).toBe(true);
    expect(governance.map((c) => c.messageKey)).toContain("slcS3GovernanceBypass");
  });
});

describe("confirmationLevel", () => {
  it("requires a typed keyword for creating a SnapLock volume", () => {
    // Both types, because the incident was on an enterprise volume: the type
    // being reversible-sounding did not make the lock reversible.
    for (const snaplockType of ["compliance", "enterprise"] as const) {
      expect(
        confirmationLevel({
          kind: "createSnaplockVolume",
          volumeName: "v",
          snaplockType,
          retentionDefault: "P30D",
          retentionMax: "P1Y",
        })
      ).toBe("keyword");
    }
  });

  it("requires a typed keyword for enabling snapshot locking", () => {
    expect(confirmationLevel({ kind: "enableSnapshotLocking", volumeName: "v" })).toBe(
      "keyword"
    );
  });

  it("requires a typed keyword for S3 compliance mode only", () => {
    expect(
      confirmationLevel({ kind: "s3ObjectLock", bucket: "b", mode: "COMPLIANCE", days: 14 })
    ).toBe("keyword");
    expect(
      confirmationLevel({ kind: "s3ObjectLock", bucket: "b", mode: "GOVERNANCE", days: 14 })
    ).toBe("acknowledge");
  });

  it("asks only for acknowledgement on a snapshot lock", () => {
    // It cannot be shortened, but it expires on its own and reaches nothing
    // else. Requiring the keyword on a routine action would train operators to
    // type it without reading.
    expect(
      confirmationLevel({ kind: "lockSnapshot", snapshotName: "s", retentionDays: 7 })
    ).toBe("acknowledge");
  });

  it("asks only for acknowledgement on a retention change", () => {
    expect(
      confirmationLevel({
        kind: "updateSnaplockRetention",
        volumeName: "v",
        retentionDefault: "P30D",
      })
    ).toBe("acknowledge");
  });
});

describe("intentSubject", () => {
  it("names the resource the dialog is about", () => {
    expect(
      intentSubject({
        kind: "createSnaplockVolume",
        volumeName: "worm_vol",
        snaplockType: "enterprise",
        retentionDefault: "P30D",
        retentionMax: "P1Y",
      })
    ).toBe("worm_vol");
    expect(
      intentSubject({ kind: "lockSnapshot", snapshotName: "snap1", retentionDays: 7 })
    ).toBe("snap1");
    expect(
      intentSubject({ kind: "s3ObjectLock", bucket: "bucket1", mode: "GOVERNANCE", days: 1 })
    ).toBe("bucket1");
  });
});

describe("SNAPLOCK_CONFIRM_KEYWORD", () => {
  it("is not translated", () => {
    // The dialog compares against this exact string and interpolates it into the
    // prompt, so a locale cannot ask for one word and accept another.
    expect(SNAPLOCK_CONFIRM_KEYWORD).toBe("LOCK");
    expect(SNAPLOCK_CONFIRM_KEYWORD).toBe(SNAPLOCK_CONFIRM_KEYWORD.toUpperCase());
  });
});
