import { type ClientSchema, a, defineData } from "@aws-amplify/backend";

/**
 * AppSync GraphQL schema for the File Portal.
 *
 * Operations:
 *   - startProcessing: Triggers a Step Functions workflow for a given UC pattern
 *   - getJobStatus: Polls execution status of a running workflow
 *   - listFiles: Lists files in a given prefix via S3 AP (through Lambda)
 *   - onJobComplete: Real-time subscription for workflow completion
 *
 * The HTTP data source connects directly to Step Functions API,
 * eliminating the need for a wrapper Lambda (lower latency).
 */
const schema = a.schema({
  // --- Enums ---
  JobStatus: a.enum(["RUNNING", "SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"]),

  ProcessingPattern: a.enum([
    "UC1_LEGAL_COMPLIANCE",
    "UC3_HEALTHCARE_IMAGING",
    "UC6_SEMICONDUCTOR_EDA",
    "UC10_MEDIA_PRODUCTION",
    "UC15_MANUFACTURING_QC",
    "OPS1_CAPACITY_RIGHTSIZING",
  ]),

  // --- DynamoDB Model ---
  JobExecution: a
    .model({
      executionArn: a.string().required(),
      pattern: a.string().required(),
      inputPrefix: a.string().required(),
      status: a.string(),
      startDate: a.string(),
      stopDate: a.string(),
      output: a.json(),
    })
    .authorization((allow) => [allow.owner()]),

  // --- Custom Types ---
  FileItem: a.customType({
    key: a.string().required(),
    size: a.integer(),
    lastModified: a.string(),
    storageClass: a.string(),
  }),

  JobResult: a.customType({
    executionArn: a.string().required(),
    status: a.ref("JobStatus").required(),
    startDate: a.string(),
    stopDate: a.string(),
    output: a.json(),
  }),

  // --- Mutations ---
  startProcessing: a
    .mutation()
    .arguments({
      pattern: a.ref("ProcessingPattern").required(),
      inputPrefix: a.string().required(),
      parameters: a.json(),
    })
    .returns(
      a.customType({
        executionArn: a.string().required(),
        startDate: a.string().required(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "StepFunctionsHttpDataSource",
        entry: "./resolvers/start-processing.js",
      })
    ),

  // --- Queries ---
  getJobStatus: a
    .query()
    .arguments({
      executionArn: a.string().required(),
    })
    .returns(a.ref("JobResult"))
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "StepFunctionsHttpDataSource",
        entry: "./resolvers/get-job-status.js",
      })
    ),

  listFiles: a
    .query()
    .arguments({
      prefix: a.string(),
      maxKeys: a.integer(),
      continuationToken: a.string(),
    })
    .returns(
      a.customType({
        files: a.ref("FileItem").array(),
        nextContinuationToken: a.string(),
        isTruncated: a.boolean(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "ListFilesLambdaDataSource",
        entry: "./resolvers/list-files.js",
      })
    ),

  getPresignedUrl: a
    .query()
    .arguments({
      key: a.string().required(),
      expiresIn: a.integer(),
    })
    .returns(
      a.customType({
        url: a.string(),
        expiresIn: a.integer(),
        error: a.string(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "GetPresignedUrlLambdaDataSource",
        entry: "./resolvers/get-presigned-url.js",
      })
    ),
});

export type Schema = ClientSchema<typeof schema>;

export const data = defineData({
  schema,
  authorizationModes: {
    defaultAuthorizationMode: "userPool",
  },
});
