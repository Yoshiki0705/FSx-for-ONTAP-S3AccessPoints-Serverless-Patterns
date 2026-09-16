# File portal article series

🌐 **Language / 言語**: [日本語](devto-file-portal-series.md) | English

The file portal series runs to seven parts: the English versions on dev.to, the Japanese
versions on Hatena Blog. It is a **separate series** from the S3 AP serverless patterns; the
reasoning and the naming rules are in
[the series structure and tagging policy](./devto-series-cleanup-guide.en.md).

- Series name (dev.to): `FSx for ONTAP File Portal`
- Tags: `aws`, `fsxforontap`, plus up to two article-specific tags

## Published articles

| # | Theme | Japanese | English |
|---|---|---|---|
| 1 | Browser access (Amplify Gen 2 or Nextcloud) | [Hatena](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-1-browser-access) | [dev.to](https://dev.to/aws-builders/adding-a-file-portal-to-fsx-for-ontap-s3-access-points-choosing-between-amplify-gen2-and-887) |
| 2 | Ransomware response and WORM retention (ARP/AI, SnapLock, audit logs) | [Hatena](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-2-ransomware-worm) | [dev.to](https://dev.to/aws-builders/embedding-storage-operations-into-a-file-portal-from-arpai-incident-response-to-regulatory-1oih) |
| 3 | AI agent integration (AgentCore over MCP, with a human approving) | [Hatena](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-3-ai-agent-mcp) | [dev.to](https://dev.to/aws-builders/embedding-ai-agents-into-a-file-portal-from-agentcore-mcp-to-multi-agent-teams-part-3-19m1) |
| 4 | Delegating storage operations (182 actions, the buttons I disabled) | [Hatena](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-4-storage-operations) | [dev.to](https://dev.to/aws-builders/putting-fsx-for-ontap-operations-on-a-file-portal-on-aws-182-actions-and-the-design-of-425g) |
| 5 | What the cluster refused (FlexGroup creation, capacity rebalancing) | [Hatena](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-5-what-only-the-cluster-tells-you) | [dev.to](https://dev.to/aws-builders/what-i-learned-driving-fsx-for-ontap-from-a-file-portal-on-aws-flexgroup-creation-capacity-3gkd) |
| 6 | How far ONTAP features reach (qtree, quota, FlexClone measured) | [Hatena](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-6-outside-the-portal) | [dev.to](https://dev.to/aws-builders/what-i-left-off-the-file-portal-on-aws-how-far-fsx-for-ontap-features-reach-and-the-work-handed-hk8) |
| 7 | Comparing the scaffolding tools (Nx Plugin for AWS 1.0 / AWS Blocks / Amplify Gen 2) | [Hatena](https://hakobiya.hatenablog.com/entry/fsxn-file-portal-7-nx-blocks-amplify-gen2) | [dev.to](https://dev.to/aws-builders/what-a-stack-deletion-leaves-behind-nx-plugin-for-aws-10-aws-blocks-and-amplify-gen-2-compared-10fg) |

**The Japanese versions were not posted to dev.to.** The dev.to widget reads
`FSx for ONTAP File Portal (7 Part Series)` across the seven English articles.

## Which document each article draws on

Every article draws on documentation in this repository. The figures and the reproduction
steps are more detailed on the source side than in the article.

| # | Main sources |
|---|---|
| 1 | [UI options](./file-portal-amplify-gen2.en.md), [the gap between portal and service](./aws-feature-requests/file-portal-service-gap.en.md) |
| 2 | [ARP/AI and EMS pitfalls](./agent/pitfalls-arp-ems.md), [SnapLock pitfalls](./agent/pitfalls-snaplock.md) |
| 3 | [GenAI and edge pitfalls](./agent/pitfalls-genai-edge.md) |
| 4 | [Authorization design](./en/portal-authorization-design.md), [authorization model](./en/portal-authorization-model.md) |
| 5 | [FlexGroup pitfalls](./agent/pitfalls-flexgroup.md), [volume lifecycle pitfalls](./agent/pitfalls-volume-lifecycle.md) |
| 6 | [S3 AP and ONTAP pitfalls](./agent/pitfalls-s3ap-ontap.md), [beyond the four features](./en/portal-parity-next-steps.md) |
| 7 | [App foundation choices](./en/scaffolding-and-backend-toolkit-choices.md), [deploy verification and teardown](./en/scaffolding-deploy-verification.md), [the same four features on three foundations](./en/portal-parity-four-features.md) |

## Why it is a separate series

The reader of the S3 AP series is building a data processing pipeline out of Lambda and Step
Functions. The reader of the file portal material is looking for **how to let non-administrators
touch files on FSx for ONTAP**, and cares about authorization design, an eight-language UI,
reachability from a phone, and whether to build a portal at all. The only overlap is using
S3 AP as the data path, so combining them leaves half of the series irrelevant to either
reader.

## When publishing

- **The published article is the source of truth for wording.** Where an article settles on a
  term (the phase axis is "Phase", not "Stage"), bring the repository documents to match
- **Use the masked screenshots in `docs/screenshots/`.** To capture new ones, follow
  [the capture and replacement workflow](./screenshots/SCREENSHOT_ADDITION_WORKFLOW.md)
- Any performance or cost figure carries its conditions: Region, ONTAP version, configuration
- For the "had never worked" material, carry it through to the fix **and the gate that stops
  it recurring**. A list of defects on its own does not help the reader
- Other services and products are options suited to different contexts, not opponents. No
  superiority claims
- The part count ("seven parts") is embedded across the series. Adding one means updating the
  body and the description of every existing article too
