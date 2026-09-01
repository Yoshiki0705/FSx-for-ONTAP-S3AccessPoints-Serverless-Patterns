/**
 * The ARNs that replace a bare `*` in this backend's IAM policies.
 *
 * Every one of these existed as a comment first -- `resources: ["*"], // Restrict to
 * specific secret ARN in production` -- which is a TODO that reads as a decision. cdk-nag
 * reported each as `AwsSolutions-IAM5[Resource::*]`, and `security/cdk-nag-baseline.txt`
 * recorded them, so the gate could not tell a narrowing from a regression.
 *
 * Its own module for the reason `validate-authorization-config.ts` gives: reading
 * `backend.ts` for the presence of an ARN would confirm the code exists without
 * establishing its shape, and the shape is the whole of what these are.
 *
 * The deployment's partition, region and account arrive as an argument rather than being
 * read from `Aws.*` here, matching `scopeS3ApArns`. CDK pseudo-parameters resolve per stack
 * at deploy time but never to a literal, so a function that reached for them directly could
 * only be tested against `{"Ref": "AWS::Region"}` -- which is the same string for all three.
 *
 * What stays `*`, verified against the service authorization reference on 2026-08-28
 * rather than assumed:
 *
 *   `fsx:DescribeFileSystems`, `fsx:DescribeStorageVirtualMachines` and
 *   `fsx:DescribeS3AccessPointAttachments` define no resource type at all -- they answer
 *   for the account and Region of the endpoint.
 *
 *   `comprehend:DetectSentiment` and `DetectKeyPhrases` define none; `DetectEntities`
 *   defines only an optional custom `entity-recognizer-endpoint`, which this portal does
 *   not use.
 *
 *   `textract:DetectDocumentText` and `AnalyzeDocument` define only `adapter` and
 *   `adapterversion`, neither of which this portal creates.
 *
 *   `rekognition:DetectLabels` operates on bytes or an S3 reference, and AWS's own
 *   identity-based policy example grants it on `"*"`.
 *
 *   `s3:ListAllMyBuckets` is an account-level operation.
 */

/** The deployment an ARN is built for. Pass the CDK pseudo-parameters. */
export interface Deployment {
  partition: string;
  region: string;
  account: string;
}

const glueArnPrefix = (deployment: Deployment): string =>
  `arn:${deployment.partition}:glue:${deployment.region}:${deployment.account}`;

/**
 * The ARN of the secret holding the ONTAP credentials.
 *
 * Secrets Manager appends six random characters to the name it stores, so a policy written
 * against the configured name has to end in a wildcard to match. That wildcard covers one
 * secret's versions, not other secrets: `ontap/admin-*` does not match `ontap/admin2`,
 * because the suffix separator is part of the literal.
 *
 * An operator who configured a full ARN gets it back unchanged -- they have already been
 * exact, and appending to an ARN would make it match nothing.
 *
 * Unset -- which is what `portal-config.example.ts` ships -- grants every secret in this
 * account and Region rather than interpolating to `secret:-*`. That ARN names a secret whose
 * name begins with a hyphen, so it matches nothing, and the ONTAP calls would fail as though
 * the role were wrong when the truth is that the deployment has no secret configured. The
 * same reasoning as the Object Lock bucket below: a policy naming none refuses every call.
 *
 * @param secretName The configured `ontapSecretName`, a name or a full ARN.
 * @param deployment The deployment's partition, region and account.
 */
export function ontapSecretArn(secretName: string, deployment: Deployment): string {
  if (secretName.startsWith("arn:")) return secretName;
  const { partition, region, account } = deployment;
  const prefix = `arn:${partition}:secretsmanager:${region}:${account}:secret:`;
  const name = secretName.trim();
  return name ? `${prefix}${name}-*` : `${prefix}*`;
}

/**
 * The Athena workgroup this deployment queries through.
 *
 * No wildcard: the workgroup is fixed at deploy time, and the handlers read it from their
 * environment rather than from the request.
 *
 * @param workGroup The configured workgroup name.
 * @param deployment The deployment's partition, region and account.
 */
export function athenaWorkGroupArn(workGroup: string, deployment: Deployment): string {
  const { partition, region, account } = deployment;
  return `arn:${partition}:athena:${region}:${account}:workgroup/${workGroup}`;
}

/**
 * The Glue catalog, database and table ARNs a read of one known table needs.
 *
 * Three ARNs rather than one: Glue authorizes a table read against the table, the database
 * holding it and the account's catalog, and omitting any of the three fails the call.
 *
 * For a caller that reads one table fixed at deploy time -- the audit log reads
 * `ATHENA_DATABASE`.`ATHENA_TABLE` from its environment and takes neither from the request
 * -- pass the table and the grant names it exactly. Omit it and the tables within that one
 * database become a wildcard.
 *
 * @param database The configured Glue/Athena database name.
 * @param deployment The deployment's partition, region and account.
 * @param table The table, when one deployment reads exactly one.
 */
export function glueReadArns(
  database: string,
  deployment: Deployment,
  table?: string
): string[] {
  const prefix = glueArnPrefix(deployment);
  return [
    `${prefix}:catalog`,
    `${prefix}:database/${database}`,
    `${prefix}:table/${database}/${table ?? "*"}`,
  ];
}

/**
 * The catalog, and every database and table in it, for this account and Region.
 *
 * The catalog browser and the ad-hoc query function take the database from the request --
 * `event.get("database")` -- because the point of both is to browse what the account holds.
 * Naming one database here would leave the UI listing databases it then cannot open, so the
 * database and table entries stay wildcards.
 *
 * Still narrower than the `*` this replaces: it is bound to one account and Region, and it
 * grants nothing on the Glue resources that are not catalog contents -- crawlers, jobs,
 * triggers, connections, dev endpoints, ML transforms, schema registries. Those share the
 * `glue:` namespace, and `*` covered all of them.
 *
 * @param deployment The deployment's partition, region and account.
 */
export function glueAnyDatabaseArns(deployment: Deployment): string[] {
  const prefix = glueArnPrefix(deployment);
  return [`${prefix}:catalog`, `${prefix}:database/*`, `${prefix}:table/*/*`];
}

/**
 * A DynamoDB table this deployment was pointed at, by name.
 *
 * For tables the portal does not create. A CDK-managed table exposes `table.tableArn`, which
 * is exact and needs none of this; these are the ones an operator names in the configuration,
 * so the ARN has to be built and may be unbuildable.
 *
 * Returns `undefined` when unset, which the caller renders as `*`. Interpolating an empty
 * name would give `table/`, which addresses no table, so every call would be denied for a
 * reason that reads as a broken grant rather than as missing configuration.
 *
 * @param tableName The configured table name, or an empty string.
 * @param deployment The deployment's partition, region and account.
 */
export function dynamoTableArn(
  tableName: string,
  deployment: Deployment
): string | undefined {
  const name = tableName.trim();
  if (!name) return undefined;
  const { partition, region, account } = deployment;
  return `arn:${partition}:dynamodb:${region}:${account}:table/${name}`;
}

/**
 * The bucket behind an `s3://bucket/prefix` location, and the objects under it.
 *
 * Athena is configured with an output location as a URI rather than a bucket name, and the
 * role running the query needs to write there. Parsing it here keeps the policy and the
 * handler's `ATHENA_OUTPUT_LOCATION` derived from the same configured value.
 *
 * Returns `undefined` for anything that is not an `s3://` URI naming a bucket -- unset, or a
 * value the operator mistyped -- rather than guessing. The caller renders that as `*`.
 *
 * The prefix in the URI is deliberately not carried into the ARN: Athena writes its results
 * under a per-query subdirectory of that prefix, and a grant fixed to the prefix itself would
 * refuse them.
 *
 * @param uri The configured `s3://` location.
 * @param deployment The deployment's partition, region and account.
 */
export function s3UriBucketArns(
  uri: string,
  deployment: Deployment
): string[] | undefined {
  const trimmed = uri.trim();
  if (!trimmed.startsWith("s3://")) return undefined;
  const bucket = trimmed.slice("s3://".length).split("/")[0];
  if (!bucket) return undefined;
  return bucketAndObjects(`arn:${deployment.partition}:s3:::${bucket}`);
}

/**
 * A bucket and the objects in it.
 *
 * Both entries are required and neither substitutes for the other: a bucket-level action is
 * denied by an ARN carrying `/*`, and an object-level action is denied by one without it.
 *
 * The object entry is a wildcard because object keys cannot be enumerated in advance. That
 * is the wildcard cdk-nag reports as `Resource::<bucket>/*`, and it is the one that cannot
 * be removed.
 *
 * @param bucketArn The bucket's ARN.
 */
export function bucketAndObjects(bucketArn: string): string[] {
  return [bucketArn, `${bucketArn}/*`];
}
