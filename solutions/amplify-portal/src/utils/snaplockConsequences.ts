/**
 * Turns SnapLock form input into the consequences of submitting it.
 *
 * The forms in this portal accept a retention period and a SnapLock type and
 * then post them. Read back, those fields say what was set but not what it
 * costs: "P6M" does not say that a file system stops being deletable, and
 * "enterprise" does not say that the choice cannot be changed afterwards. That
 * gap is what this module closes — it maps an intent to the specific things
 * that become undeletable, until when, and which of them cannot be undone.
 *
 * It is deliberately free of React and of `t()`: the dialog renders the result,
 * and the rules are asserted directly in tests. Each consequence carries a
 * translation key rather than a sentence for the same reason.
 */

import type { TranslationKeys } from "../i18n";

/** A parsed ISO-8601 period. Weeks are not used by these forms. */
export interface SnaplockPeriod {
  years: number;
  months: number;
  days: number;
}

/**
 * How much weight the consequence carries.
 *
 * `irreversible` is reserved for things that cannot be undone by anyone,
 * including the account owner and AWS Support. `blocksDeletion` is for a lock
 * that expires on its own. The distinction drives both the styling and whether
 * the dialog asks for a typed keyword, so it is not cosmetic.
 */
export type SnaplockSeverity = "irreversible" | "blocksDeletion" | "info";

export interface SnaplockConsequence {
  severity: SnaplockSeverity;
  messageKey: TranslationKeys;
  /** Substituted into the message with `{name}` style placeholders. */
  values?: Record<string, string | number>;
}

/**
 * How firmly the operator has to confirm.
 *
 * `keyword` is for operations whose lock reaches a parent resource or cannot be
 * undone at all; the operator types a word so that the action cannot happen by
 * clicking through. `acknowledge` is a checkbox, used where the lock is bounded
 * and self-contained.
 */
export type SnaplockConfirmationLevel = "keyword" | "acknowledge";

export type SnaplockIntent =
  | {
      kind: "createSnaplockVolume";
      volumeName: string;
      snaplockType: "compliance" | "enterprise";
      /** ISO-8601, applied to files as they are committed to WORM. */
      retentionDefault: string;
      /** ISO-8601 ceiling; the longest any single file can be locked for. */
      retentionMax: string;
    }
  | {
      kind: "updateSnaplockRetention";
      volumeName: string;
      retentionDefault: string;
    }
  | {
      kind: "enableSnapshotLocking";
      volumeName: string;
    }
  | {
      kind: "lockSnapshot";
      snapshotName: string;
      retentionDays: number;
    }
  | {
      kind: "s3ObjectLock";
      bucket: string;
      mode: "GOVERNANCE" | "COMPLIANCE";
      days: number;
    }
  | {
      /**
       * A snapshot policy that carries a retention period.
       *
       * Distinct from `lockSnapshot` because the lock recurs: every snapshot the
       * schedule takes is locked, not one chosen by hand. That difference is the
       * reason this has its own intent rather than reusing the snapshot wording.
       */
      kind: "snapshotPolicyRetention";
      policyName: string;
      /** ISO-8601 retention applied to each snapshot the schedule takes. */
      retentionPeriod: string;
      /** hourly / daily / weekly, as the form offers it. */
      schedule: string;
      /** Snapshots the policy keeps before rotating the oldest out. */
      count: number;
    };

const PERIOD_RE = /^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?$/;

/**
 * Parse an ISO-8601 period as these forms use it.
 *
 * `P0D` is a real value meaning no retention, so zero is parsed rather than
 * rejected. A bare `P` has no components and is rejected, as is anything with a
 * time part: none of these forms produce one, and silently ignoring `T` would
 * understate a period.
 */
export function parseIsoPeriod(period: string): SnaplockPeriod | null {
  const match = PERIOD_RE.exec(period.trim());
  if (!match) return null;
  const [, y, m, d] = match;
  if (y === undefined && m === undefined && d === undefined) return null;
  return {
    years: Number(y ?? 0),
    months: Number(m ?? 0),
    days: Number(d ?? 0),
  };
}

/**
 * The date a period ends, counted from `from`.
 *
 * Months are added as calendar months rather than 30-day blocks, because that
 * is what ONTAP reports back as `expiry_time` and a date the operator can check
 * against the console is worth more than an approximation. `setMonth` rolls the
 * year over on its own, and clamps 31 January + 1 month to early March the same
 * way the platform does.
 */
export function addPeriod(from: Date, period: SnaplockPeriod): Date {
  const out = new Date(from.getTime());
  out.setFullYear(out.getFullYear() + period.years);
  out.setMonth(out.getMonth() + period.months);
  out.setDate(out.getDate() + period.days);
  return out;
}

/** True when the period has no length, i.e. nothing would be locked. */
export function isZeroPeriod(period: SnaplockPeriod): boolean {
  return period.years === 0 && period.months === 0 && period.days === 0;
}

/**
 * The date the lock this intent creates would end, or null when the intent
 * creates no dated lock.
 *
 * For volume creation this is the ceiling, not the default: the default applies
 * per file at commit time, so the volume stops being deletable until the last
 * committed file expires, and the ceiling is the only bound that holds for
 * every file.
 */
export function lockedUntil(intent: SnaplockIntent, now: Date): Date | null {
  switch (intent.kind) {
    case "createSnaplockVolume": {
      const max = parseIsoPeriod(intent.retentionMax);
      if (!max || isZeroPeriod(max)) return null;
      return addPeriod(now, max);
    }
    case "updateSnaplockRetention": {
      const def = parseIsoPeriod(intent.retentionDefault);
      if (!def || isZeroPeriod(def)) return null;
      return addPeriod(now, def);
    }
    case "lockSnapshot":
      if (intent.retentionDays <= 0) return null;
      return addPeriod(now, { years: 0, months: 0, days: intent.retentionDays });
    case "s3ObjectLock":
      if (intent.days <= 0) return null;
      return addPeriod(now, { years: 0, months: 0, days: intent.days });
    case "snapshotPolicyRetention": {
      const period = parseIsoPeriod(intent.retentionPeriod);
      if (!period || isZeroPeriod(period)) return null;
      // The date for a snapshot taken now. Later ones move with the schedule,
      // which is what makes this recurring rather than a single expiry.
      return addPeriod(now, period);
    }
    case "enableSnapshotLocking":
      // Enabling locks nothing by itself, so there is no date to show.
      return null;
  }
}

/**
 * The date to show as the dialog headline, or null for no headline.
 *
 * The headline reads as "<subject> cannot be deleted until <date>", which only
 * holds when the date bounds the subject itself. A snapshot policy is the
 * exception: the policy stays deletable and the date belongs to the next
 * snapshot the schedule takes, so the headline would claim the wrong thing. That
 * case states its date inside the list instead, where it can say whose date it
 * is. Keeping the rule here rather than in the dialog leaves presentation free
 * of intent-specific branching and keeps it testable.
 */
export function headlineUntil(intent: SnaplockIntent, now: Date): Date | null {
  if (intent.kind === "snapshotPolicyRetention") return null;
  return lockedUntil(intent, now);
}

/**
 * What submitting this intent would do, worst consequence first.
 *
 * Ordering is deliberate: an operator who reads only the first line should read
 * the part that cannot be undone.
 */
export function describeConsequences(
  intent: SnaplockIntent,
  now: Date
): SnaplockConsequence[] {
  const out: SnaplockConsequence[] = [];
  const until = lockedUntil(intent, now);
  const untilValue = until ? until.toISOString() : "";

  switch (intent.kind) {
    case "createSnaplockVolume": {
      out.push({
        severity: "irreversible",
        messageKey: "slcTypeImmutable",
        values: { type: intent.snaplockType },
      });

      if (intent.snaplockType === "compliance") {
        out.push({ severity: "irreversible", messageKey: "slcComplianceNoDelete" });
      } else {
        out.push({ severity: "info", messageKey: "slcEnterprisePrivilegedDelete" });
      }

      out.push({ severity: "blocksDeletion", messageKey: "slcWormBlocksParents" });

      if (until) {
        out.push({
          severity: "blocksDeletion",
          messageKey: "slcWormMaxUntil",
          values: { date: untilValue, period: intent.retentionMax },
        });
      }

      // Worth saying plainly: an empty SnapLock volume is still deletable. It
      // tells the operator where the point of no return actually is, which is
      // the first committed file rather than this button.
      out.push({ severity: "info", messageKey: "slcEmptyStillDeletable" });
      out.push({ severity: "info", messageKey: "slcBillingContinues" });
      break;
    }

    case "updateSnaplockRetention": {
      out.push({ severity: "info", messageKey: "slcRetentionFutureFilesOnly" });
      if (until) {
        out.push({
          severity: "blocksDeletion",
          messageKey: "slcRetentionNewFileUntil",
          values: { date: untilValue, period: intent.retentionDefault },
        });
        out.push({ severity: "blocksDeletion", messageKey: "slcWormBlocksParents" });
      } else {
        out.push({ severity: "info", messageKey: "slcRetentionZero" });
      }
      break;
    }

    case "enableSnapshotLocking": {
      out.push({ severity: "irreversible", messageKey: "slcLockingCannotDisable" });
      out.push({ severity: "info", messageKey: "slcLockingLocksNothingYet" });
      break;
    }

    case "lockSnapshot": {
      out.push({ severity: "irreversible", messageKey: "slcSnapshotExtendOnly" });
      if (until) {
        out.push({
          severity: "blocksDeletion",
          messageKey: "slcSnapshotUntil",
          values: { date: untilValue, days: intent.retentionDays },
        });
      }
      out.push({ severity: "info", messageKey: "slcSnapshotScope" });
      break;
    }

    case "snapshotPolicyRetention": {
      if (!until) {
        // No retention means an ordinary policy. Saying so plainly is the point:
        // the field is optional and leaving it empty is the safe default.
        out.push({ severity: "info", messageKey: "slcPolicyNoRetention" });
        break;
      }

      // Recurrence first. A reader who takes in one line should learn that this
      // is not a single lock but a standing instruction to keep making them.
      out.push({
        severity: "blocksDeletion",
        messageKey: "slcPolicyEverySnapshotLocked",
        values: { schedule: intent.schedule, period: intent.retentionPeriod },
      });
      out.push({
        severity: "blocksDeletion",
        messageKey: "slcPolicyFirstSnapshotUntil",
        values: { date: untilValue },
      });

      // Locked snapshots cannot be deleted, and rotation deletes the oldest, so
      // the count stops bounding how many exist. That follows from the two rules
      // rather than being separate behaviour, and it is the part that shows up as
      // a capacity problem rather than a compliance one.
      out.push({
        severity: "blocksDeletion",
        messageKey: "slcPolicyCountNotACap",
        values: { count: intent.count },
      });

      out.push({ severity: "irreversible", messageKey: "slcSnapshotExtendOnly" });

      // The policy itself is reversible, which is the useful half of the news:
      // it bounds the damage to snapshots already taken.
      out.push({ severity: "info", messageKey: "slcPolicyStoppable" });
      break;
    }

    case "s3ObjectLock": {
      if (intent.mode === "COMPLIANCE") {
        out.push({ severity: "irreversible", messageKey: "slcS3ComplianceNoChange" });
      } else {
        out.push({ severity: "info", messageKey: "slcS3GovernanceBypass" });
      }
      if (until) {
        out.push({
          severity: "blocksDeletion",
          messageKey: "slcS3ObjectsUntil",
          values: { date: untilValue, days: intent.days },
        });
      }
      out.push({ severity: "info", messageKey: "slcS3FutureObjectsOnly" });
      break;
    }
  }

  return out;
}

/**
 * How firmly to ask.
 *
 * Anything with an irreversible consequence gets a typed keyword, except a
 * snapshot lock: it cannot be shortened, but it expires on its own and reaches
 * nothing but that one snapshot, so a checkbox is proportionate. Making every
 * routine lock require typing would train operators to type it without reading.
 *
 * A snapshot policy carrying retention does get the keyword, even though each
 * individual lock it creates would only warrant a checkbox. It is a standing
 * instruction rather than one act: it keeps producing locks on a schedule after
 * the operator has stopped watching. A policy with no retention has no
 * irreversible consequence and so falls through to the checkbox on its own.
 */
export function confirmationLevel(intent: SnaplockIntent): SnaplockConfirmationLevel {
  if (intent.kind === "lockSnapshot") return "acknowledge";
  const hasIrreversible = describeConsequences(intent, new Date()).some(
    (c) => c.severity === "irreversible"
  );
  return hasIrreversible ? "keyword" : "acknowledge";
}

/** Short label for the thing being changed, shown in the dialog title. */
export function intentSubject(intent: SnaplockIntent): string {
  switch (intent.kind) {
    case "createSnaplockVolume":
    case "updateSnaplockRetention":
    case "enableSnapshotLocking":
      return intent.volumeName;
    case "lockSnapshot":
      return intent.snapshotName;
    case "s3ObjectLock":
      return intent.bucket;
    case "snapshotPolicyRetention":
      return intent.policyName;
  }
}

/**
 * The word the operator types for a `keyword` confirmation.
 *
 * Not translated, and interpolated into the prompt rather than written into it,
 * so that the word asked for and the word compared against cannot drift apart
 * per locale.
 */
export const SNAPLOCK_CONFIRM_KEYWORD = "LOCK";
