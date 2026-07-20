/**
 * AppSync APPSYNC_JS Resolver: List volume snapshots via Lambda (ONTAP REST API).
 *
 * Invokes the ListSnapshots Lambda which calls ONTAP REST API to retrieve
 * available snapshots for the configured volume. This enables the
 * "Version History" feature — users can browse past file states.
 *
 * Note: This Lambda runs inside VPC (access to ONTAP management LIF).
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "listSnapshots",
      maxResults: ctx.arguments.maxResults || 10,
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
    snapshots: result.snapshots || [],
    volumeName: result.volumeName || "",
    error: result.error || null,
  };
}
