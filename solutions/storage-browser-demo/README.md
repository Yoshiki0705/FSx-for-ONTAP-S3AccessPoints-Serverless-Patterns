# Storage Browser for S3 — FSx for ONTAP S3 AP Demo

A minimal React app demonstrating [Storage Browser for S3](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser) connected to FSx for ONTAP via S3 Access Points.

## What this demonstrates

- Browse FSx for ONTAP volume files from a web browser
- Preview images, videos, and text files
- Upload files (up to 5 GB) and create folders
- Download and delete files
- All while the same files remain accessible via NFS and SMB

## Prerequisites

- An FSx for ONTAP S3 Access Point (Internet origin, Lifecycle = AVAILABLE)
- IAM credentials with `s3:ListBucket`, `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on the AP ARN
- Node.js 18+

## Setup

```bash
npm install
```

Edit `src/StorageBrowserFSxN.tsx` — update the `CONFIG` object:

| Parameter | How to find |
|---|---|
| `s3ApAlias` | `aws fsx describe-s3-access-point-attachments --query '..Alias' --region ap-northeast-1` |
| `region` | Same as your FSx for ONTAP file system |
| `accountId` | `aws sts get-caller-identity --query Account` |

## Running (development)

Two terminals needed:

```bash
# Terminal 1: Start the credentials API (uses your local AWS credentials)
node server/credentials-api.mjs

# Terminal 2: Start the Vite dev server (proxies /api/credentials to port 3001)
npm run dev
# Open http://localhost:5173
```

The credentials API reads from your standard AWS credential chain (`~/.aws/credentials`, env vars, or IAM role). It exposes temporary credentials at `http://localhost:3001/api/credentials` which Vite proxies to the frontend.

**Security**: The credentials server is for local development only. For production, use Cognito Identity Pool or API Gateway + Lambda (see detailed guide).

## Architecture

```
Browser → StorageBrowser component
       → S3 API (SigV4 signed) → S3 AP alias endpoint
       → FSx for ONTAP volume (NFS/SMB coexist)
```

## Detailed guide

- [English](../../docs/en/storage-browser-demo-guide.md)
- [日本語](../../docs/ja/storage-browser-demo-guide.md)

## Related

- [Storage Browser for S3 docs](https://ui.docs.amplify.aws/react/connected-components/storage/storage-browser)
- [FSx for ONTAP S3 AP compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
