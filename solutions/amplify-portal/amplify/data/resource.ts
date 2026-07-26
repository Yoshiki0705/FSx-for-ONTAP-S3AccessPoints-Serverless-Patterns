import { type ClientSchema, a, defineData } from "@aws-amplify/backend";

/**
 * AppSync GraphQL schema for the File Portal.
 *
 * Architecture: Generic dispatch pattern to reduce CloudFormation resource count.
 * Each data source has a single query + mutation endpoint that dispatches by "action" param.
 * This reduces ~57 individual operations (each generating Resolver + FunctionConfiguration)
 * to 8 generic endpoints, saving ~100 CloudFormation resources and ~400KB template size.
 *
 * Operations kept as individual endpoints:
 *   - startProcessing / getJobStatus: Step Functions HTTP data source
 *   - getPresignedUrl: Single-purpose, unique data source
 *   - searchFiles: Separate search data source
 *   - queryAuditLog: Separate audit data source
 *   - getFileMetadata: Separate metadata data source
 *   - generateQrCode: Separate QR data source
 *   - askAboutFile: Bedrock AI data source
 *   - detectLabels: Rekognition data source
 *   - runAthenaQuery: Athena data source
 *   - extractText: Textract data source
 *   - analyzeText: Comprehend data source
 *   - browseCatalog: Glue data source
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

  // --- Step Functions (keep as-is: HTTP data source) ---
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

  // =========================================================================
  // Generic Dispatch: Admin / Resource Management
  // Replaces 35+ individual rm-* operations (listVolumes, createVolume, etc.)
  // Actions: listVolumes, getVolume, createVolume, resizeVolume, deleteVolume,
  //   listExportPolicies, getExportPolicyRules, createExportPolicyRule,
  //   deleteExportPolicyRule, listQosPolicies, createQosPolicy, deleteQosPolicy,
  //   assignQosToVolume, getSnaplockConfig, updateSnaplockRetention,
  //   listQuotaRules, getQuotaReport, createQuotaRule, deleteQuotaRule,
  //   listCifsShares, createCifsShare, deleteCifsShare,
  //   listQtrees, createQtree, deleteQtree, getEfficiencyStats,
  //   listArpVolumes, updateArpStateAdmin, getArpSuspectsAdmin,
  //   clearArpSuspects, updateArpSurgeParams, enableArpBulk,
  //   listSnapshotPolicies, createSnapshotPolicy, enableSnapshotLocking,
  //   lockSnapshot, assignSnapshotPolicy, getSnapshotLockingStatus
  // =========================================================================
  adminQuery: a
    .query()
    .arguments({ action: a.string().required(), params: a.json() })
    .returns(a.json())
    .authorization((allow) => [allow.groups(["storage-admin"])])
    .handler(a.handler.custom({ dataSource: "ResourceMgmtLambdaDataSource", entry: "./resolvers/rm-dispatch.js" })),

  adminMutation: a
    .mutation()
    .arguments({ action: a.string().required(), params: a.json() })
    .returns(a.json())
    .authorization((allow) => [allow.groups(["storage-admin"])])
    .handler(a.handler.custom({ dataSource: "ResourceMgmtLambdaDataSource", entry: "./resolvers/rm-dispatch.js" })),

  // =========================================================================
  // Generic Dispatch: ARP/AI Response Actions
  // Replaces 7 individual arp-* operations
  // Actions: blockSmbUser, unblockSmbUser, blockNfsIp, unblockNfsIp,
  //   containThreat, listActiveBlocks, disconnectSessions
  // =========================================================================
  arpQuery: a
    .query()
    .arguments({ action: a.string().required(), params: a.json() })
    .returns(a.json())
    .authorization((allow) => [allow.authenticated()])
    .handler(a.handler.custom({ dataSource: "ArpResponseLambdaDataSource", entry: "./resolvers/arp-dispatch.js" })),

  arpMutation: a
    .mutation()
    .arguments({ action: a.string().required(), params: a.json() })
    .returns(a.json())
    .authorization((allow) => [allow.groups(["storage-admin"])])
    .handler(a.handler.custom({ dataSource: "ArpResponseLambdaDataSource", entry: "./resolvers/arp-dispatch.js" })),

  // =========================================================================
  // Generic Dispatch: Data Protection (Snapshots, ARP status, SnapLock)
  // Replaces 9 individual snapshot/protection operations
  // Actions: listSnapshots, getArpStatus, getSnaplockStatus,
  //   createSnapshot, deleteSnapshot, updateArpState, lockSnapshot,
  //   updateRetention, getProtectionSummary
  // =========================================================================
  protectionQuery: a
    .query()
    .arguments({ action: a.string().required(), params: a.json() })
    .returns(a.json())
    .authorization((allow) => [allow.authenticated()])
    .handler(a.handler.custom({ dataSource: "ListSnapshotsLambdaDataSource", entry: "./resolvers/snapshots-dispatch.js" })),

  protectionMutation: a
    .mutation()
    .arguments({ action: a.string().required(), params: a.json() })
    .returns(a.json())
    .authorization((allow) => [allow.groups(["storage-admin"])])
    .handler(a.handler.custom({ dataSource: "ListSnapshotsLambdaDataSource", entry: "./resolvers/snapshots-dispatch.js" })),

  // =========================================================================
  // Generic Dispatch: File Operations
  // Replaces 6 individual file operations
  // Actions: listFiles, listFilesFromAp, trashFile, restoreFromTrash,
  //   createUploadLink, renameFile
  // =========================================================================
  fileQuery: a
    .query()
    .arguments({ action: a.string().required(), params: a.json() })
    .returns(a.json())
    .authorization((allow) => [allow.authenticated()])
    .handler(a.handler.custom({ dataSource: "ListFilesLambdaDataSource", entry: "./resolvers/files-dispatch.js" })),

  fileMutation: a
    .mutation()
    .arguments({ action: a.string().required(), params: a.json() })
    .returns(a.json())
    .authorization((allow) => [allow.authenticated()])
    .handler(a.handler.custom({ dataSource: "ListFilesLambdaDataSource", entry: "./resolvers/files-dispatch.js" })),

  // =========================================================================
  // Individual operations (unique data sources — keep as-is)
  // =========================================================================
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

  // --- DynamoDB Models (keep as-is) ---
  FileNotification: a
    .model({
      source: a.string().required(),
      eventType: a.string().required(),
      fileKey: a.string().required(),
      fileName: a.string(),
      fileSize: a.integer(),
      clientIp: a.string(),
      userName: a.string(),
      timestamp: a.string().required(),
    })
    .authorization((allow) => [allow.authenticated()]),

  Favorite: a
    .model({
      fileKey: a.string().required(),
      fileName: a.string(),
      pinnedAt: a.string().required(),
    })
    .authorization((allow) => [allow.owner()]),

  FileTag: a
    .model({
      fileKey: a.string().required(),
      tag: a.string().required(),
      color: a.string(),
      taggedAt: a.string().required(),
    })
    .authorization((allow) => [allow.owner()]),

  FolderWatch: a
    .model({
      folderPrefix: a.string().required(),
      notifyOnCreate: a.boolean(),
      notifyOnModify: a.boolean(),
      notifyOnDelete: a.boolean(),
      createdAt: a.string(),
    })
    .authorization((allow) => [allow.owner()]),

  RecentFile: a
    .model({
      fileKey: a.string().required(),
      fileName: a.string(),
      accessedAt: a.string().required(),
      action: a.string(),
    })
    .authorization((allow) => [allow.owner()]),

  // --- AI/Analytics (unique data sources — keep as-is) ---
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

  extractText: a
    .mutation()
    .arguments({
      key: a.string().required(),
      mode: a.string(),
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

  analyzeText: a
    .mutation()
    .arguments({
      key: a.string().required(),
      analysisType: a.string(),
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

  browseCatalog: a
    .query()
    .arguments({
      action: a.string().required(),
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
