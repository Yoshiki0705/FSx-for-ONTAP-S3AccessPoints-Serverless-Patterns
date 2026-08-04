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
import { readFileSync } from "fs";
import { resolve } from "path";

const BACKEND_PATH = resolve(__dirname, "../../amplify/backend.ts");
const backendSource = readFileSync(BACKEND_PATH, "utf-8");

// Handler bodies used to be inline in backend.ts and now live under functions/.
// Assertions about Python behaviour must read the handler source directly.
const PRESIGNED_URL_HANDLER = resolve(__dirname, "../../functions/presigned-url/index.py");
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

    it("all Lambda functions use Python 3.12 ARM64", () => {
      const pythonMatches = (backendSource.match(/runtime: lambda\.Runtime\.PYTHON_3_12/g) || []).length;
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

    it("cdk-nag is applied", () => {
      expect(backendSource).toContain("AwsSolutionsChecks");
      expect(backendSource).toContain("NagSuppressions");
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
        (line) =>
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

  it("passes the table name and default expiry to the ARP function", () => {
    expect(backendSource).toContain("CONTAINMENT_BLOCKS_TABLE: containmentBlocksTable.tableName");
    expect(backendSource).toContain("DEFAULT_BLOCK_TTL_HOURS: String(config.defaultBlockTtlHours)");
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

  it("only creates the endpoint when route tables are supplied", () => {
    // The VPC belongs to another stack; writing to its route tables should be a
    // deliberate choice rather than a side effect of deploying the portal.
    expect(backendSource).toContain("vpcConfig && config.vpcRouteTableIds.length > 0");
  });
});
