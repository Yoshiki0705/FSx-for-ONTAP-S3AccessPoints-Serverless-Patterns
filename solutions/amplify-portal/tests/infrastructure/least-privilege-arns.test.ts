/**
 * The shape of the ARNs that replaced a bare `*` in the backend's IAM policies.
 *
 * Asserted here rather than by reading `backend.ts`, for the reason
 * `authorization-config.test.ts` gives: grepping the backend for the presence of
 * `glueReadArns(...)` would confirm the call exists and say nothing about what it returns,
 * and what it returns is the whole of the grant.
 *
 * These cannot be verified by deploying -- an over-broad grant works, and a too-narrow one
 * fails only on the request that needs the part left out. So the properties asserted are the
 * ones a wrong ARN would break: which segment holds the wildcard, and which does not.
 *
 * A literal deployment is passed in place of the CDK pseudo-parameters `backend.ts` passes.
 * Those never resolve to a literal, so asserting against them would compare
 * `{"Ref": "AWS::Region"}` -- the same shape for partition, region and account alike.
 */
import { describe, it, expect } from "vitest";
import {
  athenaWorkGroupArn,
  bucketAndObjects,
  glueAnyDatabaseArns,
  dynamoTableArn,
  glueReadArns,
  ontapSecretArn,
  s3UriBucketArns,
  type Deployment,
} from "../../amplify/least-privilege-arns";

const HERE: Deployment = {
  partition: "aws",
  region: "ap-northeast-1",
  account: "123456789012",
};

describe("the secret the ONTAP-facing functions read", () => {
  it("ends in a wildcard, for the six characters Secrets Manager appends", () => {
    expect(ontapSecretArn("ontap/admin", HERE)).toBe(
      "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap/admin-*"
    );
  });

  it("does not match a differently named secret sharing the prefix", () => {
    // `ontap/admin-*` matching `ontap/admin2` would make the narrowing decorative. The
    // separator is part of the literal, so it does not.
    const arn = ontapSecretArn("ontap/admin", HERE);
    expect(arn).toContain(":secret:ontap/admin-");
    expect(arn.endsWith("-*")).toBe(true);
  });

  it("returns a configured full ARN unchanged", () => {
    // An operator who gave an exact ARN has already been exact; appending `-*` to it would
    // produce an ARN that matches no secret at all.
    // A different Region and a real Secrets Manager suffix, so an ARN that came back
    // rebuilt rather than untouched would not match.
    const exact = "arn:aws:secretsmanager:us-east-1:123456789012:secret:some/secret-AbCdEf";
    expect(ontapSecretArn(exact, HERE)).toBe(exact);
  });

  it("falls back to every secret when unset, not to one that cannot exist", () => {
    // `portal-config.example.ts` ships this empty. Interpolating it would give
    // `secret:-*`, which matches only names beginning with a hyphen -- so ONTAP calls would
    // fail as though the role were wrong, when nothing is configured.
    for (const unset of ["", "   "]) {
      expect(ontapSecretArn(unset, HERE)).toBe(
        "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:*"
      );
    }
  });

  it("stays inside Secrets Manager, this account and this Region even when unset", () => {
    // The fallback is a wildcard within one service, not the bare `*` it replaced.
    const arn = ontapSecretArn("", HERE);
    expect(arn).toContain(":secretsmanager:ap-northeast-1:123456789012:");
    expect(arn).not.toBe("*");
  });

  it("builds in the partition it is given, not a hardcoded `aws`", () => {
    expect(ontapSecretArn("ontap/admin", { ...HERE, partition: "aws-us-gov" })).toContain(
      "arn:aws-us-gov:secretsmanager:"
    );
  });
});

describe("the Athena workgroup", () => {
  it("names the configured workgroup and nothing else", () => {
    expect(athenaWorkGroupArn("primary", HERE)).toBe(
      "arn:aws:athena:ap-northeast-1:123456789012:workgroup/primary"
    );
  });

  it("carries no wildcard", () => {
    // The workgroup is fixed at deploy time and read from the environment by the handler,
    // so there is nothing here that has to be left open.
    expect(athenaWorkGroupArn("primary", HERE)).not.toContain("*");
  });
});

describe("reading one known Glue table", () => {
  it("grants the catalog, the database and the table, because Glue checks all three", () => {
    expect(glueReadArns("cloudtrail_logs", HERE, "cloudtrail_s3_events")).toEqual([
      "arn:aws:glue:ap-northeast-1:123456789012:catalog",
      "arn:aws:glue:ap-northeast-1:123456789012:database/cloudtrail_logs",
      "arn:aws:glue:ap-northeast-1:123456789012:table/cloudtrail_logs/cloudtrail_s3_events",
    ]);
  });

  it("wildcards the table only when the caller does not name one", () => {
    const arns = glueReadArns("cloudtrail_logs", HERE);
    expect(arns[2]).toBe("arn:aws:glue:ap-northeast-1:123456789012:table/cloudtrail_logs/*");
    // The database stays named either way -- that is the half of the scope that holds.
    expect(arns[1]).not.toContain("*");
  });
});

describe("browsing every Glue database", () => {
  it("wildcards the database, because the request names it", () => {
    expect(glueAnyDatabaseArns(HERE)).toEqual([
      "arn:aws:glue:ap-northeast-1:123456789012:catalog",
      "arn:aws:glue:ap-northeast-1:123456789012:database/*",
      "arn:aws:glue:ap-northeast-1:123456789012:table/*/*",
    ]);
  });

  it("stays bound to one account and Region, and to catalog contents", () => {
    // This is what it buys over the `*` it replaced. `glue:` also covers crawlers, jobs,
    // triggers, connections, dev endpoints and schema registries; none is granted here.
    for (const arn of glueAnyDatabaseArns(HERE)) {
      expect(arn).toContain(":ap-northeast-1:123456789012:");
      expect(arn).toMatch(/:(catalog$|database\/|table\/)/);
    }
  });
});

describe("a table the portal was pointed at", () => {
  it("names the configured table", () => {
    expect(dynamoTableArn("ai-metadata", HERE)).toBe(
      "arn:aws:dynamodb:ap-northeast-1:123456789012:table/ai-metadata"
    );
  });

  it("is undefined when unset, rather than an ARN addressing no table", () => {
    // `table/` would be denied on every read, and the denial would read as a broken grant
    // rather than as configuration nobody filled in. The caller renders undefined as `*`.
    for (const unset of ["", "  "]) {
      expect(dynamoTableArn(unset, HERE)).toBeUndefined();
    }
  });
});

describe("the bucket behind an Athena output location", () => {
  it("takes the bucket from the URI and grants the objects under it", () => {
    expect(s3UriBucketArns("s3://audit-results/portal/", HERE)).toEqual([
      "arn:aws:s3:::audit-results",
      "arn:aws:s3:::audit-results/*",
    ]);
  });

  it("does not carry the prefix into the ARN", () => {
    // Athena writes under a per-query subdirectory of the prefix, so an ARN fixed to the
    // prefix itself would refuse the results it is meant to allow.
    const arns = s3UriBucketArns("s3://audit-results/portal/", HERE)!;
    for (const arn of arns) expect(arn).not.toContain("portal");
  });

  it("is undefined for anything that is not an s3:// URI naming a bucket", () => {
    for (const bad of ["", "   ", "audit-results", "https://audit-results", "s3://", "s3:///x"]) {
      expect(s3UriBucketArns(bad, HERE), JSON.stringify(bad)).toBeUndefined();
    }
  });
});

describe("a bucket and its objects", () => {
  it("grants the bucket and the keys under it", () => {
    expect(bucketAndObjects("arn:aws:s3:::example-bucket")).toEqual([
      "arn:aws:s3:::example-bucket",
      "arn:aws:s3:::example-bucket/*",
    ]);
  });

  it("keeps the bucket entry free of the object wildcard", () => {
    // A bucket-level action is denied by an ARN carrying `/*`, and an object-level action is
    // denied by one without it. Both entries are required, and neither substitutes.
    const [bucket, objects] = bucketAndObjects("arn:aws:s3:::example-bucket");
    expect(bucket.endsWith("/*")).toBe(false);
    expect(objects).toBe(`${bucket}/*`);
  });
});
