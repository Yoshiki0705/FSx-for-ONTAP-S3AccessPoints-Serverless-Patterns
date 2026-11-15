/**
 * AppSync resolver for toolsQuery (functions/file-tools).
 *
 * writeOperation is set here, after the client's params, so a client cannot set it:
 * the writes (saveUseCase, deleteUseCase, generateImage, saveResult) need toolsMutation,
 * which AppSync limits to the write roles when roles are enforced.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  const params = typeof ctx.arguments.params === "string"
    ? JSON.parse(ctx.arguments.params)
    : (ctx.arguments.params || {});
  const groups = ctx.identity.claims ? ctx.identity.claims["cognito:groups"] || [] : [];
  return {
    operation: "Invoke",
    payload: { ...params, action: ctx.arguments.action, userId: ctx.identity.username, groups, writeOperation: false },
  };
}

export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
