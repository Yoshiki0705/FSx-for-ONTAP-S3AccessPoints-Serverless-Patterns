# Business User Guide

[日本語](business-user-guide-ja.md) | [English](business-user-guide.md)

This guide is for business users who access dashboards and insights built on replicated data from FSx for ONTAP via Amazon Quick / QuickSight.

## Before Making Decisions, Check:

1. **Source-of-record timestamp** — When was the original data created or updated?
2. **Last replicated timestamp** — When was the data copied to AWS?
3. **Dashboard refresh timestamp** — When did Quick / QuickSight last pull the data?
4. **Data freshness status** — Is the data Fresh / Stale / Unknown?
5. **Human review flag** — Does this insight require human review before action?
6. **Known limitations** — What cannot be concluded from this dashboard?

## Dashboard Labels (Required)

Every dashboard or Quick answer should display:

| Label | Example |
|-------|---------|
| Data source | Replicated copy on FSx for ONTAP |
| Source-of-record timestamp | 2026-06-10 10:00:00 JST |
| Last replicated at | 2026-06-10 10:05:12 JST |
| Dashboard refreshed at | 2026-06-10 10:06:00 JST |
| Data age | 6 minutes |
| Freshness status | ✅ Fresh (within SLO) |
| Source of truth? | ❌ No — this is a replicated copy |

## What This Data IS

- A near real-time replicated view of enterprise file data
- Suitable for trend analysis, pattern detection, and operational awareness
- Updated via scheduled SnapMirror replication + on-demand triggers

## What This Data IS NOT

- The source of record (source is on-premises ONTAP)
- Zero-latency real-time data (replication has a minimum 5-minute schedule)
- Validated for regulatory or compliance decisions (without additional review)
- Suitable for immediate automated actions without human confirmation

## Safe Usage Guidelines

1. Always verify the replication timestamp before citing specific values
2. Cross-reference with source system if precision is critical
3. Request human review for any action that affects operations, finance, or safety
4. Report any data that appears stale, missing, or inconsistent
5. Do not use dashboard values as contractual evidence without source verification
