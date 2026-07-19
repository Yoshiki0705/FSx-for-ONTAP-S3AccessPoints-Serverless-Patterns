import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      key: ctx.arguments.key,
      analysisType: ctx.arguments.analysisType || "entities",
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
    results: result.results || [],
    error: result.error || null,
  };
}
