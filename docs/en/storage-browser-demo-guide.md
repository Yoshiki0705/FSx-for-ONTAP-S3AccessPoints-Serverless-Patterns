# Storage Browser for S3 + FSx for ONTAP S3 Access Points — Demo Guide

Browse, preview, download, and upload files on your FSx for ONTAP volumes directly from a React web application using [Storage Browser for S3](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser).

---

## Overview

Storage Browser for S3 is an Amplify UI React component (GA December 2024) that provides a file explorer experience against S3 data. Because FSx for ONTAP S3 Access Points expose standard S3 API operations (`ListObjectsV2`, `GetObject`, `PutObject`, `DeleteObject`), Storage Browser works with FSx for ONTAP S3 AP aliases the same way it works with standard S3 buckets.

### What you get

| Feature | Storage Browser provides |
|---|---|
| File listing & folder navigation | Paginated listing with breadcrumb |
| File preview | Images, videos, text files rendered in-browser |
| File download | Direct download via Presigned URL |
| File upload | Drag-and-drop, up to 5 GB (FSx for ONTAP S3 AP limit) |
| Copy & delete | Single file or entire folder |
| Folder creation | Create new folders (S3 prefix creation) |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (React + @aws-amplify/ui-react-storage)            │
│  ┌──────────────────────────────────────────────────┐       │
│  │  StorageBrowser component                        │       │
│  │  - createManagedAuthAdapter (IAM credentials)    │       │
│  │  - S3 Client → ListObjectsV2 / GetObject / etc.  │       │
│  └──────────────────┬───────────────────────────────┘       │
└─────────────────────┼───────────────────────────────────────┘
                      │ HTTPS (SigV4)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  S3 Access Point endpoint                                   │
│  Alias: xxx-ext-s3alias                                     │
│  Network Origin: Internet                                   │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  FSx for ONTAP Volume                                       │
│  - Files accessible via NFS/SMB AND S3 AP simultaneously    │
│  - FileSystemIdentity enforces ONTAP-level permissions      │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Item | Requirement |
|---|---|
| FSx for ONTAP file system | AVAILABLE, with at least one volume mounted (junction path) |
| S3 Access Point | Attached to the volume, Internet origin, Lifecycle = AVAILABLE |
| IAM credentials | User or role with `s3:ListBucket`, `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on the AP ARN |
| Node.js | v18+ |
| Package manager | npm or yarn |

---

## Three Authentication Methods

Storage Browser supports three methods for providing credentials to end users. Choose based on your access control model:

### Method 1: Amplify Auth (Cognito)

Best for: Customer/partner-facing portals with social or enterprise login.

```typescript
import { Amplify } from 'aws-amplify';
import { createAmplifyAuthAdapter, createStorageBrowser } from '@aws-amplify/ui-react-storage/browser';
import '@aws-amplify/ui-react-storage/styles.css';
import config from './amplify_outputs.json';

Amplify.configure(config);

export const { StorageBrowser } = createStorageBrowser({
  config: createAmplifyAuthAdapter(),
});
```

**Note**: Requires Amplify Storage configured with the S3 AP alias as the bucket name in `amplify/storage/resource.ts`. This is currently not natively supported by Amplify Storage category (FR-6), so use Method 2 instead.

### Method 2: Managed Auth Adapter (Custom Credentials) — Recommended for S3 AP

Best for: FSx for ONTAP S3 AP use cases where you manage IAM credentials yourself.

```typescript
import { createManagedAuthAdapter, createStorageBrowser } from '@aws-amplify/ui-react-storage/browser';
import '@aws-amplify/ui-react-storage/styles.css';

const S3_AP_ALIAS = 'your-ap-alias-ext-s3alias'; // Replace with your S3 AP alias

export const { StorageBrowser } = createStorageBrowser({
  config: createManagedAuthAdapter({
    credentialsProvider: async () => {
      // Provide temporary credentials (e.g., from Cognito Identity Pool, STS AssumeRole)
      const response = await fetch('/api/credentials');
      const creds = await response.json();
      return {
        credentials: {
          accessKeyId: creds.accessKeyId,
          secretAccessKey: creds.secretAccessKey,
          sessionToken: creds.sessionToken,
          expiration: new Date(creds.expiration),
        },
      };
    },
    region: 'ap-northeast-1', // Must match the S3 AP region
    accountId: '123456789012', // Your AWS account ID
    registerAuthListener: (onAuthStateChange) => {
      // Call onAuthStateChange() when auth state changes (e.g., logout)
    },
  }),
});
```

**Key parameter**: The `accountId` and `region` tell the SDK where to route S3 API calls. The S3 AP alias is passed as the bucket name in the `listLocations` handler (see Custom Location Provider below).

### Method 3: S3 Access Grants (Enterprise Scale)

Best for: Large organizations with IAM Identity Center + S3 Access Grants.

This method uses `GetDataAccess` and `ListCallerAccessGrants` APIs. Not covered in this guide — see [AWS documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/setup-storagebrowser.html).

---

## Quick Start (Method 2)

### 1. Create the project

```bash
npm create vite@latest storage-browser-fsxn -- --template react-ts
cd storage-browser-fsxn
npm install @aws-amplify/ui-react-storage aws-amplify
npm install -D @types/react
```

### 2. Configure the Storage Browser component

Create `src/StorageBrowserFSxN.tsx`:

```tsx
import { createManagedAuthAdapter, createStorageBrowser } from '@aws-amplify/ui-react-storage/browser';
import '@aws-amplify/ui-react-storage/styles.css';

// ===== CONFIGURATION — Update these values =====
const CONFIG = {
  // Your FSx for ONTAP S3 AP alias (from: aws fsx describe-s3-access-point-attachments)
  s3ApAlias: 'your-ap-alias-ext-s3alias',
  // AWS region where the S3 AP is located
  region: 'ap-northeast-1',
  // Your AWS account ID
  accountId: '123456789012',
};
// ===== END CONFIGURATION =====

export const { StorageBrowser } = createStorageBrowser({
  config: createManagedAuthAdapter({
    credentialsProvider: async () => {
      // For demo: use environment credentials or a backend /api/credentials endpoint
      // For production: use Cognito Identity Pool or STS AssumeRole with web identity
      const response = await fetch('/api/credentials');
      const creds = await response.json();
      return {
        credentials: {
          accessKeyId: creds.accessKeyId,
          secretAccessKey: creds.secretAccessKey,
          sessionToken: creds.sessionToken,
          expiration: new Date(creds.expiration),
        },
      };
    },
    region: CONFIG.region,
    accountId: CONFIG.accountId,
    registerAuthListener: () => {},
  }),
});
```

### 3. Custom Location Provider (maps S3 AP alias as a location)

Create `src/locations.ts`:

```typescript
// Define the S3 AP alias as a Storage Browser "location"
export const getLocations = () => ({
  locations: [
    {
      bucket: 'your-ap-alias-ext-s3alias', // S3 AP alias acts as bucket name
      id: 'fsxn-volume',
      permissions: ['delete', 'get', 'list', 'write'],
      prefix: '',
      type: 'PREFIX' as const,
    },
  ],
});
```

### 4. Render in App.tsx

```tsx
import { StorageBrowser } from './StorageBrowserFSxN';

function App() {
  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: 20 }}>
      <h1>FSx for ONTAP File Portal</h1>
      <StorageBrowser />
    </div>
  );
}

export default App;
```

### 4. Create the S3 AP via CLI (verified syntax)

```bash
# Create JSON input (Internet origin is default when S3AccessPoint block is omitted)
cat <<EOF > create-ap.json
{
    "Name": "my-storage-browser-ap",
    "Type": "ONTAP",
    "OntapConfiguration": {
        "VolumeId": "fsvol-XXXXXXXXXXXXXXXXX",
        "FileSystemIdentity": {
            "Type": "UNIX",
            "UnixUser": {
                "Name": "root"
            }
        }
    }
}
EOF

# Create the access point
aws fsx create-and-attach-s3-access-point \
  --cli-input-json file://create-ap.json \
  --region ap-northeast-1

# Wait for AVAILABLE (poll every 10s)
watch -n 10 "aws fsx describe-s3-access-point-attachments \
  --region ap-northeast-1 \
  --query 'S3AccessPointAttachments[?Name==\`my-storage-browser-ap\`].{Lifecycle:Lifecycle,Alias:S3AccessPoint.Alias}' \
  --output table"
```

**Key learnings from our verification (2026-07-19)**:
- `--cli-input-json` is the reliable way to pass complex structures (positional args are fragile)
- Omitting `S3AccessPoint` block → Internet origin (default). To restrict to VPC, add `"S3AccessPoint": {"VpcConfiguration": {"VpcId": "vpc-XXX"}}`
- WINDOWS identity requires AD DC reachable from SVM (otherwise: "Failed to lookup the provided user in ONTAP")
- UNIX identity (e.g., `root`) works without AD — simplest for demos

### 5. Run and verify

```bash
npm run dev
# Open http://localhost:5173
```

---

## Parameter Reference

| Parameter | Where to find | Example |
|---|---|---|
| `s3ApAlias` | `aws fsx describe-s3-access-point-attachments --query 'S3AccessPointAttachments[].S3AccessPoint.Alias'` | `myap-abc123-ext-s3alias` |
| `region` | Same region as your FSx for ONTAP file system | `ap-northeast-1` |
| `accountId` | `aws sts get-caller-identity --query Account` | `123456789012` |
| `credentials` | Cognito Identity Pool `getCredentialsForIdentity` or STS `AssumeRole` | Temporary session credentials |

---

## IAM Policy (Minimum Required)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/your-ap-name",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/your-ap-name/object/*"
      ]
    }
  ]
}
```

**Note**: Use the S3 AP ARN format (`arn:aws:s3:{region}:{account}:accesspoint/{name}`), not the bucket ARN format.

---

## Production Deployment Considerations

### Credentials Backend

Do NOT embed AWS credentials in frontend code. Use one of:

| Method | How |
|---|---|
| Cognito Identity Pool | Federated identity → temporary STS credentials scoped to S3 AP |
| API Gateway + Lambda | Backend endpoint returns temporary credentials via STS AssumeRole |
| Amplify Auth | If FR-6 (Amplify Storage + S3 AP) is resolved, direct Amplify flow |

### S3 AP Resource Policy

For production, add a resource policy to restrict access:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/StorageBrowserUserRole"
      },
      "Action": ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/your-ap-name",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/your-ap-name/object/*"
      ]
    }
  ]
}
```

### FileSystemIdentity Considerations

| Identity Type | Use case | Notes |
|---|---|---|
| UNIX (uid/gid) | NFS-primary volumes, Linux workloads | Simplest setup, no AD required |
| WINDOWS (AD user) | SMB-primary volumes, enterprise with AD | Requires SVM AD-join, enforces NTFS ACLs |

---

## Limitations & Workarounds

| Limitation | Details | Workaround |
|---|---|---|
| Upload size | 5 GB max per PutObject (FSx for ONTAP S3 AP constraint) | Use multipart upload for larger files (Storage Browser handles this automatically up to 5 GB) |
| S3 AP public roadmap | Storage Browser lists "Support for S3 Access Points" as under evaluation | Works today via Method 2 (managed auth adapter with AP alias as bucket) |
| Presigned URL docs | Listed as "Not supported" in FSx docs | Works (client-side SigV4, executes as standard GetObject). See [compatibility notes](../s3ap-compatibility-notes.en.md) |
| S3 Access Grants | Not tested with FSx for ONTAP S3 AP | Use Method 2 (managed auth) instead |

---

## Related Resources

- [Storage Browser for S3 — Amplify UI docs](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser)
- [Setting up Storage Browser — S3 User Guide](https://docs.aws.amazon.com/AmazonS3/latest/userguide/setup-storagebrowser.html)
- [FSx for ONTAP S3 AP compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [Using access points with AWS services](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)
- [AWS Storage Blog: S3 AP + AD + Quick Suite](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/)
