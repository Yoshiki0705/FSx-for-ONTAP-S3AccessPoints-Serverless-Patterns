/**
 * AppSync resolver for toolsQuery (functions/file-tools).
 *
 * writeOperation and useCaseOperation are set here, after the client's params, so a
 * client cannot set them. The folder writes (generateImage, saveResult) need
 * toolsMutation, limited to the write roles when roles are enforced. The use-case
 * writes (saveUseCase, deleteUseCase) need toolsUseCaseMutation, limited to the portal
 * roles. toolsQuery sets both to false.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  const params = typeof ctx.arguments.params === "string"
    ? JSON.parse(ctx.arguments.params)
    : (ctx.arguments.params || {});
  const groups = ctx.identity.claims ? ctx.identity.claims["cognito:groups"] || [] : [];
  return {
    operation: "Invoke",
    payload: { ...params, action: ctx.arguments.action, userId: ctx.identity.username, groups, writeOperation: false, useCaseOperation: false },
  };
}

export function response(ctx) {
  if (ctx.error) return util.error(ctx.error.message, ctx.error.type);
  return ctx.result;
}
