import { util } from "@aws-appsync/utils";

export function request(ctx) {
  var executionArn = ctx.arguments.executionArn;

  return {
    method: "POST",
    resourcePath: "/",
    params: {
      headers: {
        "Content-Type": "application/x-amz-json-1.0",
        "X-Amz-Target": "AWSStepFunctions.DescribeExecution",
      },
      body: JSON.stringify({
        executionArn: executionArn,
      }),
    },
  };
}

export function response(ctx) {
  if (ctx.error) {
    return util.error(ctx.error.message, ctx.error.type);
  }

  if (ctx.result.statusCode !== 200) {
    return util.error("Failed to describe execution", "StepFunctionsError");
  }

  var body = JSON.parse(ctx.result.body);
  return {
    executionArn: body.executionArn,
    status: body.status,
    startDate: body.startDate,
    stopDate: body.stopDate || null,
    output: body.output ? JSON.parse(body.output) : null,
  };
}
