/**
 * AppSync APPSYNC_JS Resolver: Rename file (UX-9).
 *
 * S3 AP does not support native rename. Implements as CopyObject + DeleteObject.
 * Note: This requires V-2 verification (CopyObject support on S3 AP).
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "renameFile",
      sourceKey: ctx.arguments.sourceKey,
      destinationKey: ctx.arguments.destinationKey,
      userId: ctx.identity.username,
    },
  };
}

export function response(ctx) {
  if (ctx.error) {
    return util.error(ctx.error.message, ctx.error.type);
  }
  return ctx.result;
}
