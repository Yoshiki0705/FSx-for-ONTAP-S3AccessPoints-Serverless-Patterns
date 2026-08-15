# dev.to series structure and tagging policy

🌐 **Language / 言語**: [日本語](devto-series-cleanup-guide.md) | English

This defines the series names and tags for the dev.to articles published from this
repository. **A series name has to match exactly**, character for character, case
included. When it does not, the series splits in two and readers lose the in-series
navigation.

## Why they are separate

The S3 AP serverless patterns and the file portal have **different readers**: one is
designing a data processing pipeline, the other is handing a web UI to its users. Putting
them in one series makes half of it irrelevant to either reader. Permission-Aware RAG is
separate for the same reason.

**Languages are separate series too.** dev.to orders a series by publication date and
nothing else, so a Japanese and an English article under one series name interleave, and
both audiences end up skipping every other entry.

## Series definitions

| # | Series name (exact) | Language | Subject |
|---|---|---|---|
| 1 | `FSx for ONTAP S3 Access Points` | EN | S3 AP serverless patterns |
| 2 | `FSx for ONTAP S3 AP サーバーレスパターン集` | JA | Same |
| 3 | `FSx for ONTAP File Portal` | EN | File portal (Amplify Gen2) |
| 4 | `FSx for ONTAP ファイルポータル` | JA | Same |
| 5 | `Permission-Aware RAG` | EN | Permission-Aware RAG |

The article plan for the file portal series is in
[the file portal series plan](./devto-file-portal-series.en.md).

## Tagging policy

dev.to allows **four tags** per article, in a global namespace. When the same product is
tagged differently from one article to the next, a reader following that tag receives only
part of the series.

### The current inconsistency (to be fixed)

Four different tags are in use for the same product across published articles.

| Tag in use | Articles |
|---|---|
| `amazonfsxfornetappontap` | 2 |
| `netapp` | 5 |
| `fsxforontap` | 1 |
| `fsxontap` | 1 |

### The policy

| Position | S3 AP series | File portal series | Permission-Aware RAG |
|---|---|---|---|
| 1 | `aws` | `aws` | `aws` |
| 2 | `serverless` | `amplify` | `rag` |
| 3 | `fsxforontap` | `fsxforontap` | `fsxforontap` |
| 4 | Article-specific (`bedrock`, `fpolicy`, `eventdriven`, …) | Article-specific (`react`, `graphql`, `cognito`, …) | Article-specific |

The product tag is standardised on **`fsxforontap`**. `amazonfsxfornetappontap` is faithful
to the full product name but long, and `fsxontap` and `netapp` collide with articles about
other products.

### Done (2026-08-15, the three file portal articles)

Parts 1 to 3 were moved out of the S3 AP series and their tags aligned with the policy.

| Article | Before | After |
|---|---|---|
| Part 1 | `series: FSx for ONTAP S3 Access Points` / `aws, netapp, serverless, storage` | `series: FSx for ONTAP File Portal` / `aws, amplify, fsxforontap, architecture` |
| Part 2 | same / `aws, netapp, security, serverless` | same / `aws, amplify, fsxforontap, security` |
| Part 3 | same / `aws, bedrock, ai, netapp` | same / `aws, amplify, fsxforontap, bedrock` |

**The S3 AP series articles were left untagged as they were.** The inconsistency table above
is a count from that moment, so re-count the current state before deciding whether to align
the rest (dev.to Dashboard → Posts).

> **Re-tagging published articles is the author's call.** Changing a tag changes who the
> article reaches. New articles follow the table above; whether to align the existing ones
> is a decision about reach, not correctness.

## Fixing the series on an existing article

1. Sign in to dev.to, then profile icon → **Dashboard** → **Posts**
2. **Edit** the article
3. Make the `series` field in the front matter match the definition exactly

```yaml
---
title: "Article title"
published: true
series: "FSx for ONTAP S3 Access Points"
tags: aws, serverless, fsxforontap, fpolicy
---
```

4. Save
5. Confirm the series navigation widget appears on the article page

## Checklist

- [ ] Every EN S3 AP article carries `series: "FSx for ONTAP S3 Access Points"`
- [ ] Every JA S3 AP article carries `series: "FSx for ONTAP S3 AP サーバーレスパターン集"`
- [ ] File portal articles use the series name for their language
- [ ] Permission-Aware RAG articles carry `series: "Permission-Aware RAG"`
- [ ] No article belongs to two series
- [ ] No series name is shared between JA and EN
- [ ] The product tag is `fsxforontap` throughout, or the decision not to re-tag is recorded
- [ ] The series navigation widget appears on each article

## Notes

- The widget appears automatically once two or more articles share a series name
- A series is ordered by publication date, ascending; reordering means changing those dates
- Public pages can take a few minutes to reflect a change
- The drafts in the repository (`docs/devto-ja/`, `docs/article-*.md`) carry front matter
  too. If a draft's series name drifts from the published one, the next publication splits
  the series again
