import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return { operation: "Invoke", payload: { action: "getProtectionSummary", userId: ctx.identity.username } };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return { data: ctx.result, error: ctx.result.error || null };
}
