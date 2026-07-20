import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return { operation: "Invoke", payload: { action: "deleteSnapshot", snapshotId: ctx.arguments.snapshotId, snapshotName: ctx.arguments.snapshotName, userId: ctx.identity.username } };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
