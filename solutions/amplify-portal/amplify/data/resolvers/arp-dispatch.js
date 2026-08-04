import { util } from "@aws-appsync/utils";

export function request(ctx) {
  const action = ctx.arguments.action;
  const params = typeof ctx.arguments.params === "string"
    ? JSON.parse(ctx.arguments.params)
    : (ctx.arguments.params || {});

  // The identity fields come after the spread so they win over anything the
  // caller put in params. `actor` is nulled rather than left alone because the
  // handler used to fall back to it and no resolver ever cleared it.
  //
  // A version of this filtered the keys out of params with Object.keys and a
  // loop, which reads better but the APPSYNC_JS runtime rejected it with only
  // "The code contains one or more errors" and no indication of which construct.
  // Not worth bisecting: the ordering here is what the runtime accepts, and the
  // handler does not trust these fields on their own in any case — it requires
  // invokedVia to say appsync before it attributes an action to a user.
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
