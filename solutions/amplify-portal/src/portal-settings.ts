/**
 * Frontend portal settings.
 *
 * These control UI behavior (not backend configuration).
 * Set `processingEnabled` to true once you have configured a real
 * Step Functions state machine ARN in the backend.
 *
 * Set `fileListingEnabled` to true once you have configured an
 * S3 AP alias or bucket in the backend Lambda environment variable.
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
  processingEnabled: false,

  /**
   * Enable the Files tab (S3 AP file listing).
   * Set to true AFTER configuring S3_AP_ALIAS Lambda env var.
   * Default: false (shows "not configured" instead of misleading "No files")
   */
  fileListingEnabled: true,

  /**
   * Storage Browser configuration.
   * Required for the Upload tab (Storage Browser for S3 component).
   * Set these to match your FSx for ONTAP S3 AP and account.
   */
  region: "ap-northeast-1",
  accountId: "123456789012",
  s3ApAlias: "",
};
