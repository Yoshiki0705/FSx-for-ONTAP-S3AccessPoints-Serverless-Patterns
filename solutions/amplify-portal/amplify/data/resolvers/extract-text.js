import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      key: ctx.arguments.key,
      mode: ctx.arguments.mode || "text",
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
    text: result.text || "",
    blockCount: result.blockCount || 0,
    pageCount: result.pageCount || 0,
    error: result.error || null,
  };
}
