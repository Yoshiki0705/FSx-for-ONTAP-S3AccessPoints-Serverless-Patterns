# FlexCache AnyCast / DR 模式

🌐 **Language / 語言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

本模式提供設計指南、模擬演示和維運設計文件，用於實現 ONTAP FlexCache AnyCast 和 DR（災難復原）配置與 FSx for ONTAP × S3 Access Points × AWS Serverless 服務的結合。

## 解決的問題

| 問題 | FlexCache AnyCast / DR 解決方案 |
|------|-------------------------------|
| 地理分散團隊的讀取效能 | 從最近的 FlexCache 提供熱資料 |
| EDA/媒體/HPC 雲端爆發 | 本地 Origin + 雲端 FlexCache 減少 WAN 傳輸 |
| DR 期間的讀取連續性 | Origin 故障時快取讀取持續 |
| WAN 傳輸量減少 | 僅快取熱資料，增量傳輸 |
| 用戶端掛載配置複雜性 | 透過 AnyCast IP 實現單一掛載點 |

## 成功指標

| 指標 | 目標 |
|------|------|
| 故障偵測時間 | < 30 秒 |
| DNS 傳播時間 | < 60 秒 |
| 故障轉移期間讀取連續性 | > 99.9% |
| 快取命中率（熱資料） | > 80% |
| WAN 傳輸減少率 | > 60% |

---

## Governance Note

> 本模式提供技術架構指導。不構成法律、合規或監管建議。組織應諮詢合格的專業人員。
