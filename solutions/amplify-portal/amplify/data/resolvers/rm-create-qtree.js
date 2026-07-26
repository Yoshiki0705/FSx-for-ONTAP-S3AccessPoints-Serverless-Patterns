import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return { operation: "Invoke", payload: { action: "createQtree", volumeName: ctx.arguments.volumeName, name: ctx.arguments.name, securityStyle: ctx.arguments.securityStyle || "unix", exportPolicy: ctx.arguments.exportPolicy || "default", svm: ctx.arguments.svm || "", userId: ctx.identity.username } };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
