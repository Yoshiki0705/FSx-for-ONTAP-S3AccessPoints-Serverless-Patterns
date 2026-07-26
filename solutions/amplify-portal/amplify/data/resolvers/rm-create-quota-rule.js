import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return { operation: "Invoke", payload: { action: "createQuotaRule", volumeName: ctx.arguments.volumeName, type: ctx.arguments.type, qtreeName: ctx.arguments.qtreeName || "", userName: ctx.arguments.userName || "", groupName: ctx.arguments.groupName || "", spaceHardLimitGiB: ctx.arguments.spaceHardLimitGiB || 0, spaceSoftLimitGiB: ctx.arguments.spaceSoftLimitGiB || 0, filesHardLimit: ctx.arguments.filesHardLimit || 0, svm: ctx.arguments.svm || "", userId: ctx.identity.username } };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
