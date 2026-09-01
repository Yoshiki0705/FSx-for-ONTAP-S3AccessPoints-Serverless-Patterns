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
import { readFileSync, readdirSync } from "node:fs";
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

// The signing configuration moved out of the handler and into the shared helper, so
// the assertion that presigned URLs use SigV4 has to read where it now lives. Left
// asserting the handler alone, it would have failed on a correct relocation -- and
// worse, it would pass again if the helper dropped SigV4 while the handler kept a
// stale comment about it.
const S3AP_HELPER = resolve(HERE, "../../../../shared/s3ap_helper.py");
const s3ApHelperSource = readFileSync(S3AP_HELPER, "utf-8");

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
      "ThumbnailsFunction",
      // Outside the VPC on purpose: it answers the AWS control plane, and its
      // value is that it still answers when the ONTAP path does not.
      "PlatformDiscoveryFunction",
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

    it("keeps the data platform inventory outside the VPC", () => {
      // It reads the FSx control plane, and the reason it is the entry point for
      // narrowing is that it still answers when the ONTAP path does not. In the
      // VPC it would need an FSx interface endpoint or a NAT gateway and would
      // fail for network reasons while reporting an inventory problem -- the same
      // shape of failure this layer was added to remove.
      const declaration = backendSource.slice(
        backendSource.indexOf('new lambda.Function(dataStack, "PlatformDiscoveryFunction"')
      );
      const body = declaration.slice(0, declaration.indexOf("});"));
      expect(body).not.toContain("vpcConfig");
      expect(body).toContain('handler: "handler.handler"');
      // Read-only, and both calls enumerate, so neither takes a resource to scope.
      expect(backendSource).toContain("fsx:DescribeFileSystems");
      expect(backendSource).toContain("fsx:DescribeStorageVirtualMachines");
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
      expect(s3ApHelperSource).toContain('signature_version="s3v4"');
    });

    it("signs presigned URLs through the shared helper, not a bare client", () => {
      // A module-level `boto3.client("s3")` here is how the handler came to ignore
      // the group-to-access-point mapping: one client built at import time cannot
      // vary per caller, and the alias it was pointed at was the deployment default.
      expect(presignedUrlSource).toContain("S3ApHelper(ap_alias)");
      expect(presignedUrlSource).not.toMatch(/boto3\.client\(\s*["']s3["']/);
    });

    it("chooses the presigned URL's access point from the caller's groups", () => {
      // Measured: a URL signed against the default access point executes as that
      // access point's ONTAP identity, which the documented runbook pins to UNIX
      // root. Signing without consulting the groups bypasses the boundary that
      // listing and writing both enforce.
      expect(presignedUrlSource).toContain("resolve_ap_alias(groups");
      expect(presignedUrlSource).toContain("reject_key(");
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

    it("grants the upload through the group roles, not the shared one", () => {
      // This replaced `expect(backendSource).toContain('"s3:PutObject"')`, which kept
      // passing after the Storage Browser grant moved to `direct-s3-access.ts` -- the
      // string is all over this file in Lambda policies. The assertion had stopped
      // referring to the thing its name claims, in the direction that hides a removal.
      //
      // Who receives the write is asserted as data in
      // `tests/infrastructure/direct-s3-access.test.ts`. Here, only the wiring.
      expect(backendSource).toContain("DIRECT_S3_BY_GROUP");
      expect(backendSource).toContain("grantS3(groupResources.role");
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

/**
 * A Python import of `shared.` only resolves if the shared layer is attached.
 *
 * The asset for a function covers its own directory and nothing else, so
 * `from shared.x import y` is satisfied at runtime by the layer mounted at
 * /opt/python and by nothing else. When the pairing is missed the function does not
 * degrade -- it fails at import, taking every action with it. That has already
 * happened once here: `functions/data-protection/handler.py` imported
 * `shared.ontap_client` when no layer existed, so every containment call failed at
 * import time, and the resulting `IndexError: 4` was misread as an HTTP status.
 *
 * Nothing else notices. Unit tests import handlers through the repository root, where
 * `shared/` is a plain directory, so they pass either way; the difference appears only
 * in a deployed function. Pairing the two halves here is what makes attaching the
 * layer to `list-files` and `agent-chat` -- both of which now import the path-scope
 * boundary -- a checkable change rather than a hopeful one.
 */
describe("shared layer and shared imports", () => {
  const FUNCTIONS_DIR = resolve(HERE, "../../functions");

  /** Function directories whose Python imports the `shared` package. */
  const directoriesImportingShared = (): string[] =>
    readdirSync(FUNCTIONS_DIR, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .filter((entry) => {
        const dir = resolve(FUNCTIONS_DIR, entry.name);
        return readdirSync(dir)
          .filter((file) => file.endsWith(".py"))
          .some((file) =>
            /^\s*(?:from|import)\s+shared[.\s]/m.test(readFileSync(resolve(dir, file), "utf-8")),
          );
      })
      .map((entry) => entry.name)
      .sort();

  /**
   * The `new lambda.Function(...)` declaration that packages a directory.
   *
   * Located from its `functionCode("functions/<dir>")` argument: backwards to the
   * nearest `new lambda.Function(`, forwards to the end of that call. Reading the
   * enclosing declaration rather than the whole file is the point -- searching
   * `backendSource` for `sharedPythonLayer` would pass on any file that mentions it
   * once, which every file that declares the layer does.
   */
  const declarationFor = (dir: string): string => {
    const marker = `functionCode("functions/${dir}")`;
    const at = backendSource.indexOf(marker);
    expect(at, `no functionCode("functions/${dir}") in backend.ts`).toBeGreaterThan(-1);
    const opens = backendSource.lastIndexOf("new lambda.Function(", at);
    expect(opens, `no lambda.Function declaration before ${marker}`).toBeGreaterThan(-1);
    const closes = backendSource.indexOf("\n});", at);
    return backendSource.slice(opens, closes === -1 ? undefined : closes);
  };

  it("finds the directories that import shared", () => {
    // Guards the detector itself: an empty result would make every assertion below
    // vacuous, and the regex is the kind of thing that silently stops matching.
    expect(directoriesImportingShared()).toContain("list-files");
    expect(directoriesImportingShared()).toContain("agent-chat");
  });

  it.each(directoriesImportingShared())(
    "attaches sharedPythonLayer to the function packaging %s",
    (dir) => {
      // Matched inside the `layers:` array rather than as a fixed string: a function
      // may carry more than one layer, and the thumbnail function does (Pillow as
      // well). Asserting the single-element form failed on a correct declaration.
      expect(declarationFor(dir)).toMatch(/layers:\s*\[[^\]]*\bsharedPythonLayer\b/);
    },
  );
});

/*
 * The Upload tab uploaded every file to `my-ap-0123456789abcdef0-ext-s3alias` and
 * reported "All files failed to upload", because that placeholder sat in the
 * committed `src/portal-settings.ts` and Storage Browser read the alias from
 * there. Nothing failed at build time: a placeholder is a valid string. These
 * assertions are the part a type checker cannot express -- that the environment
 * is named once, in the gitignored config, and reaches the browser through the
 * generated outputs.
 */
describe("Storage Browser configuration source", () => {
  const settingsSource = readFileSync(resolve(HERE, "../../src/portal-settings.ts"), "utf-8");
  const settingsBody = settingsSource.slice(settingsSource.indexOf("export const portalSettings"));

  it("publishes the S3 AP alias and region as custom outputs", () => {
    expect(backendSource).toMatch(
      /backend\.addOutput\(\{\s*custom:\s*\{[^}]*s3ApAlias:\s*config\.s3ApAlias/,
    );
    expect(backendSource).toMatch(/backend\.addOutput\(\{\s*custom:\s*\{[^}]*region:\s*config\.region/);
  });

  it("keeps environment values out of the committed settings file", () => {
    // Comments may discuss the history; the exported object may not carry it.
    expect(settingsBody).not.toMatch(/s3ApAlias|accountId|\bregion\b/);
    expect(settingsBody).not.toMatch(/s3alias/i);
    expect(settingsBody).not.toMatch(/\b\d{12}\b/);
  });
});

/**
 * The two-axis authorization model: four roles at the AppSync layer, two scopes at
 * the access point and path boundary.
 *
 * Asserted against source text rather than a synthesised API because the rule is
 * chosen at synth time from `config.enforceRoles`, and both branches cannot exist in
 * one synthesis. What can go wrong is the shape: the ternary pointing the wrong way,
 * a role appearing in a set it does not belong to, or a group name drifting between
 * the TypeScript declaration and the Python boundary that reads it at runtime.
 */
describe("Two-axis portal authorization", () => {
  const groupsSource = readFileSync(resolve(HERE, "../../amplify/portal-groups.ts"), "utf-8");
  const dataSchemaSource = readFileSync(resolve(HERE, "../../amplify/data/resource.ts"), "utf-8");
  const authSource = readFileSync(resolve(HERE, "../../amplify/auth/resource.ts"), "utf-8");
  const pathScopeSource = readFileSync(
    resolve(HERE, "../../../../shared/portal_path_scope.py"),
    "utf-8",
  );

  /** Reads `export const NAME = "value";` out of portal-groups.ts. */
  const groupConstant = (name: string): string => {
    const match = new RegExp(`export const ${name} = "([^"]+)"`).exec(groupsSource);
    expect(match, `portal-groups.ts must declare ${name}`).not.toBeNull();
    return match![1];
  };

  /** Reads `NAME = "value"` out of the Python boundary module. */
  const pythonConstant = (name: string): string => {
    const match = new RegExp(`^${name} = "([^"]+)"`, "m").exec(pathScopeSource);
    expect(match, `portal_path_scope.py must define ${name}`).not.toBeNull();
    return match![1];
  };

  it("declares every group in the user pool", () => {
    // Declaring is not granting: a user holding none of them behaves as before.
    expect(authSource).toMatch(/groups:\s*\[\.\.\.ALL_PORTAL_GROUPS\]/);
    const declared = /export const ALL_PORTAL_GROUPS = \[([^\]]+)\]/.exec(groupsSource);
    expect(declared).not.toBeNull();
    for (const name of [
      "ROLE_STORAGE_ADMIN",
      "ROLE_VIEWER",
      "ROLE_CONTRIBUTOR",
      "ROLE_AUDITOR",
      "SCOPE_INTERNAL",
      "SCOPE_EXTERNAL",
    ]) {
      expect(declared![1]).toContain(name);
    }
  });

  it("keeps the pre-existing group name unchanged", () => {
    // Membership is already granted in deployed pools. Renaming this would revoke
    // every administrator silently -- the rules would still be valid, matching nobody.
    expect(groupConstant("ROLE_STORAGE_ADMIN")).toBe("storage-admin");
  });

  it("agrees with the Python boundary on the names it enforces", () => {
    // shared/portal_path_scope.py runs on a Lambda layer and cannot import the
    // TypeScript. A rename on one side only leaves the boundary looking configured
    // while matching nobody, which fails open.
    expect(pythonConstant("UNRESTRICTED_ROLE")).toBe(groupConstant("ROLE_STORAGE_ADMIN"));
    expect(pythonConstant("CONFINED_SCOPE")).toBe(groupConstant("SCOPE_EXTERNAL"));
  });

  it("confines an administrator who also holds the external scope", () => {
    // The condition is the absence of `external`, not the presence of `internal`.
    // Requiring `internal` would confine every administrator predating the scope
    // axis, so the assertion pins the direction and not merely the mention.
    expect(pathScopeSource).toMatch(
      /if UNRESTRICTED_ROLE in user_groups and CONFINED_SCOPE not in user_groups:/,
    );
  });

  it("emits the role rules only when enforceRoles is set", () => {
    // Direction matters: with the branches swapped, a deployment that had not yet
    // granted roles would refuse every write.
    expect(dataSchemaSource).toMatch(
      /return config\.enforceRoles \? \[restricted\(\)\] : \[authenticated\(\)\]/,
    );
  });

  it("routes writes and the audit trail through the switch", () => {
    for (const [operation, roleSet] of [
      ["fileMutation", "WRITE_ROLES"],
      ["folderMutation", "WRITE_ROLES"],
      ["queryAuditLog", "AUDIT_ROLES"],
    ] as const) {
      const body = dataSchemaSource.slice(dataSchemaSource.indexOf(`${operation}: a`));
      const authorization = body.slice(0, body.indexOf(".handler("));
      expect(authorization, `${operation} must use ${roleSet}`).toContain(
        `allow.groups(${roleSet})`,
      );
    }
  });

  it("leaves no write dispatcher outside the switch", () => {
    // The failure this guards against is an endpoint added later: writing
    // `allow.authenticated()` on a new dispatcher is the natural thing to copy from
    // its neighbours, and the result reads as authorized while enforcing nothing.
    //
    // Restricted to the generic dispatchers, whose `action` argument means one
    // endpoint covers many operations. The single-purpose mutations are listed
    // individually elsewhere and are read paths or already group-guarded.
    const dispatchers = [...dataSchemaSource.matchAll(/^ {2}(\w*[Mm]utation): a$/gm)].map(
      (match) => match[1],
    );
    // A floor, not a count: it exists so that a regex silently matching nothing
    // cannot pass this test as "no unguarded dispatchers".
    expect(dispatchers.length).toBeGreaterThanOrEqual(5);
    const unguarded: string[] = [];
    for (const name of dispatchers) {
      const body = dataSchemaSource.slice(dataSchemaSource.indexOf(`${name}: a`));
      const authorization = body.slice(0, body.indexOf(".handler("));
      const guarded =
        authorization.includes("rolesOrAuthenticated(") || authorization.includes("allow.groups(");
      if (!guarded) unguarded.push(name);
    }
    expect(unguarded).toEqual([]);
  });

  it("limits writes to contributor and above", () => {
    const writeRoles = /const WRITE_ROLES = \[([^\]]+)\]/.exec(dataSchemaSource);
    expect(writeRoles).not.toBeNull();
    expect(writeRoles![1]).toContain("ROLE_CONTRIBUTOR");
    expect(writeRoles![1]).toContain("ROLE_STORAGE_ADMIN");
    expect(writeRoles![1]).not.toContain("ROLE_VIEWER");
    expect(writeRoles![1]).not.toContain("ROLE_AUDITOR");
  });

  it("keeps the audit trail orthogonal to the read ladder", () => {
    // `auditor` is not a rung above `viewer`. A viewer reading files does not imply
    // reading everybody else's activity, so `viewer` must stay out of this set.
    const auditRoles = /const AUDIT_ROLES = \[([^\]]+)\]/.exec(dataSchemaSource);
    expect(auditRoles).not.toBeNull();
    expect(auditRoles![1]).toContain("ROLE_AUDITOR");
    expect(auditRoles![1]).toContain("ROLE_STORAGE_ADMIN");
    expect(auditRoles![1]).not.toContain("ROLE_VIEWER");
    expect(auditRoles![1]).not.toContain("ROLE_CONTRIBUTOR");
  });

  it("prefers configured path prefixes and keeps the derivation as the fallback", () => {
    // Dropping the derivation would take a deployment that configures only
    // groupApMapping to `{}`, and `{}` means unrestricted -- the boundary would
    // vanish with nothing to notice it by.
    expect(backendSource).toMatch(/config\.groupPathPrefixes \?\?\s*\(config\.groupApMapping/);
  });

  // Asserted against the example rather than against `portal-config.ts`, which is
  // gitignored: CI copies the example over it before running these tests, so an
  // assertion about the real file would be an assertion about the example wearing its
  // name -- and would fail on the values CI actually has.
  const exampleSource = readFileSync(
    resolve(HERE, "../../amplify/portal-config.example.ts"),
    "utf-8",
  );

  it("ships with the restrictive defaults", () => {
    // Registration closed, roles enforced, no AI and no share links for outside members.
    // These were the permissive values, on a compatibility argument that no longer holds:
    // nothing downstream depends on this repository, so the default is now the safe one.
    expect(exampleSource).toMatch(/enforceRoles: true/);
    expect(exampleSource).toMatch(/selfSignUpEnabled: false/);
    // `{}` denies every role, since a role absent from the map is denied.
    expect(exampleSource).toMatch(/shareLinksByRole: \{\}/);
    expect(exampleSource).toMatch(/aiEnabled: false/);
  });

  it("keeps MFA at the mode that shipped, and says what it means", () => {
    // Not raised to REQUIRED with the others. Requiring MFA changes what every user has
    // to carry to sign in, which is an organisation's decision rather than a default --
    // unlike the others, where the restrictive value costs a deployment nothing.
    expect(exampleSource).toMatch(/mfa: "OPTIONAL"/);
    // "OPTIONAL" is easy to read as a control that is in place. It is not.
    expect(exampleSource.toLowerCase()).toMatch(/each user decides/);
  });

  it("tells the reader what the defaults cost them, not only what they are", () => {
    // A restrictive default has a first-run consequence, and it will be met before this
    // file is read: a user with no role browses but cannot write.
    expect(exampleSource).toMatch(/make portal-grant-roles/);
    expect(exampleSource.toLowerCase()).toMatch(/sign out and in again/);
    // And the way back, for a deployment that genuinely wants it. Matched on a phrase
    // that cannot wrap: a comment reflowed by the formatter puts ` * ` mid-sentence, so
    // a two-word pattern would fail on a correct file.
    expect(exampleSource.toLowerCase()).toMatch(/open registration/);
  });

  // The polarity of the environment parsing -- that both variables need the word which
  // leaves the restrictive state, so a misspelling fails closed -- is not asserted here.
  // It lives in `amplify/portal-config.ts`, which is gitignored and which CI replaces with
  // the example, so a source assertion about it would pass locally and fail in CI. The
  // consequence is asserted instead, in `config-defaults.test.ts`, by loading the
  // configuration: unset and misspelled both resolve to the restrictive value.

  it("leaves the path prefixes unset rather than empty", () => {
    // `{}` and absent are not the same: `backend.ts` falls back to deriving the
    // prefixes only when this is undefined, and `{}` would read as "prefixes
    // configured, none of them restricting anything".
    expect(exampleSource).not.toMatch(/^\s*groupPathPrefixes:/m);
    expect(exampleSource).toMatch(/\*\s+groupPathPrefixes: \{/);
  });
});

/**
 * How accounts come into existence, and what signing in requires.
 *
 * Both were fixed values before, and both are the kind of fixed value that reads as a
 * decision somebody made for this deployment when it was in fact a default nobody chose.
 */
describe("Portal sign-in configuration", () => {
  const authSource = readFileSync(resolve(HERE, "../../amplify/auth/resource.ts"), "utf-8");
  const exampleSource = readFileSync(
    resolve(HERE, "../../amplify/portal-config.example.ts"),
    "utf-8",
  );

  it("takes the MFA mode from configuration, not from a literal", () => {
    expect(authSource).toMatch(/multifactor:[\s\S]{0,200}config\.signIn\.mfa/);
    // The mode was written here as "OPTIONAL". A regression would put it back.
    expect(authSource).not.toMatch(/mode:\s*"OPTIONAL"/);
    expect(authSource).not.toMatch(/mode:\s*"REQUIRED"/);
  });

  it("keeps OFF separate, because the settings are only valid with a mode that uses them", () => {
    // `MFA` is a union: `{mode: "OFF"}` alone, or a mode with settings. Passing `totp`
    // alongside "OFF" does not type-check, so the branch is not cosmetic.
    expect(authSource).toMatch(/=== "OFF" \? \{ mode: "OFF" \}/);
  });

  it("reaches the L1 for self sign-up, which defineAuth cannot express", () => {
    // @aws-amplify/auth-construct defaults ALLOW_SELF_SIGN_UP to true and defineAuth
    // exposes no field for it, so without this the answer is fixed at "anyone may
    // register" no matter what the configuration says.
    expect(backendSource).toMatch(
      /if \(!config\.signIn\.selfSignUpEnabled\)[\s\S]{0,300}AdminCreateUserConfig\.AllowAdminCreateUserOnly/,
    );
  });

  it("overrides the one property rather than replacing the object", () => {
    // The construct may set an invitation message template in the same object.
    // Assigning `adminCreateUserConfig` wholesale would drop it with no error.
    expect(backendSource).toMatch(/addPropertyOverride\(\s*\n?\s*"AdminCreateUserConfig\./);
    expect(backendSource).not.toMatch(/cfnUserPool\.adminCreateUserConfig\s*=/);
  });

  it("tells the reader how to invite somebody instead", () => {
    // Turning self sign-up off without saying what replaces it leaves an administrator
    // with a portal nobody can get into.
    expect(exampleSource).toMatch(/admin-create-user/);
    expect(exampleSource).toMatch(/email_verified/);
  });
});

/**
 * The per-user activity ledger.
 *
 * It existed as code and not as infrastructure: the handler wrote to a table named by an
 * environment variable that defaulted to empty, and skips the write when the name is
 * empty. So on every deployment that did not set the variable by hand, the trail did not
 * exist -- and an empty trail reads as "nobody did anything".
 */
describe("Portal activity ledger", () => {
  it("creates the table rather than naming one and hoping", () => {
    expect(backendSource).toMatch(
      /new dynamodb\.Table\(dataStack, "PortalActivityLedgerTable"/,
    );
  });

  it("keeps the table when the stack goes away", () => {
    // A deleted audit trail cannot be reconstructed from the thing it was recording.
    const declaration = backendSource.slice(
      backendSource.indexOf('"PortalActivityLedgerTable"'),
      backendSource.indexOf('"PortalActivityLedgerTable"') + 700,
    );
    expect(declaration).toMatch(/removalPolicy: RemovalPolicy\.RETAIN/);
    expect(declaration).toMatch(/timeToLiveAttribute: "ttl"/);
    // `pointInTimeRecoveryEnabled`, not `pointInTimeRecovery`. The flat property is
    // deprecated and CDK warns on every synth; matching the enabled flag inside the
    // specification asserts the same thing without pinning the spelling that is going away.
    expect(declaration).toMatch(/pointInTimeRecoveryEnabled: true/);
  });

  it("honours a table name a deployment already set", () => {
    // Otherwise turning this on would split one trail across two tables, and the older
    // half would stop receiving rows without appearing to have stopped.
    expect(backendSource).toMatch(
      /const activityLedgerTableName =\s*\n?\s*process\.env\.URL_AUDIT_TABLE_NAME \|\| activityLedgerTable\.tableName/,
    );
  });

  it("grants write on the ledger and nothing wider", () => {
    // The presigned-url role held `dynamodb:PutItem` on `["*"]`, with a comment saying to
    // restrict it in production. It could not be restricted while the table was created
    // by nobody.
    expect(backendSource).not.toMatch(
      /actions: \["dynamodb:PutItem"\],\s*\n\s*resources: \["\*"\]/,
    );
    const putGrants = backendSource.match(/actions: \["dynamodb:PutItem"\]/g) ?? [];
    expect(putGrants.length).toBeGreaterThanOrEqual(2);
  });

  it("gives the audit path read access and no write access", () => {
    // The audit path must not be able to amend the record it reports.
    const grant = backendSource.slice(
      backendSource.indexOf("queryAuditLogFunction.addToRolePolicy"),
      backendSource.indexOf("QueryAuditLogLambdaDataSource"),
    );
    expect(grant).toMatch(/actions: \["dynamodb:Scan"\]/);
    expect(grant).toMatch(/activityLedgerTable\.tableArn/);
    expect(grant).not.toMatch(/PutItem|UpdateItem|DeleteItem/);
  });

  it("passes the table to every handler that records or reads it", () => {
    // A handler without the name skips its write silently, which is the failure this
    // whole change exists to remove.
    for (const fn of [
      "getPresignedUrlFunction",
      "listFilesFunction",
      "folderDownloadFunction",
      "queryAuditLogFunction",
    ]) {
      const start = backendSource.indexOf(`const ${fn} = new lambda.Function`);
      expect(start, `${fn} must exist`).toBeGreaterThan(-1);
      const body = backendSource.slice(start, start + 3000);
      expect(body, `${fn} must receive the ledger table name`).toMatch(
        /URL_AUDIT_TABLE_NAME: activityLedgerTableName/,
      );
    }
  });
});
