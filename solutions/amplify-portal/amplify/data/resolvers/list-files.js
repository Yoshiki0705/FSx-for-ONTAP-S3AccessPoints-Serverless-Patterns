/**
 * AppSync APPSYNC_JS Resolver: List files via Lambda (S3 AP).
 *
 * Invokes the ListFiles Lambda function which calls ListObjectsV2
 * on the FSx for ONTAP S3 Access Point.
 *
 * Passes user's Cognito groups to enable group-based AP routing (My Files).
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  const { prefix, maxKeys, continuationToken } = ctx.arguments;

  // Extract Cognito groups from identity claims
  // Cognito User Pool: ctx.identity.claims["cognito:groups"] is a list
  const groups = ctx.identity.claims
    ? ctx.identity.claims["cognito:groups"] || []
    : [];

  return {
    operation: "Invoke",
    payload: {
      action: "listFiles",
      prefix: prefix || "",
      maxKeys: maxKeys || 100,
      continuationToken: continuationToken || null,
      userId: ctx.identity.username,
      groups: groups,
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
