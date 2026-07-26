import { util } from "@aws-appsync/utils";
export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "blockSmbUser",
      domain: ctx.arguments.domain,
      username: ctx.arguments.username,
      svm: ctx.arguments.svm || "",
      userId: ctx.identity.username,
    },
  };
}
export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
