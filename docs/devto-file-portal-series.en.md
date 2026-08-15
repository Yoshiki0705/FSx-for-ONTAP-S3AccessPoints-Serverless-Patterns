# File portal article series plan

🌐 **Language / 言語**: [日本語](devto-file-portal-series.md) | English

The shape of the file portal series on dev.to. It is a **separate series** from the S3 AP
serverless patterns; the reasoning and the naming rules are in
[the series structure and tagging policy](./devto-series-cleanup-guide.en.md).

- Series name (EN): `FSx for ONTAP File Portal`
- Series name (JA): `FSx for ONTAP ファイルポータル`
- Tags: `aws`, `amplify`, `fsxforontap`, plus one article-specific tag

## Status

**Parts 1 to 3 are published.** The three articles that had been in the S3 AP series were
moved into this one on 2026-08-15 (their `series` and `tags` changed to the definitions
above). The dev.to widget now reads `FSx for ONTAP File Portal (3 Part Series)`.

| # | Article | Status |
|---|---|---|
| 1 | [Adding a File Portal to FSx for ONTAP S3 Access Points](https://dev.to/aws-builders/adding-a-file-portal-to-fsx-for-ontap-s3-access-points-choosing-between-amplify-gen2-and-887) | Published (EN); Japanese version on Hatena Blog |
| 2 | [Embedding Storage Operations into a File Portal](https://dev.to/aws-builders/embedding-storage-operations-into-a-file-portal-from-arpai-incident-response-to-regulatory-1oih) | Published (EN); Japanese version on Hatena Blog |
| 3 | [Embedding AI Agents into a File Portal](https://dev.to/aws-builders/embedding-ai-agents-into-a-file-portal-from-agentcore-mcp-to-multi-agent-teams-part-3-19m1) | Published (EN); Japanese version on Hatena Blog |
| 4 | Putting ONTAP operations into the portal (174 actions) | **Drafted, not published.** The JA and EN drafts are `drafts/blog/article-file-portal-part4-draft{,.en}.md` (`drafts/` is gitignored, so they cannot be linked) |

**The Japanese series (`FSx for ONTAP ファイルポータル`) has no articles yet.** The Japanese
versions of Parts 1 to 3 are on Hatena Blog and were not posted to dev.to. Starting the
Japanese series there requires posting an article first.

The article plan below lists **candidate themes not yet written**. It does not correspond to
the three published articles.

## Why it is a separate series

The reader of the S3 AP series is building a data processing pipeline out of Lambda and Step
Functions. The reader of the file portal material is looking for **how to let non-administrators
touch files on FSx for ONTAP**, and cares about authorization design, an eight-language UI,
reachability from a phone, and whether to build a portal at all. The only overlap is using
S3 AP as the data path, so combining them leaves half of the series irrelevant to either
reader.

## Article plan

Each article draws on documentation already in the repository. Anything that needs writing
from scratch is marked as such.

| # | Theme | Main sources | Article tag |
|---|---|---|---|
| 1 | **Do you need to build one?** — Transfer Family web apps, Nextcloud, Amplify Gen2 and the option of no frontend, and how to choose | [file-portal-amplify-gen2.en.md](./file-portal-amplify-gen2.en.md), [file-portal-service-gap.en.md](./aws-feature-requests/file-portal-service-gap.en.md) | `architecture` |
| 2 | **Authorization in two layers** — Cognito groups against the S3 AP and ONTAP sides, and the audit trail that connects them | [portal-authorization-design.md](./en/portal-authorization-design.md), [s3ap-authorization-model.en.md](./s3ap-authorization-model.en.md) | `cognito` |
| 3 | **What Amplify Gen2 constrains** — cross-stack data sources, running cdk-nag, sandbox hotswap, the shared Python layer | [amplify-gen2-cdk-patterns.en.md](../solutions/amplify-portal/docs/amplify-gen2-cdk-patterns.en.md), [portal-cdk-quality-gates.md](./agent/portal-cdk-quality-gates.md) | `cdk` |
| 4 | **Holding eight languages with the type system** — `ja.ts` as the source of the type, failing the build on hardcoded strings, theme tokens | [portal-i18n.md](./agent/portal-i18n.md), [CONTRIBUTING-UI.en.md](../solutions/amplify-portal/docs/CONTRIBUTING-UI.en.md) | `i18n` |
| 5 | **Finding the features that had never worked** — the defects live verification turned up (presign defaulting to SigV2, FlexGroup creation against a tiering-enabled aggregate, the rebalance runtime bounds) and the gates that stop them recurring | [verification-results.en.md](../solutions/amplify-portal/docs/verification-results.en.md), [flexgroup-rebalance-verification.en.md](../solutions/amplify-portal/docs/flexgroup-rebalance-verification.en.md) | `testing` |
| 6 | **Handing it over** — reachability from a phone, what to explain at handover, first-line support | [portal-user-guide.md](./en/portal-user-guide.md), [portal-handover-guide.en.md](../solutions/amplify-portal/docs/portal-handover-guide.en.md), [portal-mobile-guide.md](./en/portal-mobile-guide.md) | `webdev` |

## When publishing

- **Use the masked screenshots in `docs/screenshots/`.** To capture new ones, follow
  [the capture and replacement workflow](./screenshots/SCREENSHOT_ADDITION_WORKFLOW.md)
- Any performance or cost figure carries its conditions: Region, ONTAP version, configuration
- For the "had never worked" material, carry it through to the fix **and the gate that stops
  it recurring**. A list of defects on its own does not help the reader
- Other services and products are options suited to different contexts, not opponents. No
  superiority claims
