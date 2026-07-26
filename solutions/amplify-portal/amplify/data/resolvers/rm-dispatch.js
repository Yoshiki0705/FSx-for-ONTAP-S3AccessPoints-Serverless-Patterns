import { util } from "@aws-appsync/utils";

export function request(ctx) {
  const action = ctx.arguments.action;
  // AWSJSON scalar: params arrives as an object (already parsed by AppSync).
  // If params is somehow a string (e.g., test tool), use JSON.parse via util.
  const params = typeof ctx.arguments.params === "string"
    ? JSON.parse(ctx.arguments.params)
    : (ctx.arguments.params || {});
  return {
    operation: "Invoke",
    payload: { ...params, action, userId: ctx.identity.username },
  };
}

export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
