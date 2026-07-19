/**
 * AppSync APPSYNC_JS Resolver: Detect labels in an image using Rekognition.
 *
 * Downloads image from FSx for ONTAP S3 AP, sends to Rekognition DetectLabels,
 * returns labels with bounding boxes and confidence scores.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  var key = ctx.arguments.key;
  var maxLabels = ctx.arguments.maxLabels || 10;
  var minConfidence = ctx.arguments.minConfidence || 70.0;

  return {
    operation: "Invoke",
    payload: {
      key: key,
      maxLabels: maxLabels,
      minConfidence: minConfidence,
      userId: ctx.identity.username,
    },
  };
}

export function response(ctx) {
  if (ctx.error) {
    return util.error(ctx.error.message, ctx.error.type);
  }

  var result = ctx.result;
  return {
    labels: result.labels || [],
    error: result.error || null,
  };
}
