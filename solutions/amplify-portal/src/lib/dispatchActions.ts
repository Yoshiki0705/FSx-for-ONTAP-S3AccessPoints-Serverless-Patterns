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
    generatePassphrase?: boolean;
    ipspace?: string;
    name?: string;
    passphrase?: string;
    remoteAddresses?: string[];
  };
  createExportPolicy: {
    name: string;
    svm?: string;
  };
  createExportPolicyRule: {
    clientMatch: string;
    policyId: string;
    protocols?: string;
    roRule?: string;
    rwRule?: string;
    superuser?: string;
  };
  createFlexCache: {
    name: string;
    originVolume: string;
    sizeGiB: number;
    originSvm?: string;
    path?: string;
    prepopulatePaths?: string;
    svm?: string;
  };
  createFlexClone: {
    cloneName: string;
    parentVolume: string;
    parentSnapshot?: string;
    svm?: string;
  };
  createFpolicyEvent: {
    name: string;
    protocol: string;
    fileOperations?: string[];
    svm?: string;
  };
  createFpolicyPolicy: {
    name: string;
    engineName?: string;
    events?: string[];
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
    index?: string;
    svm?: string;
  };
  createQosPolicy: {
    name: string;
    expectedIops?: string;
    maxIops?: string;
    maxMbps?: string;
    peakIops?: string;
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
    filesHardLimit?: string;
    groupName?: string;
    qtreeName?: string;
    spaceHardLimitGiB?: string;
    spaceSoftLimitGiB?: string;
    svm?: string;
    type?: string;
    userName?: string;
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
    applications?: string;
    localSvm?: string;
    peerCluster?: string;
  };
  createVolume: {
    name: string;
    acknowledgeIrreversible?: true;
    exportPolicy?: string;
    retentionDefault?: IsoDuration;
    retentionMax?: IsoDuration;
    retentionMin?: IsoDuration;
    securityStyle?: "unix" | "ntfs" | "mixed";
    sizeGiB?: number;
    snaplockType?: "compliance" | "enterprise" | "non_snaplock";
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
    ruleIndex: string;
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
    index?: string;
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
    volumeUuids: string;
    state?: string;
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
  updateArpStateAdmin: {
    volumeUuid: VolumeUuid;
    state?: string;
  };
  updateArpSurgeParams: {
    volumeUuid: VolumeUuid;
    surgeAsNormal?: string;
  };
  updateCifsShare: {
    name: string;
    continuouslyAvailable?: string;
    encryption?: string;
    svm?: string;
  };
  updateDnsConfig: {
    domains?: string;
    servers?: string;
    svm?: string;
  };
  updatePortalSettings: {
    key?: string;
    value?: string;
  };
  updateQosPolicy: {
    policyUuid: PolicyUuid;
    expectedIops?: string;
    maxIops?: string;
    maxMbps?: string;
    peakIops?: string;
  };
  updateSnaplockRetention: {
    volumeUuid: VolumeUuid;
    acknowledgeIrreversible?: true;
    days?: number;
  };
  updateSnapmirrorNow: {
    relationshipUuid: SnapmirrorUuid;
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
  getS3ObjectLockStatus: Record<string, never>;
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
    confirm: boolean;
    allSvms?: boolean;
    policyName?: string;
    reason?: string;
    svm?: string;
    svms?: string[];
  };
  unblockSmbUser: {
    confirm: boolean;
    domain: string;
    username: string;
    allSvms?: boolean;
    reason?: string;
    svm?: string;
    svms?: string[];
  };
  updateArpState: {
    state?: string;
  };
  updateRetentionPolicy: {
    acknowledgeIrreversible?: true;
    days?: number;
    mode?: "GOVERNANCE" | "COMPLIANCE";
    target?: "snaplock" | "s3_object_lock";
  };
}

/** Actions of functions/snapshots, reached by `protectionMutation`, `protectionQuery`. */
export interface SnapshotsActionParams {
  /** No parameters. */
  getArpStatus: Record<string, never>;
  getFilePermissions: {
    filePath: string;
  };
  /** No parameters. */
  getProtectionSummary: Record<string, never>;
  /** No parameters. */
  getSnaplockStatus: Record<string, never>;
  listSnapshots: {
    acknowledgeIrreversible?: true;
    expiryTime?: IsoTimestamp;
    filePath?: string;
    maxResults?: number;
    snapshotId?: SnapshotId;
  };
  lockSnapshot: {
    expiryTime: IsoTimestamp;
    snapshotId: SnapshotId;
    acknowledgeIrreversible?: true;
  };
}

/** Actions of functions/list-files, reached by `fileMutation`, `fileQuery`. */
export interface ListFilesActionParams {
  createUploadLink: {
    destinationPrefix?: string;
    expiresIn?: string;
    fileName?: string;
  };
  listFiles: {
    apAlias?: string;
    continuationToken?: string;
    destinationKey?: string;
    destinationPrefix?: string;
    expiresIn?: string;
    fileName?: string;
    groups?: string;
    key?: string;
    maxKeys?: number;
    prefix?: string;
    sourceKey?: string;
    trashKey?: string;
  };
  listFilesFromAp: {
    apAlias: string;
  };
  renameFile: {
    destinationKey: string;
    sourceKey: string;
  };
  restoreFromTrash: {
    trashKey?: string;
  };
  trashFile: {
    key: string;
  };
}

/** Actions of functions/agent-chat, reached by `agentQuery`. */
export interface AgentChatActionParams {
  chat: {
    history?: string;
    image?: string;
    message?: string;
    mode?: string;
  };
  createAgent: {
    category?: string;
    description?: string;
    icon?: string;
    isShared?: boolean;
    name?: string;
    systemPrompt?: string;
    tools?: string;
  };
  createTeam: {
    agents?: string;
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
    createdAt?: string;
    messages?: string;
    sessionId?: string;
    title?: string;
  };
  updateAgent: {
    agentId: string;
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
};

/** Every endpoint whose actions are constrained. */
export type DispatchEndpoint = keyof DispatchParams;

/** The actions one endpoint accepts. */
export type ActionOf<E extends DispatchEndpoint> = keyof DispatchParams[E] & string;

/** The parameters one action takes. */
export type ParamsOf<E extends DispatchEndpoint, A extends ActionOf<E>> = DispatchParams[E][A];
