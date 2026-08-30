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
  // The groups decide which access point signs the URL and which prefixes the key
  // may fall under. Without them the function has no way to tell one caller from
  // another, and every URL was signed against the deployment's default access
  // point -- which is the permissive one in the documented default configuration.
  var groups = ctx.identity.claims
    ? ctx.identity.claims["cognito:groups"] || []
    : [];

  return {
    operation: "Invoke",
    payload: {
      key: key,
      expiresIn: expiresIn,
      userId: ctx.identity.username,
      groups: groups,
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
