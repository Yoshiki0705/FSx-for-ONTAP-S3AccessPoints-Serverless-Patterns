/**
 * FSx for ONTAP File Portal — Configuration Example
 *
 * SETUP:
 *   1. Copy this file:  cp portal-config.example.ts portal-config.ts
 *   2. Edit portal-config.ts with your environment values
 *   3. Deploy: make sandbox (or npx ampx sandbox)
 *
 * ALTERNATIVE: Set environment variables instead of editing the file:
 *   export AMPLIFY_PORTAL_REGION=ap-northeast-1
 *   export AMPLIFY_PORTAL_S3AP_ALIAS=my-s3-access-point01-abc123-s3alias
 *   export AMPLIFY_PORTAL_SFN_ARN=arn:aws:states:ap-northeast-1:123456789012:stateMachine:my-workflow
 */
import type { PortalConfig } from "./portal-config";

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
};
