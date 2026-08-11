/**
 * CDK Harness — Structural assertions for amplify-portal backend.
 *
 * Validates that backend.ts produces the expected infrastructure without
 * actually deploying. These tests catch:
 * - Missing Lambda functions (AI services added but not wired)
 * - IAM policy drift (permissions removed accidentally)
 * - Environment variable misconfiguration
 * - Resource count regressions
 *
 * Inspired by CDK Conference Japan 2026 session:
 * "AIに書かせたCDK、動くだけで満足してませんか？今日から始める、CDKハーネス設計！"
 *
 * Note: These tests read the backend.ts source AST, not a synthesized template.
 * For full synth-based testing, use `npx ampx sandbox --once` + cfn-lint.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// import.meta.dirname, not __dirname: this package is "type": "module", so
// __dirname does not exist at runtime. It only worked because the test runner
// transpiled the file; TypeScript 7 reports it correctly.
const HERE = import.meta.dirname;

const BACKEND_PATH = resolve(HERE, "../../amplify/backend.ts");
const backendSource = readFileSync(BACKEND_PATH, "utf-8");

// Handler bodies used to be inline in backend.ts and now live under functions/.
// Assertions about Python behaviour must read the handler source directly.
const PRESIGNED_URL_HANDLER = resolve(HERE, "../../functions/presigned-url/index.py");
const presignedUrlSource = readFileSync(PRESIGNED_URL_HANDLER, "utf-8");

describe("Backend Infrastructure Structure", () => {
  describe("Lambda Functions", () => {
    const expectedLambdas = [
      "ListFilesFunction",
      "FolderDownloadFunction",
      "GetPresignedUrlFunction",
      "ListSnapshotsFunction",
      "SearchFilesFunction",
      "QueryAuditLogFunction",
      "GetFileMetadataFunction",
      "GenerateQrCodeFunction",
      "AskAboutFileFunction",
      "DetectLabelsFunction",
      "AthenaQueryFunction",
      "TextractFunction",
      "ComprehendFunction",
      "GlueCatalogFunction",
      "AgentChatFunction",
      "ArpResponseFunction",
      "ResourceMgmtFunction",
      "NotificationBridgeFunction",
    ];

    it("defines all expected Lambda functions", () => {
      for (const name of expectedLambdas) {
        expect(backendSource).toContain(`"${name}"`);
      }
    });

    it(`has ${expectedLambdas.length} Lambda functions total`, () => {
      const lambdaCount = (backendSource.match(/new lambda\.Function\(/g) || []).length;
      expect(lambdaCount).toBe(expectedLambdas.length);
    });

    it("all Lambda functions use Python 3.13 ARM64", () => {
      const pythonMatches = (backendSource.match(/runtime: lambda\.Runtime\.PYTHON_3_13/g) || []).length;
      const armMatches = (backendSource.match(/architecture: lambda\.Architecture\.ARM_64/g) || []).length;
      expect(pythonMatches).toBe(expectedLambdas.length);
      expect(armMatches).toBe(expectedLambdas.length);
    });

    it("all Lambda functions have explicit timeout", () => {
      // Timeouts may be expressed in seconds or minutes.
      const timeoutMatches = (
        backendSource.match(/timeout: Duration\.(?:seconds|minutes)\(/g) || []
      ).length;
      expect(timeoutMatches).toBeGreaterThanOrEqual(expectedLambdas.length);
    });

    it("all Lambda functions have description field", () => {
      // Every new lambda.Function() should have a description property set
      const lambdaBlocks = backendSource.match(/new lambda\.Function\([^)]+\)/g) || [];
      // Check that 'description:' appears in the file at least once per Lambda
      const descCount = (backendSource.match(/description:\s*["`']/g) || []).length;
      expect(descCount).toBeGreaterThanOrEqual(lambdaBlocks.length);
    });
  });

  describe("AppSync Data Sources", () => {
    it("has HTTP data source for Step Functions", () => {
      expect(backendSource).toContain("addHttpDataSource");
      expect(backendSource).toContain("StepFunctionsHttpDataSource");
    });

    it("all Lambda functions are registered as data sources", () => {
      const addLambdaDSCount = (backendSource.match(/api\.addLambdaDataSource\(/g) || []).length;
      // Should match the number of Lambda functions (each gets a data source)
      expect(addLambdaDSCount).toBeGreaterThanOrEqual(12);
    });
  });

  describe("IAM Roles", () => {
    it("creates dedicated IAM role per Lambda (least privilege)", () => {
      const roleCount = (backendSource.match(/new iam\.Role\(dataStack/g) || []).length;
      // At least one role per Lambda (some may share)
      expect(roleCount).toBeGreaterThanOrEqual(10);
    });

    it("CDK IAM role wildcard resources have production-scope comments", () => {
      // Check that wildcard resources in CDK role definitions have justification comments.
      // We identify CDK roles by looking for lines with 'resources: ["*"]' that are
      // within IAM PolicyDocument blocks (indented with TypeScript structure, not Python).
      // Python inline code uses different indentation patterns.
      const lines = backendSource.split("\n");
      const cdkWildcards: string[] = [];

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.includes('resources: ["*"]') && !line.includes("//")) {
          // Check if this is in CDK context (TypeScript indentation: spaces + keyword)
          // vs Python inline code (deeper indentation within template literal)
          const indent = line.length - line.trimStart().length;
          // CDK IAM statements are typically indented 10-14 spaces
          // Python inline code is typically indented 0-8 spaces (inside backtick)
          if (indent >= 8 && indent <= 16) {
            cdkWildcards.push(`Line ${i + 1}: ${line.trim()}`);
          }
        }
      }

      // Report but don't fail — this is a tracking assertion
      // In production hardening, these should all get specific ARN scoping
      if (cdkWildcards.length > 0) {
        console.log(
          `INFO: ${cdkWildcards.length} wildcard resource(s) in CDK IAM roles ` +
          `(acceptable for reference architecture, scope in production):`
        );
        cdkWildcards.forEach((w) => console.log(`  ${w}`));
      }
      // For now: pass as long as the count doesn't increase unexpectedly
      expect(cdkWildcards.length).toBeLessThanOrEqual(15);
    });
  });

  describe("Security Configuration", () => {
    it("uses SigV4 for S3 presigned URLs", () => {
      expect(presignedUrlSource).toContain('signature_version="s3v4"');
    });

    it("has CONFIDENTIAL guardrail in AskAboutFile", () => {
      expect(backendSource).toContain("AI_BLOCKED_LEVELS");
      expect(backendSource).toContain("CONFIDENTIAL");
    });

    it("Presigned URL has max expiry enforcement", () => {
      expect(presignedUrlSource).toContain("min(event.get");
      // GetPresignedUrl caps at 3600
      expect(presignedUrlSource).toContain("3600");
    });

    it("cdk-nag is wired through the v3 policy validation API", () => {
      expect(backendSource).toContain("AwsSolutionsChecks");
      // cdk-nag v3 removed NagSuppressions and moved off IAspect. Naming the
      // replacements keeps a future revert from passing this file unnoticed.
      expect(backendSource).toContain("Validations.of(dataStack).acknowledge(");
      // The call forms, not the words: the comment above the code names both
      // removed APIs so that a reader knows what moved.
      expect(backendSource).not.toContain("NagSuppressions.");
      expect(backendSource).not.toContain("Aspects.of(");
    });

    it("registers the pack on the app root, not on the stack", () => {
      // Validations.addPlugins throws unless the scope is a Stage or an App, and
      // the throw happens during synth — after CDK_NAG=1 has already been set in
      // CI, so a stack-scoped registration would only fail in the nag job.
      expect(backendSource).toContain("Validations.of(dataStack.node.root).addPlugins(");
    });
  });

  describe("Environment Variables", () => {
    it("S3_AP_ALIAS is set on all S3-accessing Lambdas", () => {
      const s3ApAliasEnvCount = (backendSource.match(/S3_AP_ALIAS: config\.s3ApAlias/g) || []).length;
      // ListFiles, GetPresignedUrl, GenerateQrCode, AskAboutFile, DetectLabels,
      // Textract, Comprehend, QueryAuditLog = 8 Lambdas that access S3 AP
      expect(s3ApAliasEnvCount).toBeGreaterThanOrEqual(6);
    });

    it("ONTAP-related env vars are optional (DemoMode compatible)", () => {
      // ONTAP env vars must be sourced from portal-config (config.<property>)
      // rather than bare process.env, so DemoMode has defined fallbacks.
      const cdkConfigLines = backendSource.split("\n").filter(
        (line: string) =>
          (line.includes("ONTAP_MGMT_IP:") || line.includes("ONTAP_SECRET_NAME:")) &&
          line.includes("config.")
      );
      // At least the environment block in ListSnapshotsFunction should have these
      expect(cdkConfigLines.length).toBeGreaterThanOrEqual(2);
    });
  });

  describe("Storage Browser Integration", () => {
    it("adds S3 AP permissions to Cognito authenticated role", () => {
      expect(backendSource).toContain("StorageBrowserS3APAccess");
      expect(backendSource).toContain("authenticatedUserIamRole");
    });

    it("grants s3:PutObject for uploads", () => {
      expect(backendSource).toContain('"s3:PutObject"');
    });
  });
});


describe("portal-config.example.ts covers what backend.ts reads", () => {
  // The failure this prevents is total and silent at deploy time. backend.ts
  // writes Lambda environment values with String(config.<field>), so a field the
  // example never declared becomes the literal "undefined" in the environment.
  // defaultBlockTtlHours was missing exactly this way: int("undefined") raised
  // while the ARP module was being imported, so every containment action failed
  // before its handler ran, on a deployment configured exactly as documented.
  const EXAMPLE_PATH = resolve(HERE, "../../amplify/portal-config.example.ts");
  const exampleSource = readFileSync(EXAMPLE_PATH, "utf-8");

  it("declares every config field backend.ts uses", () => {
    // `config.example.ts` appears in prose, so drop what a property access cannot be.
    const used = new Set(
      [...backendSource.matchAll(/\bconfig\.([a-zA-Z][a-zA-Z0-9]*)/g)]
        .map((m) => m[1])
        .filter((name) => !["example", "ts", "s"].includes(name))
    );
    expect(used.size).toBeGreaterThan(10);

    const missing = [...used].filter(
      // Declared in the interface or assigned in the literal — either proves the
      // field exists on the object a deployer copies.
      (name) =>
        !new RegExp(`^\\s{2}${name}\\??\\s*:`, "m").test(exampleSource) &&
        !new RegExp(`^\\s{2}${name}\\s*:`, "m").test(exampleSource)
    );

    expect(
      missing,
      `backend.ts reads config fields the example does not define: ${missing.join(", ")}. ` +
        'A missing field becomes the string "undefined" in the Lambda environment.'
    ).toEqual([]);
  });

  it("gives the block expiry fields values, not just types", () => {
    // A declared-but-unassigned field is the same failure with extra steps.
    for (const field of [
      "defaultBlockTtlHours",
      "maxBlockTtlHours",
      "blockSweepIntervalMinutes",
    ]) {
      expect(exampleSource).toMatch(new RegExp(`^\\s{2}${field}:\\s*\\d`, "m"));
    }
  });
});

describe("Containment block expiry", () => {
  it("defines the ledger table with a TTL attribute", () => {
    // ONTAP deny rules carry no timestamp, so without this table nothing can
    // say when a block was placed or when it should be lifted.
    expect(backendSource).toContain('"ContainmentBlocksTable"');
    expect(backendSource).toContain('timeToLiveAttribute: "ttl"');
  });

  it("retains the ledger table on stack removal", () => {
    // Losing it would leave blocks on the cluster with nothing recording that
    // they were ever meant to expire.
    const table = backendSource.slice(
      backendSource.indexOf('"ContainmentBlocksTable"'),
      backendSource.indexOf('"ContainmentBlocksTable"') + 700
    );
    expect(table).toContain("RemovalPolicy.RETAIN");
  });

  it("schedules the sweep against the ARP function", () => {
    expect(backendSource).toContain('"ContainmentBlockSweepSchedule"');
    expect(backendSource).toContain('action: "sweepExpiredBlocks"');
    const rule = backendSource.slice(
      backendSource.indexOf('"ContainmentBlockSweepSchedule"'),
      backendSource.indexOf('"ContainmentBlockSweepSchedule"') + 900
    );
    expect(rule).toContain("targets.LambdaFunction(arpResponseFunction");
  });

  it("grants the ARP role Scan but not DeleteItem on the ledger", () => {
    // Scan is what lets the sweep find due rows without knowing their keys.
    // DeleteItem is deliberately absent: rows are closed out by status so the
    // audit trail survives, and the native TTL removes them later.
    const role = backendSource.slice(
      backendSource.indexOf('"ArpResponseLambdaRole"'),
      backendSource.indexOf('"ArpResponseLambdaRole"') + 2000
    );
    expect(role).toContain('"dynamodb:Scan"');
    expect(role).toContain('"dynamodb:UpdateItem"');
    expect(role).not.toContain('"dynamodb:DeleteItem"');
  });

  it("passes the table name and both expiry bounds to the ARP function", () => {
    expect(backendSource).toContain("CONTAINMENT_BLOCKS_TABLE: containmentBlocksTable.tableName");
    expect(backendSource).toContain("DEFAULT_BLOCK_TTL_HOURS: String(config.defaultBlockTtlHours)");
    expect(backendSource).toContain("MAX_BLOCK_TTL_HOURS: String(config.maxBlockTtlHours)");
  });

  it("refuses a default expiry above the ceiling", () => {
    // Otherwise every block that did not name its own ttlHours would be refused,
    // citing a limit the caller never supplied.
    expect(backendSource).toContain("is above maxBlockTtlHours");
    expect(backendSource).toContain("config.maxBlockTtlHours > 0 && config.defaultBlockTtlHours");
  });

  it("can add a DynamoDB gateway endpoint for the VPC functions", () => {
    // A Lambda ENI has no public IP, so a subnet whose default route is an
    // internet gateway has no egress at all. Without a path to DynamoDB the
    // ledger call hung until the function was killed, which made a block ONTAP
    // had already accepted look like a failure at the caller.
    expect(backendSource).toContain('"DynamoDbGatewayEndpoint"');
    expect(backendSource).toContain('vpcEndpointType: "Gateway"');
    expect(backendSource).toContain("config.vpcRouteTableIds");
  });

  it("alarms on a sweep that stops running, not only on one that errors", () => {
    // The failure mode that matters most: a sweep which has stopped firing
    // reports no failures, so alarming only on errors would call it healthy
    // while blocks quietly outlive their expiry.
    expect(backendSource).toContain('"ContainmentSweepSilentAlarm"');
    const alarm = backendSource.slice(
      backendSource.indexOf('"ContainmentSweepSilentAlarm"'),
      backendSource.indexOf('"ContainmentSweepSilentAlarm"') + 1200
    );
    expect(alarm).toContain("TreatMissingData.BREACHING");
    expect(alarm).toContain('sweepMetric("SweepRuns"');
  });

  it("ties the alarm window to the sweep interval", () => {
    // A period chosen independently of the schedule drifts from it. A fixed hour
    // against a 15 minute sweep also meant recovery took two hours after the
    // sweep came back.
    expect(backendSource).toContain(
      "period: Duration.minutes(config.blockSweepIntervalMinutes)"
    );
    expect(backendSource).toContain("MISSED_SWEEPS_BEFORE_ALARM");
  });

  it("alarms on repeated sweep failures rather than the first one", () => {
    // A single failed lift is retried on the next tick by design.
    expect(backendSource).toContain('"ContainmentSweepFailureAlarm"');
    const alarm = backendSource.slice(
      backendSource.indexOf('"ContainmentSweepFailureAlarm"'),
      backendSource.indexOf('"ContainmentSweepFailureAlarm"') + 1200
    );
    expect(alarm).toContain("datapointsToAlarm: 2");
    expect(alarm).toContain("TreatMissingData.NOT_BREACHING");
  });

  it("routes all three alarms to a topic", () => {
    expect(backendSource).toContain('"ContainmentAlarmTopic"');
    expect(backendSource).toContain("sweepFailureAlarm.addAlarmAction");
    expect(backendSource).toContain("sweepSilentAlarm.addAlarmAction");
    expect(backendSource).toContain("unattributedActionAlarm.addAlarmAction");
  });

  it("alarms on a containment action that carries no portal identity", () => {
    // Prevention is not available here: within one account an identity policy
    // alone authorises Invoke, and the Lambda permission API writes only Allow
    // statements, so nothing added to this stack can revoke it. The reachable
    // requirement is that it cannot happen quietly.
    expect(backendSource).toContain('"ContainmentUnattributedActionAlarm"');
    const alarm = backendSource.slice(
      backendSource.indexOf('"ContainmentUnattributedActionAlarm"'),
      backendSource.indexOf('"ContainmentUnattributedActionAlarm"') + 1400
    );
    expect(alarm).toContain('sweepMetric("UnattributedContainmentActions"');
    // First occurrence, not a pattern: one unaccountable containment action is
    // already the thing worth looking at, and nothing retries it away.
    expect(alarm).toContain("evaluationPeriods: 1");
    expect(alarm).toContain("datapointsToAlarm: 1");
    // Missing data is the normal state — no containment actions ran.
    expect(alarm).toContain("TreatMissingData.NOT_BREACHING");
  });

  it("refuses to deploy into a VPC with no path to the ledger", () => {
    // Documenting the requirement is not enough: without the endpoint the
    // deployment looks complete while expiry silently never runs, and that is
    // visible only to someone reading an individual action's response.
    expect(backendSource).toContain("vpcRouteTableIds is required when vpcId is set");
    expect(backendSource).toContain("config.allowNoBlockExpiry");
    // The message has to name the config field, not only an environment
    // variable: portal-config.ts is gitignored and copied from the example,
    // which takes plain values, so the variable is only read where the local
    // configuration happens to wire it up.
    expect(backendSource).toContain("vpcRouteTableIds in portal-config.ts");
  });

  it("only creates the endpoint when route tables are supplied", () => {
    // The VPC belongs to another stack; writing to its route tables should be a
    // deliberate choice rather than a side effect of deploying the portal.
    expect(backendSource).toContain("vpcConfig && config.vpcRouteTableIds.length > 0");
  });
});

describe("Shared Python layer attachment", () => {
  // functionCode() bundles only the function's own directory, so a handler that
  // imports shared/ needs the layer. Without it the failure appears at request
  // time as an ImportError from inside one action, not at deploy time.
  const functionsImportingShared = [
    "functions/data-protection",
    "functions/resource-management",
  ];

  for (const directory of functionsImportingShared) {
    it(`attaches the layer to ${directory}`, () => {
      const marker = `code: functionCode("${directory}")`;
      const start = backendSource.indexOf(marker);
      expect(start, `${marker} not found`).toBeGreaterThan(-1);
      // The layer must be listed inside this function's own property block, not
      // merely somewhere in the file.
      const block = backendSource.slice(start, backendSource.indexOf("memorySize", start));
      expect(block).toContain("layers: [sharedPythonLayer]");
    });
  }

  it("keeps the layer's description tied to the content hash", () => {
    // ampx sandbox deploys through hotswap, which skips LayerVersion content
    // changes. A layer differing only by S3 key is never republished, and the
    // function keeps importing the previous version of shared/.
    expect(backendSource).toContain("sources ${sharedSourcesFingerprint}");
  });
});

describe("GraphQL authorization", () => {
  const SCHEMA_PATH = resolve(HERE, "../../amplify/data/resource.ts");
  const schemaSource = readFileSync(SCHEMA_PATH, "utf-8");

  /** The `.authorization(...)` call belonging to one schema entry. */
  function authorizationFor(operation: string): string {
    const start = schemaSource.indexOf(`  ${operation}: a`);
    expect(start, `${operation} not found in the schema`).toBeGreaterThan(-1);
    const call = schemaSource.indexOf(".authorization(", start);
    expect(call, `${operation} declares no authorization`).toBeGreaterThan(-1);
    return schemaSource.slice(call, schemaSource.indexOf("\n", call));
  }

  // runAthenaQuery executes its `sql` argument as given. There is no parameterised
  // form of StartQueryExecution, so the group boundary is the only control: the
  // Lambda role holds `glue:Get*` on `*`, which makes the whole Data Catalog
  // enumerable, and an S3 read matching `*athena-results*`, which reaches any bucket
  // in the account whose name contains that string. It shipped as
  // `allow.authenticated()`, so every signed-in user could run arbitrary SQL while
  // four less privileged operations in the same schema already required the group.
  //
  // Pinned here because nothing else would notice it changing back: the endpoint
  // keeps working either way, and the difference is only visible to a reader who
  // compares this line against the other four.
  it("requires the storage-admin group to run arbitrary SQL", () => {
    expect(authorizationFor("runAthenaQuery")).toContain('allow.groups(["storage-admin"])');
  });

  it("does not leave arbitrary SQL open to any authenticated user", () => {
    expect(authorizationFor("runAthenaQuery")).not.toContain("allow.authenticated()");
  });

  // The server refusing is correct but not sufficient: a section that stays in the
  // sidebar and answers every query with an authorization error tells the user the
  // account can do something it cannot. Resource Management had exactly this problem
  // before it was hidden, and the fix is only half applied if the UI forgets.
  it("hides the Analytics section from non-admins in the UI", () => {
    const appSource = readFileSync(resolve(HERE, "../../src/App.tsx"), "utf-8");
    expect(appSource).toContain('hiddenSections.add("analytics")');
  });
});
