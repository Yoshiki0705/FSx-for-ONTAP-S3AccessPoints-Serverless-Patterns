/**
 * AppSync HTTP Resolver: Get Step Functions execution status.
 *
 * Calls DescribeExecution on the Step Functions API.
 * Returns the current status, output (if completed), and timestamps.
 *
 * NOTE (access control): Currently any authenticated user can query any
 * execution ARN. For production, consider:
 *   - Storing execution ARN → userId mapping in DynamoDB
 *   - Validating ctx.identity.username matches the execution owner
 *   - Using AppSync owner-based authorization on a Job model
 */
export function request(ctx) {
  const { executionArn } = ctx.arguments;

  return {
    method: "POST",
    resourcePath: "/",
    params: {
      headers: {
        "Content-Type": "application/x-amz-json-1.0",
        "X-Amz-Target": "AWSStepFunctions.DescribeExecution",
      },
      body: JSON.stringify({
        executionArn,
      }),
    },
  };
}

export function response(ctx) {
  const body = JSON.parse(ctx.result.body);

  if (ctx.result.statusCode !== 200) {
    return util.error(body.message || "Failed to describe execution", "StepFunctionsError");
  }

  return {
    executionArn: body.executionArn,
    status: body.status,
    startDate: body.startDate,
    stopDate: body.stopDate || null,
    output: body.output ? JSON.parse(body.output) : null,
  };
}
