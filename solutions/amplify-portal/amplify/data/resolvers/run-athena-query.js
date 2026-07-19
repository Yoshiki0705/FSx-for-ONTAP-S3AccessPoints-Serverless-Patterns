import { util } from "@aws-appsync/utils";

export function request(ctx) {
  return {
    operation: "Invoke",
    payload: {
      sql: ctx.arguments.sql,
      database: ctx.arguments.database || "default",
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
    columns: result.columns || [],
    rows: result.rows || [],
    status: result.status || "UNKNOWN",
    error: result.error || null,
    executionId: result.executionId || null,
  };
}
