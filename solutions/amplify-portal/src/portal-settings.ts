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
   * Set to false if stateMachineArn in start-processing.js is still "placeholder".
   */
  processingEnabled: true,

  /**
   * Enable the Files tab (S3 AP file listing).
   * Set to false if S3_AP_ALIAS Lambda env var is empty.
   */
  fileListingEnabled: true,
};
