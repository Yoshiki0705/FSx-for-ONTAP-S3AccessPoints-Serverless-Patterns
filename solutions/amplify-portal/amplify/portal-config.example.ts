/**
 * FSx for ONTAP File Portal — Configuration Example
 *
 * SETUP:
 *   1. Copy this file:  cp portal-config.example.ts portal-config.ts
 *   2. Edit portal-config.ts with your environment values
 *   3. Edit src/portal-settings.ts for frontend settings (Upload tab, region, accountId)
 *   4. Deploy: make sandbox (or npx ampx sandbox)
 *
 * ALTERNATIVE: Set environment variables instead of editing the file:
 *   export AMPLIFY_PORTAL_REGION=ap-northeast-1
 *   export AMPLIFY_PORTAL_S3AP_ALIAS=my-s3-access-point01-abc123-s3alias
 *   export AMPLIFY_PORTAL_SFN_ARN=arn:aws:states:ap-northeast-1:123456789012:stateMachine:my-workflow
 *
 * UPLOAD TAB (Storage Browser):
 *   The Upload tab uses Storage Browser for S3, which requires frontend-side config
 *   in src/portal-settings.ts. Set region, accountId, and s3ApAlias there.
 *   The Upload tab uses Cognito Identity Pool credentials (auto-provisioned by sandbox).
 */

export interface PortalConfig {
  region: string;
  s3ApAlias: string;
  stateMachineArn: string;
  stateMachineResourceScope: string;
  s3ApResourceArns: string[];
  groupApMapping: Record<string, string>;
  bedrockKbId: string;

  // Bedrock Guardrails (PII detection/masking + content filtering)
  bedrockGuardrailId: string;
  bedrockGuardrailVersion: string;

  // VPC configuration (required for ONTAP REST API access)
  vpcId: string;
  vpcSubnetIds: string[];
  vpcSecurityGroupIds: string[];

  // ONTAP connection
  ontapMgmtIp: string;
  ontapSecretName: string;
  ontapSvmName: string;
  ontapVolumeName: string;
}

export const config: PortalConfig = {
  // ─── Required ───────────────────────────────────────────────────────────

  /** AWS Region where your FSx for ONTAP and Step Functions are deployed */
  region: "ap-northeast-1",

  /**
   * S3 Access Point alias for FSx for ONTAP volume.
   * Find this in: AWS Console → FSx → File Systems → S3 Access Points tab
   * Format: "<ap-name>-<random>-s3alias"
   *
   * For DemoMode (no FSx for ONTAP): use a regular S3 bucket name.
   * Leave empty to show "No files" in the Files tab.
   */
  s3ApAlias: "",

  /**
   * Step Functions state machine ARN.
   * Find this in: AWS Console → Step Functions → State Machines
   *
   * If you haven't deployed a UC pattern yet, create a test machine:
   *   make sfn-test-create
   * Then paste the ARN here.
   */
  stateMachineArn:
    "arn:aws:states:ap-northeast-1:123456789012:stateMachine:placeholder",

  // ─── Optional (defaults work for sandbox) ──────────────────────────────

  /**
   * IAM scope for Step Functions.
   * Sandbox: "*" (all state machines)
   * Production: restrict to specific ARN pattern
   */
  stateMachineResourceScope: "*",

  /**
   * IAM scope for S3 AP access.
   * Sandbox: all access points in all regions
   * Production: restrict to specific AP ARN
   *
   * DemoMode (regular S3 bucket): S3 AP ARNs won't work for regular buckets.
   * Add bucket ARNs explicitly:
   *   "arn:aws:s3:::your-bucket-name",
   *   "arn:aws:s3:::your-bucket-name/*",
   */
  s3ApResourceArns: [
    "arn:aws:s3:*:*:accesspoint/*",
    "arn:aws:s3:*:*:accesspoint/*/object/*",
    // DemoMode: uncomment and set your bucket name
    // "arn:aws:s3:::your-demo-bucket",
    // "arn:aws:s3:::your-demo-bucket/*",
  ],

  /**
   * Group-based S3 AP routing.
   * Maps Cognito groups to S3 AP aliases (each with a different File System Identity).
   * See interface definition above for examples.
   * Empty = disabled (all users share the default s3ApAlias).
   */
  groupApMapping: {},

  /**
   * Bedrock Knowledge Base ID.
   * Find in: AWS Console → Bedrock → Knowledge Bases → ID column
   * Leave empty to disable full-text search.
   */
  bedrockKbId: "",

  /**
   * Bedrock Guardrail ID and version for PII detection/masking.
   * Create in: AWS Console → Bedrock → Guardrails → Create guardrail
   * Leave empty to disable guardrails (AI responses unfiltered).
   *
   * Recommended configuration:
   *   - PII: ANONYMIZE for EMAIL, PHONE; BLOCK for SSN, CREDIT_CARD
   *   - Content: BLOCK SEXUAL/VIOLENCE at HIGH strength
   */
  bedrockGuardrailId: "",
  bedrockGuardrailVersion: "DRAFT",

  // ─── VPC & ONTAP (required for Admin/DataProtection/ARP features) ──────

  /**
   * VPC where FSx for ONTAP ENIs reside.
   * Find: aws fsx describe-file-systems --file-system-ids <fs-id> \
   *         --query "FileSystems[0].{VpcId:VpcId,SubnetIds:SubnetIds}"
   * Leave empty to deploy without VPC (admin panels show "ONTAP connection required").
   */
  vpcId: "",
  vpcSubnetIds: [],
  vpcSecurityGroupIds: [],

  /**
   * ONTAP management LIF IP address.
   * Find: aws fsx describe-file-systems --file-system-ids <fs-id> \
   *         --query "FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]"
   */
  ontapMgmtIp: "",

  /**
   * Secrets Manager secret containing ONTAP credentials.
   * Secret must have: {"username": "fsxadmin", "password": "..."}
   */
  ontapSecretName: "",

  /** SVM name (default SVM for operations) */
  ontapSvmName: "",

  /** Default volume name for snapshot/lock operations */
  ontapVolumeName: "",
};
