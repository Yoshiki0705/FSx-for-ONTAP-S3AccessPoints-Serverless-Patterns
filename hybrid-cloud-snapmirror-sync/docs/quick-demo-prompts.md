# Amazon Quick Demo Prompts

Amazon Quick / Quick Sight を使ったデモで活用できるプロンプト例・操作シナリオ。
業務判断と次のアクションにつなげるストーリー構成。

---

## Data Freshness (データ鮮度の確認)

- "What is the latest replicated timestamp?"
- "Which records were updated after the last SnapMirror transfer?"
- "Are there files missing required metadata?"
- "Show files added in the last 10 minutes."
- "Is there any replication lag between source and destination?"

## Business Analysis (業務分析)

- "Show the trend of inspection results by site."
- "Which location has the highest anomaly count?"
- "Summarize recent changes in the replicated dataset."
- "Compare this week's data volume with last week."
- "Which departments have the most active file creation?"

## Operational Action (業務アクション)

- "Which records require review?"
- "Create a summary for the operations team."
- "What should be checked before the next refresh?"
- "Flag any files that haven't been updated in 30 days."
- "Generate a report of today's data sync activity."
- "Which operational team should review the highest-priority items?"
- "Create a short summary for the daily operations meeting."
- "List items that require human review."

## Source-of-Truth Awareness (正本データの意識)

- "Which dataset is the replicated copy, and what is the source-of-record timestamp?"
- "Show the latest business metrics with the replication timestamp."
- "Which insights are based on data replicated after the last SnapMirror update?"
- "Which records changed since the last replication cycle?"
- "Show the latest replicated timestamp and dashboard refresh timestamp."
- "Summarize anomalies by site and severity."

---

## Demo Storyline Example

### Scenario: Manufacturing Quality Inspection

> A manufacturing operations team needs to monitor newly generated inspection files
> from an on-premises ONTAP system. The data is replicated to FSx for ONTAP using
> SnapMirror. Amazon Quick provides a business-facing UI to identify anomalies,
> summarize recent changes, and guide the next operational action.

**Step 1**: "What changed since the last sync?"
→ Quick shows newly replicated inspection files

**Step 2**: "Which inspections failed?"
→ Quick highlights anomalies with natural language summary

**Step 3**: "Create a report for the quality manager."
→ Quick generates a formatted summary with citations to source files

**Step 4**: "What action should we take?"
→ Quick recommends review of specific records based on patterns

---

## Key Principle

> The goal is not to demonstrate a dashboard.
> The goal is to demonstrate how existing enterprise file data can become
> **actionable** — leading to a decision, an action, or an outcome —
> without first moving it into a separate data lake.

This aligns with the principle that generative AI and BI value comes from
connecting data to business outcomes, not from building another visualization.


## Safe Usage Prompts

- "Is this dashboard showing source-of-record data or replicated data?"
- "What is the latest replicated timestamp?"
- "Is the data fresh enough for operational review?"
- "Which insights require human review before action?"
- "What should not be concluded from this dashboard?"

## AI-Safe Interpretation

- "Which assumptions are behind this insight?"
- "Which fields are missing or stale?"
- "Which recommendations require human review?"
- "What data quality issues should be checked first?"
- "Is the replicated data fresh enough for this conclusion?"
