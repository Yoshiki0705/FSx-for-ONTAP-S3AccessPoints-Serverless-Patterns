/**
 * AppSync APPSYNC_JS Resolver: Get AI processing metadata for files.
 *
 * Invokes Lambda to batch-fetch AI metadata (classification labels,
 * Rekognition labels, entity counts, etc.) from DynamoDB for a set of
 * file keys. Used by FileExplorer to show inline badges.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "getFileMetadata",
      fileKeys: ctx.arguments.fileKeys,
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
    metadata: result.metadata || [],
    error: result.error || null,
  };
}
