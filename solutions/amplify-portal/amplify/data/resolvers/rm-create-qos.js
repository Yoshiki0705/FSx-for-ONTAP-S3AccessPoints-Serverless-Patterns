import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return { operation: "Invoke", payload: { action: "createQosPolicy", name: ctx.arguments.name, policyType: ctx.arguments.policyType, maxIops: ctx.arguments.maxIops, maxMbps: ctx.arguments.maxMbps, expectedIops: ctx.arguments.expectedIops, peakIops: ctx.arguments.peakIops, svm: ctx.arguments.svm || "", userId: ctx.identity.username } };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
