/**
 * AppSync APPSYNC_JS Resolver: Get AI service cost summary (H-3).
 *
 * Invokes Lambda to query Cost Explorer for Bedrock/Rekognition/Comprehend
 * costs over the past 30 days. Used by the admin dashboard.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "getCostSummary",
      days: ctx.arguments.days || 30,
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
    costs: result.costs || [],
    totalCost: result.totalCost || "0.00",
    currency: result.currency || "USD",
    period: result.period || "",
    error: result.error || null,
  };
}
