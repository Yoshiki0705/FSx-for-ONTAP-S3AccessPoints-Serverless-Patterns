/**
 * AppSync APPSYNC_JS Resolver: Move file to trash (UX-3).
 *
 * Instead of permanent delete, moves file to .trash/ prefix.
 * Original path is preserved in the trash key for restoration.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "trashFile",
      key: ctx.arguments.key,
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
