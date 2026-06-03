# S3 Access Points for FSx for ONTAP — Dual-Layer Authorization Model

🌐 **Language / 言語**: [日本語](s3ap-authorization-model.md) | [English](s3ap-authorization-model.en.md)

## Overview

Amazon S3 Access Points for FSx for ONTAP employs a **dual-layer authorization model**. For a request via the S3 API to succeed, **both** the AWS-side authorization and the file-system-side authorization must permit it.

> **Design Principle**: The S3 API does not strip file system semantics. Even when accessed through an S3 Access Point, file access permissions on the volume continue to apply.

## Authorization Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    S3 API Request                            │
│            (GetObject / PutObject / ListObjectsV2)          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: AWS-side Authorization                            │
│                                                             │
│  All of the following policies are evaluated and ALL must   │
│  permit:                                                    │
│  • IAM identity-based policy (caller's permissions)         │
│  • S3 Access Point resource policy                          │
│  • VPC endpoint policy (if VPC-restricted)                  │
│  • Service Control Policies (SCP)                           │
│                                                             │
│  → If any denies → AccessDenied                             │
└─────────────────────────┬───────────────────────────────────┘
                          │ (all permit)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: File-system-side Authorization                    │
│                                                             │
│  Authorized using the file system ID associated with the    │
│  Access Point:                                              │
│  • UNIX identity (UID) → UNIX security style volumes        │
│    - Controlled by mode-bits or NFSv4 ACLs                  │
│  • Windows identity (domain\user) → NTFS style volumes      │
│    - Controlled by Windows ACLs                             │
│                                                             │
│  → The file system user's permissions determine access level│
└─────────────────────────────────────────────────────────────┘
```

## Layer 1: AWS-side Authorization

### Evaluated Policies

| Policy Type | Description | Configuration Location |
|-------------|-------------|----------------------|
| IAM identity-based policy | Permissions of the caller (e.g., Lambda Role) | IAM Console |
| S3 Access Point resource policy | Resource policy on the AP itself | `s3control put-access-point-policy` |
| VPC endpoint policy | Endpoint policy for VPC-restricted APs | VPC Console |
| Service Control Policies | Organization-level controls | AWS Organizations |

### IAM Policy ARN Format

S3 Access Points for FSx for ONTAP uses a different ARN format from regular S3 bucket ARNs:

```json
{
  "Effect": "Allow",
  "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
  "Resource": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap"
},
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject"],
  "Resource": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap/object/*"
}
```

> **Note**: Using the S3 AP alias (`xxx-ext-s3alias`) in the `arn:aws:s3:::` format will not be recognized by IAM. Always use the `arn:aws:s3:{region}:{account}:accesspoint/{name}` format.

## Layer 2: File-system-side Authorization

### Role of the File System ID

The file system ID specified when creating the S3 Access Point is used for authorization of all S3 API requests:

- **Read-only user** associated → Only read requests are authorized; writes are blocked
- **Read-write user** associated → Both read and write requests are authorized

### Security Style Mapping

| Volume Security Style | ID Type Used | Permission Control Method |
|-----------------------|--------------|--------------------------|
| UNIX | UNIX identity (UID) | mode-bits / NFSv4 ACLs |
| NTFS | Windows identity (domain\user) | Windows ACLs |

### Important Behavioral Characteristics

1. **No impact on NFS/SMB access**: Attaching an S3 Access Point does not change existing NFS/SMB access in any way. AP policy restrictions apply only to requests via the AP.

2. **Block Public Access**: S3 APs attached to FSx for ONTAP always have Block Public Access enabled, and this cannot be changed.

3. **MISCONFIGURED state**: If the file system ID can no longer be resolved, the AP transitions to a `MISCONFIGURED` state. Amazon FSx periodically checks and automatically returns it to `AVAILABLE` when the issue is resolved.

## Least-Privilege Design Guidelines

To apply the principle of least privilege, access must be restricted at **both layers**:

### Layer 1 Restriction Example

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::123456789012:role/ProcessingLambdaRole"},
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap/object/*"
      ],
      "Condition": {
        "StringEquals": {"aws:PrincipalOrgID": "o-xxxxx"}
      }
    }
  ]
}
```

### Layer 2 Restriction Example

- Create a dedicated user with read permissions only on the target directories
- Avoid using root (UID 0) (as it grants access to all files)
- In NTFS environments, use a service account with minimal AD group membership

## Application in This Project

The 28 UC + 6 FC patterns in this repository adopt the following design:

| Component | Layer 1 Design | Layer 2 Design |
|-----------|---------------|---------------|
| Discovery Lambda | ListBucket + GetObject only | UNIX user with read permissions on target volumes |
| Processing Lambda | GetObject only (input reading) | Same as above |
| Output Lambda (FSXN_S3AP mode) | PutObject added | User with write permissions on the output directory |

## Troubleshooting

| Symptom | Possible Cause | Verification Point |
|---------|---------------|-------------------|
| AccessDenied despite IAM permission | Insufficient file system ID permissions | Check UNIX/Windows ID file/directory permissions associated with the S3 AP |
| ListBucket succeeds but GetObject returns AccessDenied | File ACL / export policy / security style mismatch | Check effective permissions on the target file with `ls -la` (UNIX) or `icacls` (NTFS) |
| PutObject fails | Insufficient directory write permissions | Check write permissions on the parent directory. If the file system ID is read-only, writes are not possible |
| Timeout from VPC Lambda | Accessing Internet Origin AP via S3 Gateway EP | Place Lambda outside VPC, or route via NAT Gateway |
| MISCONFIGURED state | File system ID cannot be resolved | Verify that the UNIX UID exists or that the Windows user is active in AD |
| AccessDenied on specific directories only | ONTAP export policy restrictions | Check SVM export policy rules (NFS export and S3 AP are different paths but share the same volume permissions) |

### Verification Command Examples

> **Note**: All commands below are read-only for troubleshooting purposes. They do not make any changes to the environment.

```bash
# === AWS CLI ===

# 1. Check S3 AP resource policy
aws s3control get-access-point-policy \
  --account-id <ACCOUNT_ID> \
  --name <AP_NAME>

# 2. Verify permissions with IAM Policy Simulator
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<ACCOUNT_ID>:role/<LAMBDA_ROLE> \
  --action-names s3:GetObject s3:ListBucket \
  --resource-arns "arn:aws:s3:<REGION>:<ACCOUNT_ID>:accesspoint/<AP_NAME>/object/*"

# 3. Check AccessDenied events in CloudTrail
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetObject \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ) \
  --query 'Events[?contains(CloudTrailEvent, `AccessDenied`)]'

# 4. Check filesystem identity associated with S3 AP
aws fsx describe-data-repository-associations \
  --query 'Associations[?AssociationType==`S3_ACCESS_POINT`].{Name:ResourceARN,Identity:S3}'

# === ONTAP CLI ===

# 5. ONTAP side: Check ACL / permissions on target path (UNIX)
# Via SSH or ONTAP CLI
vserver security file-directory show -vserver <SVM_NAME> -path <PATH>

# === VPC / Network ===

# 6. Check VPC Endpoint policy
aws ec2 describe-vpc-endpoints \
  --filters Name=service-name,Values=com.amazonaws.<REGION>.s3 \
  --query 'VpcEndpoints[*].{Id:VpcEndpointId,Policy:PolicyDocument}'
```

## References

- [Managing access point access — Amazon FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- [Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Enabling AI-powered analytics on enterprise file data (AWS Storage Blog)](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/)
