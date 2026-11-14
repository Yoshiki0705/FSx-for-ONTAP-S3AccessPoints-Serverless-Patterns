import { util } from "@aws-appsync/utils";

export function request(ctx) {
  const { pattern, inputPrefix, parameters } = ctx.arguments;

  // Published by `backend.ts` from `config.stateMachineArn` as an AppSync
  // environment variable, because a resolver cannot read the config file it was
  // built from. It used to be a literal here, naming account 123456789012 -- so
  // the value that shipped was a placeholder, and `startProcessing` failed on
  // every deployment including the one whose config named a real state machine.
  // The config field existed and was applied to the IAM scope only, which is why
  // the gap survived: the permission was right and the target was not.
  //
  // Absent rather than wrong when unconfigured: the variable is only set when the
  // config names a state machine, so DemoMode reports that processing is not
  // configured instead of failing against an ARN nobody owns.
  //
  // One state machine per industry pattern. The industry patterns under
  // solutions/industry/ each deploy a stack `fsxn-s3ap-<directory>` whose state machine
  // is named `fsxn-s3ap-<directory>-workflow`, and a pattern key is
  // `UC<n>_<DIRECTORY_NAME>`. When STATE_MACHINE_ARN_TEMPLATE is set (for example
  // `arn:aws:states:ap-northeast-1:<account>:stateMachine:fsxn-s3ap-{slug}-workflow`),
  // `{slug}` is replaced with the directory name derived from the key, so each pattern
  // starts its own state machine. Patterns that do not follow that naming (OPS1, FC7)
  // and deployments without a template use STATE_MACHINE_ARN.
  const parts = String(ctx.arguments.pattern).split("_");
  const isIndustryPattern = parts.length > 1 && parts[0].indexOf("UC") === 0;
  const slug = isIndustryPattern ? parts.slice(1).join("-").toLowerCase() : "";
  const template = ctx.env.STATE_MACHINE_ARN_TEMPLATE;
  const stateMachineArn =
    template && slug ? template.split("{slug}").join(slug) : ctx.env.STATE_MACHINE_ARN;
  if (!stateMachineArn) {
    return util.error(
      "No Step Functions state machine is configured for this deployment. " +
        "Set stateMachineArn or stateMachineArnTemplate in amplify/portal-config.ts " +
        "(or AMPLIFY_PORTAL_SFN_ARN / AMPLIFY_PORTAL_SFN_ARN_TEMPLATE) and redeploy.",
      "ConfigurationError"
    );
  }
  // `pattern` is part of the input so that a single shared state machine can branch on it.
  const input = JSON.stringify({
    pattern: pattern,
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
