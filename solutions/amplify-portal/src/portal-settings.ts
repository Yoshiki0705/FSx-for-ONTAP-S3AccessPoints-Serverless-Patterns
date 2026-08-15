/**
 * Frontend portal settings.
 *
 * These are feature switches for the UI, and nothing here describes an
 * environment. This file is committed, so anything environment-specific would
 * ship as a placeholder and the placeholder would be what runs -- which is what
 * happened to the Upload tab while `region`, `accountId` and `s3ApAlias` lived
 * here. Those moved out: `amplify/portal-config.ts` (gitignored) holds them, and
 * `amplify/backend.ts` publishes what the browser needs into
 * `amplify_outputs.json`, read by `src/lib/portalOutputs.ts`. `accountId` was
 * read by nothing at all and is gone.
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
};
