import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      key: ctx.arguments.key,
      analysisType: ctx.arguments.analysisType || "entities",
      // The boundary needs the caller's groups: they decide which access point
      // serves the request and which prefixes the key may fall under.
      groups: ctx.identity.claims ? ctx.identity.claims["cognito:groups"] || [] : [],
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
