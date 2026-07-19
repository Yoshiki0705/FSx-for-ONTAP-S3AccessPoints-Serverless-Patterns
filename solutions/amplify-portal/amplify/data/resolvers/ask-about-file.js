/**
 * AppSync APPSYNC_JS Resolver: Ask about a file using Bedrock.
 *
 * Reads file content from FSx for ONTAP S3 AP, sends to Bedrock with
 * the user's question, and returns the AI-generated answer.
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  var key = ctx.arguments.key;
  var question = ctx.arguments.question;

  return {
    operation: "Invoke",
    payload: {
      key: key,
      question: question,
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
    answer: result.answer || "",
    model: result.model || "",
    error: result.error || null,
  };
}
