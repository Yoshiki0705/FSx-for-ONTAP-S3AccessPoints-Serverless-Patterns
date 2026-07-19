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

  // --- AI/Analytics Mutations ---
  askAboutFile: a
    .mutation()
    .arguments({
      key: a.string().required(),
      question: a.string().required(),
    })
    .returns(
      a.customType({
        answer: a.string(),
        model: a.string(),
        error: a.string(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "AskAboutFileLambdaDataSource",
        entry: "./resolvers/ask-about-file.js",
      })
    ),

  detectLabels: a
    .mutation()
    .arguments({
      key: a.string().required(),
      maxLabels: a.integer(),
      minConfidence: a.float(),
    })
    .returns(
      a.customType({
        labels: a.json(),
        error: a.string(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "DetectLabelsLambdaDataSource",
        entry: "./resolvers/detect-labels.js",
      })
    ),

  // --- Athena SQL Query ---
  runAthenaQuery: a
    .mutation()
    .arguments({
      sql: a.string().required(),
      database: a.string(),
    })
    .returns(
      a.customType({
        columns: a.string().array(),
        rows: a.json(),
        status: a.string(),
        error: a.string(),
        executionId: a.string(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "AthenaQueryLambdaDataSource",
        entry: "./resolvers/run-athena-query.js",
      })
    ),

  // --- Textract ---
  extractText: a
    .mutation()
    .arguments({
      key: a.string().required(),
      mode: a.string(), // "text" or "analyze"
    })
    .returns(
      a.customType({
        text: a.string(),
        blockCount: a.integer(),
        pageCount: a.integer(),
        error: a.string(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "TextractLambdaDataSource",
        entry: "./resolvers/extract-text.js",
      })
    ),

  // --- Comprehend ---
  analyzeText: a
    .mutation()
    .arguments({
      key: a.string().required(),
      analysisType: a.string(), // "entities", "sentiment", "keyPhrases"
    })
    .returns(
      a.customType({
        results: a.json(),
        error: a.string(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "ComprehendLambdaDataSource",
        entry: "./resolvers/analyze-text.js",
      })
    ),

  // --- Glue Catalog ---
  browseCatalog: a
    .query()
    .arguments({
      action: a.string().required(), // "listDatabases", "listTables", "getSchema"
      database: a.string(),
      table: a.string(),
    })
    .returns(a.json())
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "GlueCatalogLambdaDataSource",
        entry: "./resolvers/browse-catalog.js",
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
