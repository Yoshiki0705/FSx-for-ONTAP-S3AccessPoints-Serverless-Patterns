import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return { operation: "Invoke", payload: { action: "resizeVolume", volumeUuid: ctx.arguments.volumeUuid, newSizeGiB: ctx.arguments.newSizeGiB, userId: ctx.identity.username } };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
