/**
 * Frontend portal settings.
 *
 * These control UI behavior (not backend configuration).
 * Set `processingEnabled` to true once you have configured a real
 * Step Functions state machine ARN in the backend.
 *
 *
 * The values below are placeholders and this file is committed. Put the real ones
 * in `amplify/portal-config.ts`, which is gitignored.
 *
 * UPLOAD TAB (Storage Browser for S3):
 *   The Upload tab requires `region`, `accountId`, and `s3ApAlias` below.
 *   - region: Same as your FSx for ONTAP region (e.g., "ap-northeast-1")
 *   - accountId: Your AWS account ID (aws sts get-caller-identity --query Account --output text)
 *   - s3ApAlias: Same alias used in portal-config.ts (e.g., "my-ap-xxxxx-ext-s3alias")
 *   These are used client-side by Storage Browser to call S3 API directly
 *   (via Cognito Identity Pool credentials, no Lambda proxy needed).
 */
export const portalSettings = {
  /**
   * Enable the Process tab (Start Processing button).
   * Set to true AFTER configuring stateMachineArn in start-processing.js.
   * Default: false (safe-by-default — prevents confusing errors in unconfigured state)
   */
  processingEnabled: true,

  // `fileListingEnabled` used to live here. It documented a "not configured"
  // fallback for the Files tab, was hardcoded true, and was imported nowhere — so
  // neither the flag nor the fallback it described existed. The Files tab reports
  // an unconfigured backend through the listing response instead.

  /**
   * Enable AI Agent Chat and Bedrock Knowledge Base features.
   * Default: false — Bedrock KB incurs ongoing cost (OpenSearch Serverless OCU charges).
   * Admin can enable at runtime from Resource Management > AI Settings panel.
   * This compile-time flag is the FALLBACK when DynamoDB settings are unavailable.
   */
  aiAgentEnabled: false,

  /**
   * Storage Browser configuration.
   * Required for the Upload tab (Storage Browser for S3 component).
   * Set these to match your FSx for ONTAP S3 AP and account.
   */
  region: "ap-northeast-1",
  accountId: "123456789012",
  // Placeholder, like `accountId` above. This file is committed, so a real alias
  // here is published: an S3 AP alias names a live access point and belongs in
  // the gitignored `amplify/portal-config.ts` with the rest of the environment.
  s3ApAlias: "my-ap-0123456789abcdef0-ext-s3alias",
};
