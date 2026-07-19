/**
 * Frontend portal settings.
 *
 * These control UI behavior (not backend configuration).
 * Set `processingEnabled` to true once you have configured a real
 * Step Functions state machine ARN in the backend.
 *
 * Set `fileListingEnabled` to true once you have configured an
 * S3 AP alias or bucket in the backend Lambda environment variable.
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
};
