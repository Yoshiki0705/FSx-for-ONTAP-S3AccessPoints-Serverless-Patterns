import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return { operation: "Invoke", payload: { action: "deleteVolume", volumeUuid: ctx.arguments.volumeUuid, volumeName: ctx.arguments.volumeName, confirm: ctx.arguments.confirm, userId: ctx.identity.username } };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
