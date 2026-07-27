import { util } from "@aws-appsync/utils";

export function request(ctx) {
  const action = ctx.arguments.action;
  const params = typeof ctx.arguments.params === "string"
    ? JSON.parse(ctx.arguments.params)
    : (ctx.arguments.params || {});
  // Pass user groups for KB smart routing (group-based search scope)
  const groups = (ctx.identity.groups || []);
  return {
    operation: "Invoke",
    payload: { action, params, userId: ctx.identity.username, userGroups: groups },
  };
}

export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
