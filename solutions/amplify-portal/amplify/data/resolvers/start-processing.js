import { util } from "@aws-appsync/utils";

export function request(ctx) {
  const { pattern, inputPrefix, parameters } = ctx.arguments;

  const stateMachineArn =
    "arn:aws:states:ap-northeast-1:178625946981:stateMachine:amplify-portal-test-workflow";

  const input = JSON.stringify({
    inputPrefix: inputPrefix,
    parameters: parameters || {},
    triggeredBy: "amplify-portal",
    triggeredAt: util.time.nowISO8601(),
    userId: ctx.identity.username,
  });

  const executionName = "portal-" + pattern + "-" + util.time.nowEpochMilliSeconds();

  return {
    method: "POST",
    resourcePath: "/",
    params: {
      headers: {
        "Content-Type": "application/x-amz-json-1.0",
        "X-Amz-Target": "AWSStepFunctions.StartExecution",
      },
      body: JSON.stringify({
        stateMachineArn: stateMachineArn,
        input: input,
        name: executionName,
      }),
    },
  };
}

export function response(ctx) {
  if (ctx.error) {
    return util.error(ctx.error.message, ctx.error.type);
  }

  if (ctx.result.statusCode !== 200) {
    var errorBody = JSON.parse(ctx.result.body);
    return util.error(errorBody.message || "Failed to start execution", "StepFunctionsError");
  }

  var body = JSON.parse(ctx.result.body);
  return {
    executionArn: body.executionArn,
    startDate: body.startDate,
  };
}
