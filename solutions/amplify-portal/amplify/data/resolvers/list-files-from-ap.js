/**
 * AppSync APPSYNC_JS Resolver: List files from a specific S3 AP alias.
 *
 * Used by the SnapshotCompare component to list files from a FlexClone
 * volume's S3 AP (different from the default AP).
 *
 * The Lambda uses the apAlias parameter instead of the default S3_AP_ALIAS env var.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  const { prefix, maxKeys, apAlias } = ctx.arguments;

  return {
    operation: "Invoke",
    payload: {
      action: "listFilesFromAp",
      prefix: prefix || "",
      maxKeys: maxKeys || 500,
      apAlias: apAlias,
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
    files: result.files || [],
    nextContinuationToken: result.nextContinuationToken || null,
    isTruncated: result.isTruncated || false,
  };
}
