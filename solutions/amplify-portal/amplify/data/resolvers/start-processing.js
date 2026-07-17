/**
 * AppSync HTTP Resolver: Start Step Functions execution.
 *
 * This resolver calls StartExecution on the Step Functions API directly,
 * without an intermediate Lambda function. It maps the GraphQL mutation
 * arguments to the StartExecution request format.
 *
 * Data source: StepFunctionsHttpDataSource (configured in custom stack)
 * Endpoint: https://states.<region>.amazonaws.com
 *
 * Note: `util` is an AppSync APPSYNC_JS runtime global — it is NOT
 * imported. See: https://docs.aws.amazon.com/appsync/latest/devguide/resolver-util-reference-js.html
 */
export function request(ctx) {
  const { pattern, inputPrefix, parameters } = ctx.arguments;

  // Map pattern enum to state machine ARN
  // TODO: Implement ARN mapping. Options:
  //   1. Store ARNs in DynamoDB and look up via pipeline resolver (stash)
  //   2. Use SSM Parameter Store with a before-mapping template
  //   3. Hardcode ARN for single-pattern deployments
  // For now, this uses a single ARN from the environment/stash.
  const stateMachineArn = ctx.stash.stateMachineArn || ctx.env.STATE_MACHINE_ARN;

  const input = JSON.stringify({
    inputPrefix,
    parameters: parameters || {},
    triggeredBy: "amplify-portal",
    triggeredAt: new Date().toISOString(),
    userId: ctx.identity.username,
  });

  return {
    method: "POST",
    resourcePath: "/",
    params: {
      headers: {
        "Content-Type": "application/x-amz-json-1.0",
        "X-Amz-Target": "AWSStepFunctions.StartExecution",
      },
      body: JSON.stringify({
        stateMachineArn,
        input,
        name: `portal-${pattern}-${Date.now()}`,
      }),
    },
  };
}

export function response(ctx) {
  const body = JSON.parse(ctx.result.body);

  if (ctx.result.statusCode !== 200) {
    return util.error(body.message || "Failed to start execution", "StepFunctionsError");
  }

  return {
    executionArn: body.executionArn,
    startDate: body.startDate,
  };
}
