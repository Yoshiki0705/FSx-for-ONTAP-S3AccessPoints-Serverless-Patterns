/**
 * AppSync APPSYNC_JS Resolver: Restore file from trash (UX-3).
 *
 * Copies file from .trash/ back to original path and deletes the trash copy.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "restoreFromTrash",
      trashKey: ctx.arguments.trashKey,
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
