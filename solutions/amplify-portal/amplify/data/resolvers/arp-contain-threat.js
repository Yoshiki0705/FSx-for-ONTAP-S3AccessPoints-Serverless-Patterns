import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "containThreat",
      domain: ctx.arguments.domain || null,
      username: ctx.arguments.username || null,
      clientIp: ctx.arguments.clientIp || null,
      volumeName: ctx.arguments.volumeName || null,
      policyName: ctx.arguments.policyName || "default",
      reason: ctx.arguments.reason || "portal-initiated",
      svm: "",
      userId: ctx.identity.username,
    },
  };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
