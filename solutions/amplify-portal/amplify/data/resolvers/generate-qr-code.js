/**
 * AppSync APPSYNC_JS Resolver: Generate QR code for file access.
 *
 * Invokes Lambda to create a short-expiry Presigned URL and encode it
 * as a QR code (base64 PNG). Used by manufacturing/OT scenarios where
 * workers scan a QR code on a tablet to view associated drawings.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      action: "generateQrCode",
      key: ctx.arguments.key,
      expiresIn: ctx.arguments.expiresIn || 300,
      userId: ctx.identity.username,
    },
  };
}

export function response(ctx) {
  if (ctx.error) {
    return util.error(ctx.error.message, ctx.error.type);
  }

  const result = ctx.result;
  return {
    qrCodeBase64: result.qrCodeBase64 || "",
    presignedUrl: result.presignedUrl || "",
    expiresIn: result.expiresIn || 0,
    error: result.error || null,
  };
}
