/**
 * AppSync APPSYNC_JS Resolver: Create upload link for external file request (UX-7).
 *
 * Generates a PutObject Presigned URL that external users can use to
 * upload files without authentication. Useful for receiving files from
 * partners, vendors, or clients.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "createUploadLink",
      destinationPrefix: ctx.arguments.destinationPrefix,
      fileName: ctx.arguments.fileName,
      expiresIn: ctx.arguments.expiresIn || 3600,
      maxSizeBytes: ctx.arguments.maxSizeBytes || 104857600,
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
