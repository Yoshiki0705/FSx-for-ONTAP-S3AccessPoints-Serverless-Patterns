/**
 * FSx for ONTAP File Portal — Configuration Example
 *
 * SETUP:
 *   1. Copy this file:  cp portal-config.example.ts portal-config.ts
 *   2. Edit portal-config.ts with your environment values
 *   3. Edit src/portal-settings.ts for frontend settings (Upload tab, region, accountId)
 *   4. Deploy: make sandbox (or npx ampx sandbox)
 *
 * ALTERNATIVE: Set environment variables instead of editing the file:
 *   export AMPLIFY_PORTAL_REGION=ap-northeast-1
 *   export AMPLIFY_PORTAL_S3AP_ALIAS=my-s3-access-point01-abc123-s3alias
 *   export AMPLIFY_PORTAL_SFN_ARN=arn:aws:states:ap-northeast-1:123456789012:stateMachine:my-workflow
 *
 * UPLOAD TAB (Storage Browser):
 *   The Upload tab uses Storage Browser for S3, which requires frontend-side config
 *   in src/portal-settings.ts. Set region, accountId, and s3ApAlias there.
 *   The Upload tab uses Cognito Identity Pool credentials (auto-provisioned by sandbox).
 */

export interface PortalConfig {
  region: string;
  s3ApAlias: string;
  stateMachineArn: string;
  stateMachineResourceScope: string;
  s3ApResourceArns: string[];
  groupApMapping: Record<string, string>;

  // Path prefixes per Cognito group. Omit to derive them from `groupApMapping`
  // (each group gets `<group>/` and `shared/`), which is what happened before this
  // became configurable. See `portal-config.ts` for why it stayed optional.
  groupPathPrefixes?: Record<string, string[]>;

  // How accounts come into existence, and what signing in requires.
  signIn: {
    selfSignUpEnabled: boolean;
    mfa: "OFF" | "OPTIONAL" | "REQUIRED";
  };

  // Emit role-based AppSync rules instead of `allow.authenticated()`.
  // While false, any signed-in user can write and delete.
  enforceRoles: boolean;

  // What a caller holding the `external` scope may do, regardless of role.
  externalDefaults: {
    aiEnabled: boolean;
    shareLinksByRole: Record<string, boolean>;
  };

  bedrockKbId: string;

  // Bedrock Guardrails (PII detection/masking + content filtering)
  bedrockGuardrailId: string;
  bedrockGuardrailVersion: string;

  // VPC configuration (required for ONTAP REST API access)
  vpcId: string;
  vpcSubnetIds: string[];
  vpcSecurityGroupIds: string[];
  // Required whenever vpcId is set. See the assignment below for why.
  vpcRouteTableIds: string[];
  // Escape hatch: deploy into a VPC with no block expiry, on purpose.
  allowNoBlockExpiry: boolean;

  // Bucket backing the S3 Object Lock panel. Empty disables that panel.
  s3ObjectLockBucket: string;

  // Containment block expiry. All three are read by backend.ts and passed to the
  // ARP function; leaving one out puts the string "undefined" in its environment
  // and the function then fails on import. tests/infrastructure guards this.
  defaultBlockTtlHours: number;
  maxBlockTtlHours: number;
  blockSweepIntervalMinutes: number;
  // Notified when the containment sweep fails or stops running. Empty = nobody.
  alarmEmail: string;

  // ONTAP connection
  ontapMgmtIp: string;
  ontapSecretName: string;
  ontapSvmName: string;
  ontapVolumeName: string;
}

export const config: PortalConfig = {
  // ─── Required ───────────────────────────────────────────────────────────

  /** AWS Region where your FSx for ONTAP and Step Functions are deployed */
  region: "ap-northeast-1",

  /**
   * S3 Access Point alias for FSx for ONTAP volume.
   * Find this in: AWS Console → FSx → File Systems → S3 Access Points tab
   * Format: "<ap-name>-<random>-s3alias"
   *
   * For DemoMode (no FSx for ONTAP): use a regular S3 bucket name.
   * Leave empty to show "No files" in the Files tab.
   */
  s3ApAlias: "",

  /**
   * Step Functions state machine ARN.
   * Find this in: AWS Console → Step Functions → State Machines
   *
   * If you haven't deployed a UC pattern yet, create a test machine:
   *   make sfn-test-create
   * Then paste the ARN here.
   */
  stateMachineArn:
    "arn:aws:states:ap-northeast-1:123456789012:stateMachine:placeholder",

  // ─── Optional (defaults work for sandbox) ──────────────────────────────

  /**
   * IAM scope for Step Functions.
   * Sandbox: "*" (all state machines)
   * Production: restrict to specific ARN pattern
   */
  stateMachineResourceScope: "*",

  /**
   * IAM scope for S3 AP access.
   * Sandbox: all access points in all regions
   * Production: restrict to specific AP ARN
   *
   * DemoMode (regular S3 bucket): S3 AP ARNs won't work for regular buckets.
   * Add bucket ARNs explicitly:
   *   "arn:aws:s3:::your-bucket-name",
   *   "arn:aws:s3:::your-bucket-name/*",
   *
   * These ARNs are the resource scope of the Storage Browser's direct path to S3, which
   * `amplify/direct-s3-access.ts` grants per Cognito group. **Who** may write is the role
   * (`contributor`, `storage-admin`); **where** is this list. Left as the wildcard, a
   * contributor writes to any access point in the account, including one belonging to
   * another group -- the group-to-access-point routing in `groupApMapping` is applied by
   * the Lambda handlers and does not reach this path. Narrow it before production.
   *
   * Two things happen to what you put here, both in `amplify/direct-s3-access.ts`:
   *
   *   A `*` in the region or account position is replaced by the deployment's own, so the
   *   default below grants this account rather than every account. Read the synthesised
   *   policy if you want to see it; `scopeS3ApArns` is the function.
   *
   *   An access-point *name* left as `*` is refused at synth once `groupApMapping` routes
   *   any group to its own access point, because on this path that wildcard cancels the
   *   isolation the mapping asks for.
   */
  s3ApResourceArns: [
    "arn:aws:s3:*:*:accesspoint/*",
    "arn:aws:s3:*:*:accesspoint/*/object/*",
    // DemoMode: uncomment and set your bucket name
    // "arn:aws:s3:::your-demo-bucket",
    // "arn:aws:s3:::your-demo-bucket/*",
  ],

  /**
   * Group-based S3 AP routing.
   * Maps Cognito groups to S3 AP aliases (each with a different File System Identity).
   * See interface definition above for examples.
   * Empty = disabled (all users share the default s3ApAlias).
   */
  groupApMapping: {},

  /**
   * Path prefixes per Cognito group, independent of the access point routing.
   *
   * Commented out on purpose: while it is absent, the prefixes are derived from
   * `groupApMapping` exactly as before. Uncomment when the two need to differ --
   * separate access points sharing one prefix, or one access point with the
   * prefixes doing the separating.
   *
   * A group absent from this map is unrestricted, so list every group you intend
   * to confine. `storage-admin` is exempt regardless, unless it also holds
   * `external`.
   *
   *   groupPathPrefixes: {
   *     "team-a": ["teams/a/", "shared/"],
   *     "partner-acme": ["exchange/acme/"],
   *   },
   */

  /**
   * How accounts are created, and what signing in requires.
   */
  signIn: {
    /**
     * Whether anybody may register themselves with a verified email address.
     *
     * **False.** The sign-in page is public, so leaving this open means anybody who
     * reaches it can create an account. Accounts exist because somebody created them,
     * which is what makes the audit trail worth reading — every account traces back to
     * whoever issued it.
     *
     * Create accounts, including for outside members, deliberately:
     *
     *   aws cognito-idp admin-create-user --user-pool-id <pool> \
     *     --username partner@example.net \
     *     --user-attributes Name=email,Value=partner@example.net Name=email_verified,Value=true
     *
     * Set it to true only for a deployment that wants open registration — a public
     * demo being the case that does.
     */
    selfSignUpEnabled: false,

    /**
     * Multi-factor authentication: "OFF", "OPTIONAL" or "REQUIRED".
     *
     * "OPTIONAL" is what shipped, and it means each user decides — so it is "OFF"
     * for everyone who does not go looking for it. Use "REQUIRED" when MFA needs to
     * be true of every session rather than available.
     */
    mfa: "OPTIONAL",
  },

  /**
   * Emit the role-based AppSync authorization rules.
   *
   * **True.** Writes require `contributor` or `storage-admin`; the audit trail requires
   * `auditor` or `storage-admin`. Reading, previewing, downloading and searching stay
   * open to any signed-in user.
   *
   * The rules name Cognito groups, and a user holding none matches none of them — so a
   * user who has not been granted a role can browse but not write. That is the intended
   * state, and it is the state five administrative endpoints have always been in: they
   * require `storage-admin` regardless of this setting, so a deployment has never been
   * fully usable until somebody granted a group.
   *
   * On a new deployment, grant yourself a role before signing in:
   *
   *   make portal-grant-roles ARGS='--apply --assign you@example.com=storage-admin,internal'
   *
   * Then sign out and in again. Groups travel in the ID token, so a session opened
   * before the grant does not carry it — this is also why granting a role to somebody
   * already signed in does not take effect until they re-authenticate.
   *
   * Setting it to false makes `fileMutation` and `folderMutation` accept any signed-in
   * user, which means any of them can delete anything. Only useful for a demo where
   * nobody is going to be granted roles at all.
   */
  enforceRoles: true,

  /**
   * Limits applied to a caller holding the `external` scope, whatever their role.
   *
   * `external` means a member with no Windows or UNIX account on the file system,
   * identified only by an email address. Both settings below are about where data
   * goes rather than who may call what, which is why they are here and not in the
   * AppSync rules.
   */
  externalDefaults: {
    /**
     * Whether outside members may use the AI endpoints (summarise, extract text,
     * ask about a file, detect labels, analyse text, semantic search).
     *
     * False sends nothing from their files to a model. Turn it on only when the
     * data an outside member can reach is cleared for that, and note the calls are
     * billed per token.
     */
    aiEnabled: false,

    /**
     * Whether outside members may mint share links (presigned URLs and QR codes),
     * decided per role.
     *
     * There is no universal answer, so this is left to the organisation. A share
     * link is a bearer credential: it works without AWS credentials until it
     * expires, so whoever the recipient forwards it to has the same access.
     *
     * A role absent from this map is denied. `{}` therefore denies everyone, which
     * is the shipped default.
     *
     *   shareLinksByRole: {
     *     viewer: false,        // may read, may not redistribute
     *     contributor: true,    // exchanging files with your side is the point
     *     "storage-admin": true,
     *   },
     */
    shareLinksByRole: {},
  },

  /**
   * Bedrock Knowledge Base ID.
   * Find in: AWS Console → Bedrock → Knowledge Bases → ID column
   * Leave empty to disable full-text search.
   */
  bedrockKbId: "",

  /**
   * Bedrock Guardrail ID and version for PII detection/masking.
   * Create in: AWS Console → Bedrock → Guardrails → Create guardrail
   * Leave empty to disable guardrails (AI responses unfiltered).
   *
   * Recommended configuration:
   *   - PII: ANONYMIZE for EMAIL, PHONE; BLOCK for SSN, CREDIT_CARD
   *   - Content: BLOCK SEXUAL/VIOLENCE at HIGH strength
   */
  bedrockGuardrailId: "",
  bedrockGuardrailVersion: "DRAFT",

  // ─── VPC & ONTAP (required for Admin/DataProtection/ARP features) ──────

  /**
   * VPC where FSx for ONTAP ENIs reside.
   * Find: aws fsx describe-file-systems --file-system-ids <fs-id> \
   *         --query "FileSystems[0].{VpcId:VpcId,SubnetIds:SubnetIds}"
   * Leave empty to deploy without VPC (admin panels show "ONTAP connection required").
   */
  vpcId: "",
  vpcSubnetIds: [],
  vpcSecurityGroupIds: [],

  /**
   * Route tables associated with vpcSubnetIds. Required whenever vpcId is set.
   *
   * Creates a DynamoDB gateway endpoint, which the VPC functions need to reach
   * the containment block ledger. A Lambda ENI has no public IP, so a subnet
   * whose default route is an internet gateway gives the function no egress at
   * all — interface endpoints cover Secrets Manager, but DynamoDB has no path
   * unless one is added. Gateway endpoints are not billed.
   *
   * Left unset, containment still works but nothing expires: blocks land on the
   * cluster and the scheduled sweep never sees them. The response reports
   * expiryTracked: false rather than implying the block will lift itself.
   *
   *   aws ec2 describe-route-tables \
   *     --filters "Name=association.subnet-id,Values=<subnet-id>" \
   *     --query "RouteTables[].RouteTableId" --output text
   *
   * Deploying with vpcId set and this empty is refused, because the result looks
   * complete while expiry does not run. Set allowNoBlockExpiry to accept that.
   */
  vpcRouteTableIds: [],
  allowNoBlockExpiry: false,

  /**
   * Bucket used by the S3 Object Lock panel in Data Protection.
   *
   * Left empty, the panel reports that no bucket is configured rather than
   * failing — the handler already treats an empty value as "feature off".
   */
  s3ObjectLockBucket: "",

  /**
   * Expiry applied to a containment block when the caller does not name one.
   *
   * A bounded default matters more than a long one. An expiry that has to be
   * requested is an expiry that gets forgotten, and a block nobody remembers is
   * indistinguishable from an outage.
   */
  defaultBlockTtlHours: 24,

  /**
   * Longest expiry a single request may ask for. 0 removes the ceiling.
   *
   * 30 days, chosen on which instrument is right rather than which number is
   * safe. An ONTAP deny rule covers one SVM; a principal that must stay locked
   * out longer than an investigation runs should be disabled in the directory,
   * which covers the whole estate and is visible to whoever owns the account
   * lifecycle.
   *
   * Note what this does not catch: someone typing 90 meaning days gets 90 hours,
   * and no ceiling detects that. What catches it is `expiresAt` in the response.
   * Raise this if your incident practice needs longer holds, or set 0 and bound
   * it elsewhere.
   *
   * Must be at or above defaultBlockTtlHours, or synth fails — otherwise every
   * block that did not name its own expiry would be refused for exceeding a
   * limit the caller never set.
   */
  maxBlockTtlHours: 24 * 30,

  /**
   * How often the sweep looks for blocks whose expiry has passed.
   *
   * This bounds how long a block outlives its expiry, so it is a coarser control
   * than it appears: at 60, "expires in 1h" can mean up to two. It also sets the
   * period of both sweep alarms, so raising it slows detection of a sweep that
   * has stopped running.
   */
  blockSweepIntervalMinutes: 15,

  /**
   * Address to notify when the containment sweep fails or stops running.
   *
   * Left empty, the alarms still exist and are visible in the console, but the
   * SNS topic has no subscriber so nothing reaches a person. Blocks not expiring
   * is a silent condition, which is the reason the alarms exist at all.
   */
  alarmEmail: "",

  /**
   * ONTAP management LIF IP address.
   * Find: aws fsx describe-file-systems --file-system-ids <fs-id> \
   *         --query "FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]"
   */
  ontapMgmtIp: "",

  /**
   * Secrets Manager secret containing ONTAP credentials.
   * Secret must have: {"username": "fsxadmin", "password": "..."}
   *
   * **Must be the secret for the same file system as `ontapMgmtIp` above.** An account
   * with two file systems has two `fsxadmin` accounts with two passwords, and pairing one
   * cluster's address with the other's credentials is not a configuration that merely
   * fails to connect: ONTAP answers `6691623 "User is not authorized."`, and `fsxadmin`
   * is measured at `max-failed-login-attempts=5` with `lockout-duration=0` — five
   * attempts take the cluster's administrative credential out of service, and waiting
   * does not restore it.
   *
   * Tag the secret so the pair can be checked without anybody logging in:
   *
   *   aws secretsmanager tag-resource --secret-id <secret> \
   *     --tags Key=FileSystemId,Value=fs-0123456789abcdef0
   *
   * Then `make ontap-preflight FS_ID=fs-0123456789abcdef0` verifies it. Without the tag
   * that stage reports SKIP rather than passing, because a pair that authenticates
   * against the wrong cluster is indistinguishable from a correct one until it is tried.
   */
  ontapSecretName: "",

  /** SVM name (default SVM for operations) */
  ontapSvmName: "",

  /** Default volume name for snapshot/lock operations */
  ontapVolumeName: "",
};
