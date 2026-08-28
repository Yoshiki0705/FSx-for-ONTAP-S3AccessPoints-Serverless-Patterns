/**
 * AppSync APPSYNC_JS Resolver: Search files via Bedrock Knowledge Base.
 *
 * Invokes the SearchFiles Lambda which calls Bedrock KB Retrieve API
 * to perform semantic search over FSx for ONTAP S3 AP content.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      // Search results are object keys, so they are filtered to the caller.
      groups: ctx.identity.claims ? ctx.identity.claims["cognito:groups"] || [] : [],
      action: "searchFiles",
      query: ctx.arguments.query,
      maxResults: ctx.arguments.maxResults || 5,
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
    results: result.results || [],
    query: result.query || "",
    error: result.error || null,
  };
}
