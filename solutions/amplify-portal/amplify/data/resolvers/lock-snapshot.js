import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "lockSnapshot",
      snapshotId: ctx.arguments.snapshotId,
      expiryTime: ctx.arguments.expiryTime,
      userId: ctx.identity.username,
    },
  };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
