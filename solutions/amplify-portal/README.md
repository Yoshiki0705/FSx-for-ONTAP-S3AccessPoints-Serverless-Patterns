# FSx for ONTAP File Portal — Amplify Gen2

Web-based file portal for browsing, processing, and viewing results on FSx for ONTAP volumes via S3 Access Points.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Amplify Gen2                                           │
│  ┌──────────┐  ┌─────────────────────────────────────┐  │
│  │ Cognito  │  │ AppSync GraphQL API                 │  │
│  │ Auth     │  │  startProcessing → Step Functions   │  │
│  │ +MFA     │  │  getJobStatus → Step Functions      │  │
│  │ +SAML    │  │  listFiles → Lambda → S3 AP         │  │
│  └──────────┘  └──────────────┬──────────────────────┘  │
│                               │                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ CDK Custom Stack                                    │ │
│  │  - Step Functions HTTP data source (IAM role)       │ │
│  │  - ListFiles Lambda (Python 3.12, ARM64, VPC-ext)   │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
┌──────────────────┐          ┌─────────────────────────┐
│ Step Functions   │          │ FSx for ONTAP           │
│ (existing UC     │          │ S3 Access Point         │
│  pattern ASL)    │          │ (Internet-origin)       │
└──────────────────┘          └─────────────────────────┘
```

## Prerequisites

- Node.js 18.17+ (required by Amplify Gen2)
- AWS account with Amplify permissions
- (Optional) Deployed UC pattern for Step Functions integration
- (Optional) FSx for ONTAP with S3 AP for file listing

## Quick Start

```bash
# 1. Install dependencies
make install

# 2. Start Amplify sandbox (deploys backend to your AWS account)
make sandbox

# 3. In another terminal, start the dev server
make dev

# 4. Open http://localhost:5173 in your browser
```

The Amplify sandbox creates a personal development environment with:
- Cognito User Pool (sign up with email)
- AppSync GraphQL API
- ListFiles Lambda function

> First-time sandbox deployment takes ~3-5 minutes. Subsequent updates are incremental (~30 seconds).

## Development

| Command | Description |
|---------|-------------|
| `make dev` | Start Vite dev server (frontend only) |
| `make sandbox` | Deploy Amplify backend to personal sandbox |
| `make test` | Run vitest (single execution) |
| `make lint` | ESLint check |
| `make typecheck` | TypeScript type validation |
| `make build` | Production build |
| `make clean` | Remove build artifacts |

## Project Structure

```
amplify-portal/
├── amplify/                    # Amplify Gen2 backend definition
│   ├── backend.ts              # Entry point (defineBackend)
│   ├── auth/resource.ts        # Cognito config (email + SAML/OIDC)
│   ├── data/resource.ts        # AppSync schema + resolvers
│   │   └── resolvers/
│   │       ├── start-processing.js   # HTTP → Step Functions
│   │       ├── get-job-status.js     # HTTP → Step Functions
│   │       └── list-files.js         # Lambda → S3 AP
│   └── custom/
│       └── step-functions.ts   # CDK stack (IAM, Lambda, data sources)
├── src/                        # React frontend
│   ├── main.tsx                # Entry point (Amplify config + Auth)
│   ├── App.tsx                 # Shell (Files / Process / Results tabs)
│   ├── components/
│   │   ├── FileExplorer.tsx    # Browse S3 AP files with pagination
│   │   ├── JobSubmitForm.tsx   # Select pattern + submit job
│   │   └── ResultsViewer.tsx   # Poll status + show output
│   └── index.css               # Minimal styling
├── tests/                      # Frontend tests (vitest)
├── package.json
├── tsconfig.json
├── vite.config.ts
├── Makefile
└── README.md
```

## Configuration

### Connecting to an Existing Step Functions State Machine

After deploying a UC pattern (e.g., `make deploy-uc1` from the repo root):

1. Note the State Machine ARN from the deployment output
2. Set it in `amplify/custom/step-functions.ts` parameter
3. Redeploy sandbox: `make sandbox`

### Connecting to FSx for ONTAP S3 Access Point

1. Create an S3 AP attached to your FSx for ONTAP volume
2. Set the AP alias in the `S3AccessPointAlias` parameter
3. Redeploy sandbox

### DemoMode (No FSx for ONTAP Required)

For development without FSx for ONTAP:
- The ListFiles Lambda returns empty results if no S3 AP alias is configured
- Step Functions integration works with any deployed state machine
- Use a regular S3 bucket as a stand-in during development

## Authentication

Default: Email + password with optional TOTP MFA.

For enterprise SSO, uncomment the SAML or OIDC section in `amplify/auth/resource.ts` and provide your IdP metadata.

## Relationship to Core Patterns

This portal is an **optional frontend layer**. It does not modify the core patterns:

- Backend Lambda functions (Python) remain in their respective `solutions/industry/*/` directories
- Step Functions ASL workflows are referenced, not copied
- The `shared/` Python modules are unaffected
- All existing `make test-uc*` commands continue to work independently

## Related Documentation

- [File Portal UI Options (Amplify / Nextcloud / Custom)](../../docs/file-portal-amplify-gen2.md)
- [Nextcloud External Storage Setup](../../docs/nextcloud-external-storage-s3ap.md)
- [Demo Mode Guide](../../docs/demo-mode-guide.md)
- [S3AP Compatibility Notes](../../docs/s3ap-compatibility-notes.md)
