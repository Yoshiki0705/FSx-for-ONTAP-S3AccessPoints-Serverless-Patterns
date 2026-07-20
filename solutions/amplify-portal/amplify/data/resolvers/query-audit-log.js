/**
 * AppSync APPSYNC_JS Resolver: Query audit trail via Lambda (Athena over CloudTrail).
 *
 * Invokes the QueryAuditLog Lambda which runs Athena queries against
 * CloudTrail S3 data events to surface "who accessed which file, when"
 * for compliance officers.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "queryAuditLog",
      fileKeyPrefix: ctx.arguments.fileKeyPrefix || "",
      startDate: ctx.arguments.startDate || "",
      endDate: ctx.arguments.endDate || "",
      eventType: ctx.arguments.eventType || "ALL",
      maxResults: ctx.arguments.maxResults || 50,
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
    events: result.events || [],
    queryExecutionId: result.queryExecutionId || "",
    error: result.error || null,
  };
}
