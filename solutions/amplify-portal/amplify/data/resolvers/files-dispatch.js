import { util } from "@aws-appsync/utils";

export function request(ctx) {
  const action = ctx.arguments.action;
  const params = typeof ctx.arguments.params === "string"
    ? JSON.parse(ctx.arguments.params)
    : (ctx.arguments.params || {});
  const groups = ctx.identity.claims ? ctx.identity.claims["cognito:groups"] || [] : [];
  return {
    operation: "Invoke",
    payload: { ...params, action, userId: ctx.identity.username, groups },
  };
}

export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
