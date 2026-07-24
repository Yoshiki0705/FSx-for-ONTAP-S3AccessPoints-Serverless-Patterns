# AI Features Quick Start — File Portal

Try Bedrock Q&A, Rekognition image analysis, Athena SQL, and more from the File Portal UI in under 15 minutes.

---

## Prerequisites

| Item | How to verify/set up |
|---|---|
| FSx for ONTAP S3 AP (or regular S3 bucket for DemoMode) | `aws fsx describe-s3-access-point-attachments --query '...Alias'` |
| Bedrock model access | AWS Console → Bedrock → Model access → Enable `amazon.nova-lite-v1:0` |
| Glue Data Catalog (for Athena) | At least one database + table registered via Crawler or manually |
| Athena result bucket | Any S3 bucket for query output (S3 AP cannot store Athena results) |

---

## Step 1: Deploy the Portal

```bash
cd solutions/amplify-portal
npm install
cp amplify/portal-config.example.ts amplify/portal-config.ts
# Edit portal-config.ts: set s3ApAlias to your AP alias or bucket name
SKIP_CDK_NAG=1 npx ampx sandbox --once
```

Wait ~4 minutes for deployment. You'll see:
```
✔ Deployment completed
AppSync API endpoint = https://xxx.appsync-api.ap-northeast-1.amazonaws.com/graphql
```

Then start the dev server:
```bash
npm run dev
# Open http://localhost:5173
```

---

## Step 2: Sign Up & Log In

1. Click "Create Account" tab
2. Enter email + password (8+ chars, uppercase, lowercase, digit, special)
3. In a separate terminal, confirm the user:
   ```bash
   USER_POOL_ID=$(python3 -c "import json; print(json.load(open('amplify_outputs.json'))['auth']['user_pool_id'])")
   aws cognito-idp admin-confirm-sign-up --user-pool-id "$USER_POOL_ID" --username "your@email.com" --region ap-northeast-1
   ```
4. Go back to the browser → Sign In tab → log in with your credentials
5. Skip the verification step if prompted

---

## Step 3: Browse Files (All Files)

The sidebar "📂 All Files" shows your FSx for ONTAP volume contents via S3 AP.

Click folders to navigate. Click file icons:
- 🖼️ → Image preview (fetches presigned URL)
- 📄 → Download (opens presigned URL in new tab)

---

## Step 4: Ask AI About a File (Bedrock Q&A)

1. In "📂 All Files", click any text/CSV file
2. The right panel shows "AI Assistant"
3. Type a question, e.g.: "How many records are in this file?"
4. Press Enter → Bedrock analyzes the file content and responds

**What happens behind the scenes:**
```
Click file → AppSync askAboutFile mutation → Lambda
→ S3 AP GetObject (reads file) → Bedrock Converse API (Nova Lite)
→ Answer returned to UI
```

---

## Step 5: Detect Objects in Images (Rekognition)

1. Navigate to a folder containing images (.jpg, .png, etc.)
2. Click the 🖼️ icon → image preview popover appears
3. Click "Detect Objects" button
4. Rekognition labels appear as colored tags below the image

---

## Step 6: Run SQL Queries (Athena)

1. Click "📊 Analytics" in the sidebar
2. Set the database name (e.g., `fsxn_athena_verification`)
3. Type a SQL query, e.g.:
   ```sql
   SELECT * FROM benchmark LIMIT 10
   ```
4. Click "Run Query" → results appear in a table

**Required setup:** Set `ATHENA_WORKGROUP` and `ATHENA_OUTPUT_LOCATION` environment variables in the Lambda. Without these, queries will fail with "No output location provided."

---

## Step 7: Upload Files

1. Click "📤 Upload" in the sidebar
2. Drag and drop files, or click to browse
3. Files are uploaded via PUT Presigned URL directly to FSx for ONTAP S3 AP
4. Uploaded files are immediately visible via NFS/SMB on the same volume

---

## Cleanup

```bash
cd solutions/amplify-portal
SKIP_CDK_NAG=1 npx ampx sandbox delete --yes
```

---

## Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| "Loading..." forever on All Files | S3 AP alias not configured | Edit `portal-config.ts` → set `s3ApAlias` |
| Bedrock returns error | Model not enabled | AWS Console → Bedrock → Model access → Enable Nova Lite |
| Athena "No output location" | Missing env var | Set `ATHENA_OUTPUT_LOCATION=s3://your-bucket/athena-results/` |
| Image preview shows ⏳ then nothing | Presigned URL issue | Check Lambda logs; verify SigV4 + regional endpoint |
| "User does not exist" on login | User not confirmed | Run `admin-confirm-sign-up` command from Step 2 |

---

## Architecture (all AI features)

```
Browser UI
  → AppSync GraphQL mutation/query
    → Lambda (VPC-external, ARM64, Python 3.12)
      → S3 AP GetObject (read file content)
      → AWS AI Service (Bedrock/Rekognition/Textract/Comprehend)
    → Result returned to browser
```

All Lambda functions:
- **No VPC** required (Internet-origin S3 AP + public AI endpoints)
- **ARM64** (Graviton2) for cost efficiency
- **Python 3.12** with boto3 (SigV4 + regional endpoint)
- **IAM**: least-privilege per function (s3:GetObject + specific AI action)

---

## Related

- [Production Deployment Guide](./amplify-hosting-production-guide.md)
- [Storage Browser Demo](./storage-browser-demo-guide.md)
- [S3 AP Compatibility Notes](../s3ap-compatibility-notes.en.md)
