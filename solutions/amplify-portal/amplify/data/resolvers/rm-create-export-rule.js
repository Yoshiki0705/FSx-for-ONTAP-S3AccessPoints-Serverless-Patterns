import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return { operation: "Invoke", payload: { action: "createExportPolicyRule", policyId: ctx.arguments.policyId, clientMatch: ctx.arguments.clientMatch, roRule: ctx.arguments.roRule, rwRule: ctx.arguments.rwRule, superuser: ctx.arguments.superuser, protocols: ctx.arguments.protocols, userId: ctx.identity.username } };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
