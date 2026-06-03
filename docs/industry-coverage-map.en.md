# Industry Coverage Map

> **Last Updated**: 2026-06-03

This document provides a comprehensive view of FSx for ONTAP S3 Access Points serverless pattern coverage against AWS official Industries categories.

## Status Definitions

| Status | Description |
|--------|-------------|
| Covered | Implemented and tested |
| Planned-P0 | Immediate priority (highest) |
| Planned-P1 | Starts after P0 completion |
| Planned-P2 | Starts after P1 completion |
| Not Covered | No implementation planned |

---

## AWS Official Industries Categories

| # | Industry (EN) | 業界名 (日本語) | UC/FC | Status | Updated |
|---|---------------|----------------|-------|--------|---------|
| 1 | Advertising & Marketing | 広告・マーケティング | UC19 | Covered | 2026-06-02 |
| 2 | Aerospace & Defense | 航空宇宙・防衛 | UC15 | Covered | 2026-05-10 |
| 3 | Automotive | 自動車 | UC9, FC4 | Covered | 2026-01-15 |
| 4 | Consumer Packaged Goods | 消費財 | — | Not Covered | 2026-06-02 |
| 5 | Education | 教育 | UC13 | Covered | 2026-03-20 |
| 6 | Energy & Utilities | エネルギー・ユーティリティ | UC8, UC25 | Covered | 2026-06-03 |
| 7 | Financial Services | 金融サービス | UC2, UC14 | Covered | 2026-03-20 |
| 8 | Games | ゲーム | FC6 | Covered | 2026-05-15 |
| 9 | Government | 政府・公共 | UC16 | Covered | 2026-05-10 |
| 10 | Healthcare & Life Sciences | 医療・ヘルスケア | UC5, UC7, FC5 | Covered | 2026-05-15 |
| 11 | Manufacturing | 製造業 | UC3 | Covered | 2026-01-15 |
| 12 | Media & Entertainment | メディア・エンターテインメント | UC4 | Covered | 2026-01-15 |
| 13 | Mining & Natural Resources | 鉱業・天然資源 | — | Not Covered | 2026-06-02 |
| 14 | Nonprofit | 非営利団体 | UC24 | Covered | 2026-06-03 |
| 15 | Power & Utilities | 電力・ユーティリティ | UC25 | Covered | 2026-06-03 |
| 16 | Retail | 小売 | UC11 | Covered | 2026-03-20 |
| 17 | Semiconductor | 半導体 | UC6 | Covered | 2026-03-20 |
| 18 | Software & Internet | ソフトウェア・インターネット | — | Not Covered | 2026-06-02 |
| 19 | Sustainability | サステナビリティ | UC23 | Covered | 2026-06-03 |
| 20 | Telecommunications | 通信 | UC18 | Covered | 2026-06-02 |
| 21 | Travel & Hospitality | 旅行・ホスピタリティ | UC20 | Covered | 2026-06-03 |
| 22 | Transportation & Logistics | 運輸・物流 | UC12, UC22 | Covered | 2026-06-03 |

---

## AWS Japan Focus Areas (Outside Global Classification)

The following are focus areas based on the AWS Japan industry team structure. These are not part of the global AWS Industries classification but have high demand in the Japan market.

| # | Area | 領域名 (日本語) | UC/FC | Status | Updated |
|---|------|----------------|-------|--------|---------|
| 1 | Agriculture & Food | 農業・食品 | UC21 | Covered | 2026-06-03 |
| 2 | Construction & Civil Engineering | 建設・土木 | UC10 | Covered | 2026-03-20 |
| 3 | Legal & Compliance | 法務・コンプライアンス | UC1 | Covered | 2026-01-15 |
| 4 | Logistics & Warehousing | 物流・倉庫 | UC12 | Covered | 2026-03-20 |
| 5 | Real Estate | 不動産 | UC26 | Covered | 2026-06-03 |
| 6 | Human Resources | 人材・HR | UC27 | Covered | 2026-06-03 |
| 7 | Chemicals & Materials | 化学・素材 | UC28 | Covered | 2026-06-03 |
| 8 | Smart City & Geospatial | スマートシティ | UC17 | Covered | 2026-05-10 |
| 9 | SAP & ERP Adjacent | SAP / ERP | SAP | Covered | 2026-04-01 |
| 10 | Enterprise GenAI | GenAI / RAG | FC3 | Covered | 2026-05-15 |
| 11 | Insurance | 保険 | UC14 | Covered | 2026-03-20 |

---

## Implementation Priority Roadmap

### P0 (Immediate)

| UC | Industry | Directory | Description |
|----|----------|-----------|-------------|
| UC18 | Telecommunications | `telecom-network-analytics/` | CDR/network log analysis and anomaly detection |
| UC19 | Advertising & Marketing | `adtech-creative-management/` | Creative asset management and brand compliance |

**Prerequisites**: None (ready to start immediately)

### P1 (After P0 Completion)

| UC | Industry | Directory | Description |
|----|----------|-----------|-------------|
| UC20 | Travel & Hospitality | `travel-document-processing/` | Reservation document processing and facility inspection |
| UC21 | Agriculture & Food | `agri-food-traceability/` | Farmland aerial imagery and traceability document management |
| UC22 | Transportation & Rail | `transportation-maintenance/` | Equipment inspection imagery and maintenance report analysis |

**Prerequisites**: UC18 + UC19 implementation complete

### P2 (After P1 Completion)

| UC | Industry | Directory | Description |
|----|----------|-----------|-------------|
| UC23 | Sustainability & ESG | `sustainability-esg-reporting/` | ESG metrics extraction and reporting |
| UC24 | Nonprofit | `nonprofit-grant-management/` | Grant application classification and outcome matching |
| UC25 | Power & Utilities | `utilities-asset-inspection/` | Drone imagery and SCADA log analysis |
| UC26 | Real Estate | `real-estate-portfolio/` | Property image analysis and contract data extraction |
| UC27 | Human Resources | `hr-document-screening/` | Resume screening and candidate evaluation |
| UC28 | Chemicals & Materials | `chemical-sds-management/` | SDS management and lab notebook analysis |

**Prerequisites**: UC20 + UC21 + UC22 implementation complete

---

## Coverage Summary

| Status | UC/FC Count | Ratio |
|--------|-------------|-------|
| Covered | 28 UC + 6 FC = 34 | — |
| Planned-P0 | 0 | — |
| Planned-P1 | 0 | — |
| Planned-P2 | 0 | — |
| Not Covered | 3 (Consumer Goods, Mining, Software) | — |

**Goal**: Provide at least one UC/FC for every AWS Industries category.

---

## Change Log

| Date | Change |
|------|--------|
| 2026-06-03 | P2 complete — Updated UC23 (Sustainability), UC24 (Nonprofit), UC25 (Power), UC26 (Real Estate), UC27 (HR), UC28 (Chemicals) to Covered. Total: 28 UC + 6 FC = 34 patterns |
| 2026-06-03 | P1 complete — Updated UC20 (Travel), UC21 (Agriculture), UC22 (Transportation) to Covered |
| 2026-06-02 | P0 complete — Updated UC18 (Telecom), UC19 (Advertising) to Covered |
| 2026-06-02 | Initial version — added planned status for UC18–UC28 |
