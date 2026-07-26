import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return { operation: "Invoke", payload: { action: "deleteQtree", volumeName: ctx.arguments.volumeName, qtreeId: ctx.arguments.qtreeId, confirm: ctx.arguments.confirm, svm: ctx.arguments.svm || "", userId: ctx.identity.username } };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
