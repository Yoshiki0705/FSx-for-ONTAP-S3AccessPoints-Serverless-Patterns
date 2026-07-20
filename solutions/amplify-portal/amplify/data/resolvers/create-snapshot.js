import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return { operation: "Invoke", payload: { action: "createSnapshot", name: ctx.arguments.name, comment: ctx.arguments.comment || "", userId: ctx.identity.username } };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
