/**
 * AppSync APPSYNC_JS Resolver: Agent Chat generic dispatch.
 *
 * Routes agentQuery calls to the AgentChat Lambda.
 * Handles AWSJSON params parsing (may arrive as string or object).
 */
import { util } from "@aws-appsync/utils";

export function request(ctx) {
  var action = ctx.arguments.action || "";
  var params = ctx.arguments.params;

  // AWSJSON delivers params as pre-parsed object OR string depending on client
  if (typeof params === "string") {
    try {
      params = JSON.parse(params);
    } catch (e) {
      params = {};
    }
  }
  if (!params) params = {};

  return {
    operation: "Invoke",
    payload: {
      action: action,
      params: params,
      userId: ctx.identity.username || ctx.identity.sub || "anonymous",
    },
  };
}

export function response(ctx) {
  if (ctx.error) {
    return util.error(ctx.error.message, ctx.error.type);
  }
  return ctx.result;
}
