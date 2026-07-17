/**
 * AppSync Lambda Resolver: List files via S3 AP.
 *
 * This resolver invokes a Lambda function that calls ListObjectsV2
 * on the FSx for ONTAP S3 Access Point. The Lambda runs VPC-external
 * (Internet-origin AP pattern).
 *
 * Data source: ListFilesLambdaDataSource (configured in custom stack)
 */
export function request(ctx) {
  const { prefix, maxKeys, continuationToken } = ctx.arguments;

  return {
    operation: "Invoke",
    payload: {
      action: "listFiles",
      prefix: prefix || "",
      maxKeys: maxKeys || 100,
      continuationToken: continuationToken || null,
      userId: ctx.identity.username,
    },
  };
}

export function response(ctx) {
  if (ctx.error) {
    return util.error(ctx.error.message, ctx.error.type);
  }

  const result = ctx.result;
  return {
    files: result.files || [],
    nextContinuationToken: result.nextContinuationToken || null,
    isTruncated: result.isTruncated || false,
  };
}
