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

  /**
   * Group-based S3 AP routing (My Files feature).
   *
   * Maps Cognito group names to S3 AP aliases with different File System Identities.
   * This enables per-team file visibility — each group only sees files accessible
   * to the UNIX UID/GID assigned to their S3 AP's File System Identity.
   *
   * Example:
   *   groupApMapping: {
   *     "engineering": "ap-eng-readonly-xxx-s3alias",   // UID 1001
   *     "legal":       "ap-legal-rw-xxx-s3alias",      // UID 1002
   *     "admin":       "ap-admin-full-xxx-s3alias",    // UID 0
   *   }
   *
   * If a user belongs to multiple groups, the first matching group (in
   * the order defined here) is used. If no group matches, falls back to
   * the default s3ApAlias above.
   *
   * Leave empty ({}) to disable group-based routing (all users see the same AP).
   */
  groupApMapping: Record<string, string>;

  /**
   * Bedrock Knowledge Base ID for full-text search (C-4).
   *
   * Create a KB with FSx for ONTAP S3 AP as the data source:
   *   AWS Console → Bedrock → Knowledge Bases → Create
   *   Data source: S3 → Bucket: <s3ApAlias>
   *
   * Leave empty to disable the Search feature.
   * See: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html
   */
  bedrockKbId: string;
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
   */
  s3ApResourceArns: [
    "arn:aws:s3:*:*:accesspoint/*",
    "arn:aws:s3:*:*:accesspoint/*/object/*",
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
};
