# DEV.to Series Configuration Cleanup Guide

The FSx for ONTAP S3 Access Points article series on DEV.to needs its series front matter corrected so articles appear in the proper series grouping and order.

## Problem

Articles are not properly grouped into series on DEV.to, causing:
- Articles appearing as standalone posts instead of a connected series
- Readers unable to navigate between related articles
- Permission-Aware RAG articles mixed with S3 AP articles

## Solution: Two Separate Series

### Series 1: "FSx for ONTAP S3 Access Points"

This series covers the serverless patterns repository phases.

**Articles to include (in order):**

| # | Phase | Article Title |
|---|-------|---------------|
| 1 | Phase 1 | Introduction to FSx for ONTAP S3 Access Points |
| 2 | Phase 7 | Deployment Profiles & Production Readiness |
| 3 | Phase 8 | Event-Driven Architecture with FPolicy |
| 4 | Phase 9 | Multi-UC Orchestration Patterns |
| 5 | Phase 10 | Enterprise Workload Examples |
| 6 | Phase 11 | Observability & Cost Optimization |
| 7 | Phase 12 | Partner/SI Delivery Checklist |
| 8 | Phase 13 | Field-Ready Reference Architecture |

### Series 2: "Permission-Aware RAG"

This is a **separate** series for the Permission-Aware RAG system articles.

---

## Step-by-Step Instructions

### 1. Log in to DEV.to

Go to https://dev.to and sign in to your account.

### 2. Navigate to Dashboard

Click your profile icon → **Dashboard** → **Posts**

### 3. Edit each FSx for ONTAP S3 AP article

For each article listed in Series 1 above:

1. Click **Edit** on the article
2. Open the front matter editor (click the `...` menu or edit the raw markdown)
3. Add or update the `series` field:

```yaml
---
title: "Your Article Title"
published: true
series: "FSx for ONTAP S3 Access Points"
tags: aws, serverless, fsxn, s3
---
```

4. Save/Update the article

### 4. Edit each Permission-Aware RAG article

For Permission-Aware RAG articles:

```yaml
---
title: "Your Article Title"
published: true
series: "Permission-Aware RAG"
tags: aws, rag, ai, fsxn
---
```

### 5. Verify series ordering

After updating all articles:

1. Go to any article in the series
2. Look for the series navigation widget (usually at the top or bottom)
3. Verify all articles appear in the correct order
4. The series page URL will be: `https://dev.to/your-username/series`

---

## Important Notes

- **Series name must be EXACTLY the same** across all articles (case-sensitive)
- DEV.to orders articles within a series by publication date (oldest first)
- If you need to reorder, you may need to adjust publication dates
- The series widget appears automatically once 2+ articles share the same series name
- Changes may take a few minutes to reflect on the public-facing pages

## Verification Checklist

- [ ] All 8 FSx for ONTAP S3 AP articles have `series: "FSx for ONTAP S3 Access Points"`
- [ ] All Permission-Aware RAG articles have `series: "Permission-Aware RAG"`
- [ ] No articles have both series tags
- [ ] Series navigation widget appears on each article
- [ ] Articles are in the correct chronological order within each series
