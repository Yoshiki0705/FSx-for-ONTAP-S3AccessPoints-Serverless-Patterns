/**
 * AppSync APPSYNC_JS Resolver: Get presigned URL via Lambda.
 *
 * Generates a time-limited presigned URL for file preview/download
 * from FSx for ONTAP S3 Access Point.
 *
 * Presigned URLs on FSx for ONTAP S3 AP are client-side SigV4 calculations
 * that execute as standard GetObject requests. Verified working (2026-07-19).
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  var key = ctx.arguments.key;
  var expiresIn = ctx.arguments.expiresIn || 300;

  return {
    operation: "Invoke",
    payload: {
      key: key,
      expiresIn: expiresIn,
      userId: ctx.identity.username,
    },
  };
}

export function response(ctx) {
  if (ctx.error) {
    return util.error(ctx.error.message, ctx.error.type);
  }

  var result = ctx.result;
  return {
    url: result.url || null,
    expiresIn: result.expiresIn || 0,
    error: result.error || null,
  };
}
