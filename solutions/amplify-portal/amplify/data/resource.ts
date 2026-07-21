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
    "FC7_FLEXCLONE_RESTORE",
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

  listSnapshots: a
    .query()
    .arguments({
      maxResults: a.integer(),
    })
    .returns(
      a.customType({
        snapshots: a.json(),
        volumeName: a.string(),
        error: a.string(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "ListSnapshotsLambdaDataSource",
        entry: "./resolvers/list-snapshots.js",
      })
    ),

  searchFiles: a
    .query()
    .arguments({
      query: a.string().required(),
      maxResults: a.integer(),
    })
    .returns(
      a.customType({
        results: a.json(),
        query: a.string(),
        error: a.string(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "SearchFilesLambdaDataSource",
        entry: "./resolvers/search-files.js",
      })
    ),

  queryAuditLog: a
    .query()
    .arguments({
      fileKeyPrefix: a.string(),
      startDate: a.string(),
      endDate: a.string(),
      eventType: a.string(),
      maxResults: a.integer(),
    })
    .returns(
      a.customType({
        events: a.json(),
        queryExecutionId: a.string(),
        error: a.string(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "QueryAuditLogLambdaDataSource",
        entry: "./resolvers/query-audit-log.js",
      })
    ),

  listFilesFromAp: a
    .query()
    .arguments({
      prefix: a.string(),
      maxKeys: a.integer(),
      apAlias: a.string().required(),
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
        entry: "./resolvers/list-files-from-ap.js",
      })
    ),

  getFileMetadata: a
    .query()
    .arguments({
      fileKeys: a.string().array().required(),
    })
    .returns(
      a.customType({
        metadata: a.json(),
        error: a.string(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "GetFileMetadataLambdaDataSource",
        entry: "./resolvers/get-file-metadata.js",
      })
    ),

  generateQrCode: a
    .mutation()
    .arguments({
      key: a.string().required(),
      expiresIn: a.integer(),
    })
    .returns(
      a.customType({
        qrCodeBase64: a.string(),
        presignedUrl: a.string(),
        expiresIn: a.integer(),
        error: a.string(),
      })
    )
    .authorization((allow) => [allow.authenticated()])
    .handler(
      a.handler.custom({
        dataSource: "GenerateQrCodeLambdaDataSource",
        entry: "./resolvers/generate-qr-code.js",
      })
    ),

  // --- E-1/E-2: Real-time notifications (FPolicy + SFTP) ---
  FileNotification: a
    .model({
      source: a.string().required(),   // "FPOLICY" | "SFTP" | "PORTAL"
      eventType: a.string().required(), // "CREATE" | "MODIFY" | "DELETE" | "RENAME"
      fileKey: a.string().required(),
      fileName: a.string(),
      fileSize: a.integer(),
      clientIp: a.string(),
      userName: a.string(),
      timestamp: a.string().required(),
    })
    .authorization((allow) => [allow.authenticated()]),

  // --- UX-1: Favorites / Pinned files ---
  Favorite: a
    .model({
      fileKey: a.string().required(),
      fileName: a.string(),
      pinnedAt: a.string().required(),
    })
    .authorization((allow) => [allow.owner()]),

  // --- UX-2: User-defined tags ---
  FileTag: a
    .model({
      fileKey: a.string().required(),
      tag: a.string().required(),
      color: a.string(),  // Optional: hex color for badge display
      taggedAt: a.string().required(),
    })
    .authorization((allow) => [allow.owner()]),

  // --- UX-3: Trash (soft delete) ---
  trashFile: a
    .mutation()
    .arguments({ key: a.string().required() })
    .returns(a.customType({ success: a.boolean(), trashKey: a.string(), error: a.string() }))
    .authorization((allow) => [allow.authenticated()])
    .handler(a.handler.custom({ dataSource: "ListFilesLambdaDataSource", entry: "./resolvers/trash-file.js" })),

  restoreFromTrash: a
    .mutation()
    .arguments({ trashKey: a.string().required() })
    .returns(a.customType({ success: a.boolean(), restoredKey: a.string(), error: a.string() }))
    .authorization((allow) => [allow.authenticated()])
    .handler(a.handler.custom({ dataSource: "ListFilesLambdaDataSource", entry: "./resolvers/restore-from-trash.js" })),

  // --- UX-6: Folder watch notifications ---
  FolderWatch: a
    .model({
      folderPrefix: a.string().required(),  // e.g., "contracts/2026/"
      notifyOnCreate: a.boolean(),
      notifyOnModify: a.boolean(),
      notifyOnDelete: a.boolean(),
      createdAt: a.string(),
    })
    .authorization((allow) => [allow.owner()]),

  // --- Data Protection: Read (authenticated) ---
  getProtectionSummary: a
    .query()
    .arguments({ volumeName: a.string() })
    .returns(a.customType({ data: a.json(), error: a.string() }))
    .authorization((allow) => [allow.authenticated()])
    .handler(a.handler.custom({ dataSource: "ListSnapshotsLambdaDataSource", entry: "./resolvers/get-protection-summary.js" })),

  // --- Data Protection: Write (storage-admin only) ---
  createSnapshot: a
    .mutation()
    .arguments({ name: a.string().required(), comment: a.string() })
    .returns(a.customType({ success: a.boolean(), snapshotName: a.string(), error: a.string() }))
    .authorization((allow) => [allow.groups(["storage-admin"])])
    .handler(a.handler.custom({ dataSource: "ListSnapshotsLambdaDataSource", entry: "./resolvers/create-snapshot.js" })),

  deleteSnapshot: a
    .mutation()
    .arguments({ snapshotId: a.string().required(), snapshotName: a.string().required() })
    .returns(a.customType({ success: a.boolean(), error: a.string() }))
    .authorization((allow) => [allow.groups(["storage-admin"])])
    .handler(a.handler.custom({ dataSource: "ListSnapshotsLambdaDataSource", entry: "./resolvers/delete-snapshot.js" })),

  updateArpState: a
    .mutation()
    .arguments({ state: a.string().required() })
    .returns(a.customType({ success: a.boolean(), newState: a.string(), error: a.string() }))
    .authorization((allow) => [allow.groups(["storage-admin"])])
    .handler(a.handler.custom({ dataSource: "ListSnapshotsLambdaDataSource", entry: "./resolvers/update-arp-state.js" })),

  updateRetentionPolicy: a
    .mutation()
    .arguments({ target: a.string().required(), mode: a.string(), days: a.integer() })
    .returns(a.customType({ success: a.boolean(), error: a.string() }))
    .authorization((allow) => [allow.groups(["storage-admin"])])
    .handler(a.handler.custom({ dataSource: "ListSnapshotsLambdaDataSource", entry: "./resolvers/update-retention.js" })),

  // --- UX-7: File request (external upload link) ---
  createUploadLink: a
    .mutation()
    .arguments({
      destinationPrefix: a.string().required(),
      fileName: a.string(),
      expiresIn: a.integer(),
      maxSizeBytes: a.integer(),
    })
    .returns(a.customType({
      uploadUrl: a.string(),
      destinationKey: a.string(),
      expiresIn: a.integer(),
      error: a.string(),
    }))
    .authorization((allow) => [allow.authenticated()])
    .handler(a.handler.custom({ dataSource: "ListFilesLambdaDataSource", entry: "./resolvers/create-upload-link.js" })),

  // --- UX-8: Recent files ---
  RecentFile: a
    .model({
      fileKey: a.string().required(),
      fileName: a.string(),
      accessedAt: a.string().required(),
      action: a.string(),  // "view" | "download" | "ai_query"
    })
    .authorization((allow) => [allow.owner()]),

  // --- UX-9: Rename file ---
  renameFile: a
    .mutation()
    .arguments({
      sourceKey: a.string().required(),
      destinationKey: a.string().required(),
    })
    .returns(a.customType({ success: a.boolean(), newKey: a.string(), error: a.string() }))
    .authorization((allow) => [allow.authenticated()])
    .handler(a.handler.custom({ dataSource: "ListFilesLambdaDataSource", entry: "./resolvers/rename-file.js" })),

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
