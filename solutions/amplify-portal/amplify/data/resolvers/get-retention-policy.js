/**
 * AppSync APPSYNC_JS Resolver: Get retention policy info (F-4).
 *
 * Invokes Lambda to query ONTAP REST API for SnapLock and Snapshot Policy
 * configuration on the volume. Displays retention status in portal UI.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "getRetentionPolicy",
      userId: ctx.identity.username,
    },
  };
}

export function response(ctx) {
  if (ctx.error) {
    return util.error(ctx.error.message, ctx.error.type);
  }

  const result = ctx.result;
  return {
    snapshotPolicy: result.snapshotPolicy || null,
    snaplock: result.snaplock || null,
    volumeName: result.volumeName || "",
    error: result.error || null,
  };
}
