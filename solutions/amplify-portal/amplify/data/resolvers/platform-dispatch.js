import { util } from "@aws-appsync/utils";

/**
 * Forward a data platform inventory call.
 *
 * Same shape as the other dispatch resolvers: the identity fields come after the
 * spread so they win over anything the caller put in params, and `invokedVia`
 * says the request arrived through AppSync rather than a direct invoke.
 *
 * Written with the spread and explicit assignments rather than a loop over
 * Object.keys: the APPSYNC_JS runtime rejects the loop form with only "The code
 * contains one or more errors", naming neither the line nor the construct.
 */
export function request(ctx) {
  const action = ctx.arguments.action;
  const params =
    typeof ctx.arguments.params === "string"
      ? JSON.parse(ctx.arguments.params)
      : ctx.arguments.params || {};
  return {
    operation: "Invoke",
    payload: {
      ...params,
      action,
      actor: null,
      userId: ctx.identity.username,
      invokedVia: "appsync",
    },
  };
}

export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
