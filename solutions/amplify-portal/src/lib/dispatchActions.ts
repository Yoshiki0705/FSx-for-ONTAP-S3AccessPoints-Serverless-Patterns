/**
 * Parameter types for the portal's generic dispatch actions.
 *
 * GENERATED, then curated. The action names and parameter names come from the
 * Lambda handlers, via `scripts/portal_action_types.py`; the types applied to them
 * come from that script's BRANDS and SCALARS tables. Regenerate with:
 *
 *     python3 scripts/portal_action_types.py --emit > \
 *       solutions/amplify-portal/src/lib/dispatchActions.ts
 *
 * `python3 scripts/portal_action_types.py --check` fails when a handler starts
 * requiring a parameter this file does not declare, or declares one no handler
 * reads. That check is what stops this file becoming a second, disagreeing
 * description of the backend.
 *
 * Why it exists: the dispatch endpoints take an untyped `params` blob, so a
 * component could send anything and the compiler had nothing to check it against.
 * A lock button shipped that had never worked, sending a snapshot name and a day
 * count where the action reads a UUID and an absolute instant. The name mismatch is
 * now caught by a script; the value mismatch needed types.
 */


/**
 * A string that a plain string is not assignable to.
 *
 * The parameter check next to this file compares the *names* a call site sends
 * against the names a handler reads. It cannot see that a name was passed where an
 * identifier was expected, because both are strings and both spell the key
 * correctly. Branding makes those two different types, so the compiler can.
 *
 * Produce one with the matching helper below. The helper is a deliberate act,
 * which is the point: somewhere a value crosses from "some string" to "the UUID of
 * a volume", and that crossing should be visible in the diff.
 */
type Brand<K, T extends string> = K & { readonly __brand: T };

/** The UUID of an FSx for ONTAP volume, as ONTAP reports it. Not a volume name. */
export type VolumeUuid = Brand<string, "VolumeUuid">;
/** The UUID of a snapshot. Not a snapshot name. */
export type SnapshotId = Brand<string, "SnapshotId">;
/** The UUID of a SnapMirror relationship. */
export type SnapmirrorUuid = Brand<string, "SnapmirrorUuid">;
/** The UUID of an SVM. Not an SVM name. */
export type SvmUuid = Brand<string, "SvmUuid">;
/** The UUID of a policy. Not a policy name. */
export type PolicyUuid = Brand<string, "PolicyUuid">;
/** The identifier of a qtree. */
export type QtreeId = Brand<string, "QtreeId">;
/** An absolute instant, ISO 8601. Not a number of days. */
export type IsoTimestamp = Brand<string, "IsoTimestamp">;
/** An ISO 8601 duration such as P30D. Not a number of days. */
export type IsoDuration = Brand<string, "IsoDuration">;

/**
 * Brand an identifier that came from ONTAP.
 *
 * Call this where a listing response is read, not at the call site that consumes
 * the value: branding at the point of use would let a name be branded as a UUID,
 * which is the mistake this is meant to prevent.
 */
export const asVolumeUuid = (uuid: string): VolumeUuid => uuid as VolumeUuid;
export const asSnapshotId = (id: string): SnapshotId => id as SnapshotId;
export const asSnapmirrorUuid = (uuid: string): SnapmirrorUuid => uuid as SnapmirrorUuid;
export const asSvmUuid = (uuid: string): SvmUuid => uuid as SvmUuid;
export const asPolicyUuid = (uuid: string): PolicyUuid => uuid as PolicyUuid;
export const asQtreeId = (id: string): QtreeId => id as QtreeId;

/** An instant, from a Date rather than from arithmetic on a string. */
export const asIsoTimestamp = (when: Date): IsoTimestamp => when.toISOString() as IsoTimestamp;

/** Days from now, as an instant. The conversion a lock has to make. */
export const daysFromNow = (days: number): IsoTimestamp => {
  const when = new Date();
  when.setDate(when.getDate() + days);
  return asIsoTimestamp(when);
};

/**
 * An ISO 8601 duration.
 *
 * Validated rather than asserted, because these arrive from free-text fields. A
 * malformed period was accepted silently before there was anywhere to check it.
 */
export const asIsoDuration = (period: string): IsoDuration | null =>
  /^P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?$/.test(period.trim())
    ? (period.trim() as IsoDuration)
    : null;

/** Days as an ISO duration, for a field that takes a period. */
export const daysAsIsoDuration = (days: number): IsoDuration => `P${days}D` as IsoDuration;


/** Actions of functions/resource-management, reached by `adminMutation`, `adminQuery`. */
export interface ResourceMgmtActionParams {
  abortSnapmirrorTransfer: {
    relationshipUuid: SnapmirrorUuid;
    transferUuid: string;
  };
  acceptClusterPeer: {
    passphrase: string;
    uuid: string;
  };
  acceptSvmPeer: {
    uuid: string;
  };
  addGroupMember: {
    groupSid: string;
    memberName: string;
    groupName?: string;
    svm?: string;
  };
  assignQosToVolume: {
    policyName: string;
    volumeUuid: VolumeUuid;
  };
  assignSnapshotPolicy: {
    policyName: string;
    volumeUuid: VolumeUuid;
    acknowledgeIrreversible?: true;
  };
  breakSnapmirror: {
    confirm: boolean;
    relationshipUuid: SnapmirrorUuid;
  };
  bringVolumeOnline: {
    volumeUuid: VolumeUuid;
    volumeName?: string;
  };
  clearArpSuspects: {
    volumeUuid: VolumeUuid;
  };
  createCifsShare: {
    name: string;
    path: string;
    comment?: string;
    svm?: string;
  };
  createClusterPeer: {
    remoteAddresses: string[];
    generatePassphrase?: boolean;
    ipspace?: string;
    name?: string;
    passphrase?: string;
  };
  createExportPolicy: {
    name: string;
    svm?: string;
  };
  createExportPolicyRule: {
    clientMatch: string;
    policyId: string;
    protocols?: string[];
    roRule?: string[];
    rwRule?: string[];
    superuser?: string[];
  };
  createFlexCache: {
    name: string;
    originVolume: string;
    sizeGiB: number;
    aggregates?: string[];
    constituentsPerAggregate?: number;
    originSvm?: string;
    path?: string;
    prepopulatePaths?: string[];
    svm?: string;
    useTieredAggregate?: boolean;
    writebackEnabled?: boolean;
  };
  createFlexClone: {
    cloneName: string;
    parentVolume: string;
    parentSnapshot?: string;
    svm?: string;
  };
  createFpolicyEvent: {
    fileOperations: string[];
    name: string;
    protocol: string;
    svm?: string;
  };
  createFpolicyPolicy: {
    events: string[];
    name: string;
    engineName?: string;
    priority?: number;
    svm?: string;
  };
  createLocalGroup: {
    name: string;
    description?: string;
    svm?: string;
  };
  createLocalUser: {
    name: string;
    password: string;
    description?: string;
    fullName?: string;
    svm?: string;
  };
  createNameMapping: {
    direction: string;
    pattern: string;
    replacement: string;
    index?: number;
    svm?: string;
  };
  createQosPolicy: {
    name: string;
    expectedIops?: number;
    maxIops?: number;
    maxMbps?: number;
    peakIops?: number;
    policyType?: string;
    svm?: string;
  };
  createQtree: {
    name: string;
    volumeName: string;
    exportPolicy?: string;
    securityStyle?: string;
    svm?: string;
  };
  createQuotaRule: {
    volumeName: string;
    filesHardLimit?: number;
    groupName?: string;
    qtreeName?: string;
    spaceHardLimitGiB?: number;
    spaceSoftLimitGiB?: number;
    svm?: string;
    type?: string;
    userName?: string;
  };
  createSnapmirror: {
    destinationVolume: string;
    createDestination?: boolean;
    initialize?: boolean;
    policy?: string;
    sourceCluster?: string;
    sourcePath?: string;
    svm?: string;
    tieringSupported?: boolean;
  };
  createSnapshotPolicy: {
    name: string;
    schedules: string;
    acknowledgeIrreversible?: true;
    comment?: string;
    svm?: string;
  };
  createSvmPeer: {
    peerSvm: string;
    applications?: string[];
    localSvm?: string;
    peerCluster?: string;
  };
  createVolume: {
    name: string;
    acknowledgeIrreversible?: true;
    aggregates?: string[];
    exportPolicy?: string;
    retentionDefault?: IsoDuration;
    retentionMax?: IsoDuration;
    retentionMin?: IsoDuration;
    securityStyle?: "unix" | "ntfs" | "mixed";
    sizeGiB?: number;
    snaplockType?: "compliance" | "enterprise" | "non_snaplock";
    style?: "flexvol" | "flexgroup";
    svm?: string;
  };
  createVscanPolicy: {
    name: string;
    excludedExtensions?: string[];
    excludedPaths?: string[];
    mandatory?: boolean;
    maxFileSize?: number;
    svm?: string;
  };
  deleteCifsShare: {
    confirm: boolean;
    name: string;
    svm?: string;
  };
  deleteClusterPeer: {
    confirm: boolean;
    uuid: string;
  };
  deleteExportPolicy: {
    confirm: boolean;
    policyId: string;
  };
  deleteExportPolicyRule: {
    policyId: string;
    ruleIndex: number;
  };
  deleteFlexCache: {
    uuid: string;
    name?: string;
  };
  deleteFpolicyEvent: {
    confirm: boolean;
    name: string;
    svm?: string;
  };
  deleteFpolicyPolicy: {
    confirm: boolean;
    name: string;
    svm?: string;
  };
  deleteLocalGroup: {
    sid: string;
    name?: string;
    svm?: string;
  };
  deleteLocalUser: {
    sid: string;
    name?: string;
    svm?: string;
  };
  deleteNameMapping: {
    direction?: string;
    index?: number;
    svm?: string;
  };
  deleteQosPolicy: {
    policyUuid: PolicyUuid;
  };
  deleteQtree: {
    confirm: boolean;
    qtreeId: QtreeId;
    volumeName: string;
    svm?: string;
  };
  deleteQuotaRule: {
    ruleUuid: string;
  };
  deleteSnapmirror: {
    confirm: boolean;
    relationshipUuid: SnapmirrorUuid;
  };
  deleteSnapshotPolicy: {
    confirm: boolean;
    policyUuid: PolicyUuid;
  };
  deleteSvmPeer: {
    confirm: boolean;
    uuid: string;
  };
  deleteVolume: {
    confirm: boolean;
    volumeUuid: VolumeUuid;
    volumeName?: string;
  };
  deleteVscanPolicy: {
    confirm: boolean;
    name: string;
    svm?: string;
  };
  enableArpBulk: {
    volumeUuids: VolumeUuid[];
    state?: "dry_run" | "enabled";
  };
  enableSnapshotLocking: {
    volumeUuid: VolumeUuid;
    acknowledgeIrreversible?: true;
    enabled?: boolean;
  };
  getArpSuspectsAdmin: {
    volumeUuid: VolumeUuid;
  };
  /** No parameters. */
  getClusterInfo: Record<string, never>;
  getDnsConfig: {
    svm?: string;
  };
  getEfficiencyStats: {
    svm?: string;
  };
  getEmsEvents: {
    maxRecords?: number;
    severity?: string;
  };
  getExportPolicyRules: {
    policyId: string;
  };
  getFpolicyStatus: {
    svm?: string;
  };
  getJob: {
    jobId: string;
  };
  /** No parameters. */
  getPortalSettings: Record<string, never>;
  getQuotaReport: {
    svm?: string;
    volumeName?: string;
  };
  getS3ObjectLockStatus: {
    bucket?: string;
  };
  getSnaplockConfig: {
    svm?: string;
    volumeName?: string;
    volumeUuid?: VolumeUuid;
  };
  getSnapmirrorTransfers: {
    relationshipUuid: SnapmirrorUuid;
  };
  getSnapshotLockingStatus: {
    volumeUuid: VolumeUuid;
  };
  getVolume: {
    volumeUuid: VolumeUuid;
  };
  getVolumeRebalance: {
    volumeUuid: VolumeUuid;
  };
  getVscanStatus: {
    svm?: string;
  };
  listArpVolumes: {
    svm?: string;
  };
  listCifsShares: {
    svm?: string;
  };
  /** No parameters. */
  listClusterPeers: Record<string, never>;
  listExportPolicies: {
    svm?: string;
  };
  /** No parameters. */
  listFlexCaches: Record<string, never>;
  listFlexClones: {
    svm?: string;
  };
  listFpolicyEvents: {
    svm?: string;
  };
  listFpolicyPolicies: {
    svm?: string;
  };
  listGroupMembers: {
    groupSid: string;
    svm?: string;
  };
  /** No parameters. */
  listInterclusterLifs: Record<string, never>;
  /** No parameters. */
  listJobs: Record<string, never>;
  /** No parameters. */
  listLicenses: Record<string, never>;
  listLocalGroups: {
    svm?: string;
  };
  listLocalUsers: {
    svm?: string;
  };
  listNameMappings: {
    svm?: string;
  };
  /** No parameters. */
  listNetworkInterfaces: Record<string, never>;
  /** No parameters. */
  listNodes: Record<string, never>;
  listProtocolServices: {
    svm?: string;
  };
  listQosPolicies: {
    svm?: string;
  };
  listQtrees: {
    svm?: string;
    volumeName?: string;
  };
  listQuotaRules: {
    svm?: string;
    volumeName?: string;
  };
  listS3Buckets: {
    nameFilter?: string;
  };
  /** No parameters. */
  listSnapmirrorRelationships: Record<string, never>;
  listSnapshotPolicies: {
    svm?: string;
  };
  /** No parameters. */
  listSvmPeers: Record<string, never>;
  listVolumes: {
    svm?: string;
  };
  listVolumesFiltered: {
    maxRecords?: number;
    nameFilter?: string;
    svm?: string;
  };
  listVscanPolicies: {
    svm?: string;
  };
  lockSnapshot: {
    snapshotUuid: SnapshotId;
    volumeUuid: VolumeUuid;
    acknowledgeIrreversible?: true;
    retentionDays?: number;
  };
  moveNameMapping: {
    direction?: string;
    index?: number;
    newIndex?: number;
    svm?: string;
  };
  putS3ObjectLockRetention: {
    bucket: string;
    acknowledgeIrreversible?: true;
    days?: number;
    mode?: "GOVERNANCE" | "COMPLIANCE";
    years?: number;
  };
  quiesceSnapmirror: {
    relationshipUuid: SnapmirrorUuid;
  };
  removeGroupMember: {
    groupSid: string;
    memberName: string;
    groupName?: string;
    svm?: string;
  };
  renameQtree: {
    confirm: boolean;
    newName: string;
    qtreeId: QtreeId;
    volumeName: string;
    svm?: string;
  };
  resizeVolume: {
    volumeUuid: VolumeUuid;
    newSizeGiB?: number;
  };
  resumeSnapmirror: {
    relationshipUuid: SnapmirrorUuid;
  };
  resyncSnapmirror: {
    confirm: boolean;
    relationshipUuid: SnapmirrorUuid;
  };
  setFlexcacheWriteback: {
    uuid: string;
    enabled?: boolean;
  };
  setFpolicyPolicyEnabled: {
    enabled?: boolean;
    name?: string;
    priority?: number;
    svm?: string;
  };
  setNetworkInterfaceEnabled: {
    confirm?: boolean;
    enabled?: boolean;
    uuid?: string;
  };
  setProtocolServiceEnabled: {
    confirm?: boolean;
    enabled?: boolean;
    protocol?: "nfs" | "cifs" | "s3";
    svm?: string;
  };
  setVolumeQuotaEnabled: {
    volumeUuid: VolumeUuid;
    enabled?: boolean;
  };
  setVscanEnabled: {
    enabled?: boolean;
    svm?: string;
  };
  setVscanPolicyEnabled: {
    enabled?: boolean;
    name?: string;
    svm?: string;
  };
  splitFlexClone: {
    volumeUuid: VolumeUuid;
    volumeName?: string;
  };
  startVolumeRebalance: {
    volumeUuid: VolumeUuid;
    acknowledgeIrreversible?: true;
    maxRuntime?: string;
    startTime?: string;
  };
  stopVolumeRebalance: {
    volumeUuid: VolumeUuid;
    volumeName?: string;
  };
  updateArpStateAdmin: {
    volumeUuid: VolumeUuid;
    state?: "disabled" | "dry_run" | "enabled" | "paused";
  };
  updateArpSurgeParams: {
    volumeUuid: VolumeUuid;
    surgeAsNormal?: boolean;
  };
  updateCifsShare: {
    name: string;
    continuouslyAvailable?: boolean;
    encryption?: boolean;
    svm?: string;
  };
  updateDnsConfig: {
    domains: string[];
    servers: string[];
    svm?: string;
  };
  updateLocalUser: {
    sid: string;
    description?: string;
    enabled?: boolean;
    fullName?: string;
    password?: string;
    svm?: string;
  };
  updateNameMapping: {
    direction?: string;
    index?: number;
    pattern?: string;
    replacement?: string;
    svm?: string;
  };
  updatePortalSettings: {
    key?: "aiAgentEnabled" | "aiSearchEnabled" | "aiMultimodalEnabled" | "chatHistoryEnabled" | "folderWatchEnabled";
    value?: string;
  };
  updateQosPolicy: {
    policyUuid: PolicyUuid;
    expectedIops?: number;
    maxIops?: number;
    maxMbps?: number;
    peakIops?: number;
  };
  updateQtree: {
    qtreeId: QtreeId;
    volumeName: string;
    exportPolicy?: string;
    securityStyle?: "unix" | "ntfs" | "mixed";
    svm?: string;
  };
  updateQuotaRule: {
    ruleUuid: string;
    filesHardLimit?: number;
    spaceHardLimitGiB?: number;
    spaceSoftLimitGiB?: number;
  };
  updateSnaplockRetention: {
    volumeUuid: VolumeUuid;
    acknowledgeIrreversible?: true;
    days?: number;
  };
  updateSnapmirrorNow: {
    relationshipUuid: SnapmirrorUuid;
  };
  updateSvmPeerApplications: {
    applications: string[];
    peerUuid: string;
  };
}

/** Actions of functions/data-protection, reached by `arpMutation`, `arpQuery`. */
export interface DataProtectionActionParams {
  blockNfsIp: {
    clientIp: string;
    confirm: boolean;
    allSvms?: boolean;
    policyName?: string;
    svm?: string;
    svms?: string[];
    ttlHours?: number;
  };
  blockSmbUser: {
    confirm: boolean;
    domain: string;
    username: string;
    allSvms?: boolean;
    svm?: string;
    svms?: string[];
    ttlHours?: number;
  };
  containThreat: {
    confirm: boolean;
    allSvms?: boolean;
    clientIp?: string;
    domain?: string;
    policyName?: string;
    reason?: string;
    svm?: string;
    svms?: string[];
    ttlHours?: number;
    username?: string;
    volumeName?: string;
  };
  createSnapshot: {
    name: string;
    comment?: string;
  };
  deleteSnapshot: {
    snapshotId: SnapshotId;
    snapshotName?: string;
  };
  disconnectSessions: {
    confirm: boolean;
    allSvms?: boolean;
    clientIp?: string;
    svm?: string;
    svms?: string[];
    user?: string;
  };
  /** No parameters. */
  getArpStatus: Record<string, never>;
  /** No parameters. */
  getArpSuspects: Record<string, never>;
  /** No parameters. */
  getProtectionSummary: Record<string, never>;
  /** No parameters. */
  getSnapLockConfig: Record<string, never>;
  getSnapshotsWithLockStatus: {
    maxResults?: number;
  };
  listActiveBlocks: {
    allSvms?: boolean;
    svm?: string;
    svms?: string[];
  };
  /** No parameters. */
  listSvms: Record<string, never>;
  /** No parameters. */
  sweepExpiredBlocks: Record<string, never>;
  unblockNfsIp: {
    clientIp: string;
    allSvms?: boolean;
    confirm?: boolean;
    policyName?: string;
    reason?: string;
    svm?: string;
    svms?: string[];
  };
  unblockSmbUser: {
    domain: string;
    username: string;
    allSvms?: boolean;
    confirm?: boolean;
    reason?: string;
    svm?: string;
    svms?: string[];
  };
  updateArpState: {
    state?: "disabled" | "dry_run" | "enabled" | "paused";
  };
  updateRetentionPolicy: {
    acknowledgeIrreversible?: true;
    days?: number;
    target?: "snaplock" | "s3_object_lock";
  };
}

/** Actions of functions/snapshots, reached by `protectionMutation`, `protectionQuery`. */
export interface SnapshotsActionParams {
  getArpStatus: {
    maxResults?: number;
    svm?: string;
    volumeName?: string;
  };
  getFilePermissions: {
    filePath: string;
    maxResults?: number;
    svm?: string;
    volumeName?: string;
  };
  getProtectionSummary: {
    maxResults?: number;
    svm?: string;
    volumeName?: string;
  };
  getSnaplockStatus: {
    maxResults?: number;
    svm?: string;
    volumeName?: string;
  };
  listSnapshots: {
    acknowledgeIrreversible?: true;
    expiryTime?: IsoTimestamp;
    filePath?: string;
    maxResults?: number;
    snapshotId?: SnapshotId;
    svm?: string;
    volumeName?: string;
  };
  lockSnapshot: {
    expiryTime: IsoTimestamp;
    snapshotId: SnapshotId;
    acknowledgeIrreversible?: true;
    maxResults?: number;
    svm?: string;
    volumeName?: string;
  };
}

/** Actions of functions/list-files, reached by `fileMutation`, `fileQuery`. */
export interface ListFilesActionParams {
  copyFile: {
    continuationToken?: string;
    destinationKey?: string;
    groups?: string;
    maxKeys?: number;
    overwrite?: true;
    prefix?: string;
    sourceKey?: string;
  };
  createFolder: {
    continuationToken?: string;
    groups?: string;
    key?: string;
    maxKeys?: number;
    prefix?: string;
  };
  createUploadLink: {
    continuationToken?: string;
    destinationPrefix?: string;
    expiresIn?: number;
    fileName?: string;
    groups?: string;
    maxKeys?: number;
    prefix?: string;
  };
  deleteFileForever: {
    acknowledgeIrreversible?: true;
    continuationToken?: string;
    groups?: string;
    key?: string;
    maxKeys?: number;
    prefix?: string;
  };
  listAccessPoints: {
    continuationToken?: string;
    groups?: string;
    maxKeys?: number;
    prefix?: string;
  };
  listFiles: {
    acknowledgeIrreversible?: true;
    apAlias?: string;
    continuationToken?: string;
    destinationKey?: string;
    destinationPrefix?: string;
    expiresIn?: number;
    fileName?: string;
    groups?: string;
    key?: string;
    maxKeys?: number;
    maxResults?: number;
    overwrite?: true;
    prefix?: string;
    sourceKey?: string;
    trashKey?: string;
    watchedPrefixes?: string;
  };
  listFilesFromAp: {
    apAlias: string;
    continuationToken?: string;
    groups?: string;
    maxKeys?: number;
    prefix?: string;
  };
  listNotifications: {
    continuationToken?: string;
    groups?: string;
    maxKeys?: number;
    maxResults?: number;
    prefix?: string;
    watchedPrefixes?: string;
  };
  moveFile: {
    continuationToken?: string;
    destinationKey?: string;
    groups?: string;
    maxKeys?: number;
    overwrite?: true;
    prefix?: string;
    sourceKey?: string;
  };
  renameFile: {
    continuationToken?: string;
    destinationKey?: string;
    groups?: string;
    maxKeys?: number;
    overwrite?: true;
    prefix?: string;
    sourceKey?: string;
  };
  restoreFromTrash: {
    continuationToken?: string;
    groups?: string;
    maxKeys?: number;
    prefix?: string;
    trashKey?: string;
  };
  trashFile: {
    continuationToken?: string;
    groups?: string;
    key?: string;
    maxKeys?: number;
    prefix?: string;
  };
}

/** Actions of functions/agent-chat, reached by `agentQuery`. */
export interface AgentChatActionParams {
  chat: {
    agentId?: string;
    history?: Array<{ role: string; content: string }>;
    image?: { data: string; mediaType: string };
    message?: string;
    mode?: "multi" | "kb" | "agent";
    teamId?: string;
  };
  createAgent: {
    category?: string;
    description?: string;
    icon?: string;
    isShared?: boolean;
    name?: string;
    systemPrompt?: string;
    tools?: string[];
  };
  createTeam: {
    agents?: Array<{ agentId: string; name: string; icon: string; role: string }>;
    description?: string;
    isShared?: boolean;
    name?: string;
  };
  deleteAgent: {
    agentId: string;
  };
  deleteSession: {
    sessionId: string;
  };
  deleteTeam: {
    teamId: string;
  };
  getAgent: {
    agentId: string;
  };
  /** No parameters. */
  listAgents: Record<string, never>;
  listSessions: {
    limit?: number;
  };
  /** No parameters. */
  listTeams: Record<string, never>;
  loadSession: {
    sessionId: string;
  };
  saveSession: {
    createdAt?: number;
    messages?: Array<{ role: string; content: string; timestamp: number }>;
    sessionId?: string;
    title?: string;
  };
  updateAgent: {
    agentId: string;
    category?: string;
    description?: string;
    icon?: string;
    isShared?: boolean;
    name?: string;
    systemPrompt?: string;
    tools?: string[];
  };
}

/** Actions of functions/thumbnails, reached by `thumbnailQuery`. */
export interface ThumbnailsActionParams {
  getThumbnails: {
    keys: string[];
    groups?: string;
  };
}

/**
 * Which action map each endpoint uses.
 *
 * A query endpoint and a mutation endpoint that share a Lambda share its
 * actions: the handler does not distinguish them, and pretending otherwise
 * would be a constraint this file invented rather than one it read.
 */
export type DispatchParams = {
  adminMutation: ResourceMgmtActionParams;
  adminQuery: ResourceMgmtActionParams;
  agentQuery: AgentChatActionParams;
  arpMutation: DataProtectionActionParams;
  arpQuery: DataProtectionActionParams;
  fileMutation: ListFilesActionParams;
  fileQuery: ListFilesActionParams;
  protectionMutation: SnapshotsActionParams;
  protectionQuery: SnapshotsActionParams;
  thumbnailQuery: ThumbnailsActionParams;
};

/** Every endpoint whose actions are constrained. */
export type DispatchEndpoint = keyof DispatchParams;

/** The actions one endpoint accepts. */
export type ActionOf<E extends DispatchEndpoint> = keyof DispatchParams[E] & string;

/** The parameters one action takes. */
export type ParamsOf<E extends DispatchEndpoint, A extends ActionOf<E>> = DispatchParams[E][A];

/**
 * Actions that take an `svm`, so `dispatch` can supply the selected one.
 *
 * Derived from the handlers, not listed by hand: an action that starts or
 * stops reading `svm` changes this set with it. The alternative was every
 * panel threading the SVM through its own queries, and the panels that
 * forgot would silently keep reading the default one.
 */
export const ACTIONS_ACCEPTING_SVM: ReadonlySet<string> = new Set([
  "addGroupMember",
  "blockNfsIp",
  "blockSmbUser",
  "containThreat",
  "createCifsShare",
  "createExportPolicy",
  "createFlexCache",
  "createFlexClone",
  "createFpolicyEvent",
  "createFpolicyPolicy",
  "createLocalGroup",
  "createLocalUser",
  "createNameMapping",
  "createQosPolicy",
  "createQtree",
  "createQuotaRule",
  "createSnapmirror",
  "createSnapshotPolicy",
  "createVolume",
  "createVscanPolicy",
  "deleteCifsShare",
  "deleteFpolicyEvent",
  "deleteFpolicyPolicy",
  "deleteLocalGroup",
  "deleteLocalUser",
  "deleteNameMapping",
  "deleteQtree",
  "deleteVscanPolicy",
  "disconnectSessions",
  "getArpStatus",
  "getDnsConfig",
  "getEfficiencyStats",
  "getFilePermissions",
  "getFpolicyStatus",
  "getProtectionSummary",
  "getQuotaReport",
  "getSnaplockConfig",
  "getSnaplockStatus",
  "getVscanStatus",
  "listActiveBlocks",
  "listArpVolumes",
  "listCifsShares",
  "listExportPolicies",
  "listFlexClones",
  "listFpolicyEvents",
  "listFpolicyPolicies",
  "listGroupMembers",
  "listLocalGroups",
  "listLocalUsers",
  "listNameMappings",
  "listProtocolServices",
  "listQosPolicies",
  "listQtrees",
  "listQuotaRules",
  "listSnapshotPolicies",
  "listSnapshots",
  "listVolumes",
  "listVolumesFiltered",
  "listVscanPolicies",
  "lockSnapshot",
  "moveNameMapping",
  "removeGroupMember",
  "renameQtree",
  "setFpolicyPolicyEnabled",
  "setProtocolServiceEnabled",
  "setVscanEnabled",
  "setVscanPolicyEnabled",
  "unblockNfsIp",
  "unblockSmbUser",
  "updateCifsShare",
  "updateDnsConfig",
  "updateLocalUser",
  "updateNameMapping",
  "updateQtree",
]);
