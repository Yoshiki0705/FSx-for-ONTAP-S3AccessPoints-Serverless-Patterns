# GenAI RAG — 企業檔案

🌐 **Language / 語言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

透過 S3 Access Points 將企業檔案伺服器（FSx for ONTAP）上的機密文件安全地提供給 Amazon Bedrock / RAG 管線，**無需複製到 S3**。在保持檔案權限（ACL/NTFS）的同時實現 Permission-aware RAG。

## 解決的問題

| 問題 | 解決方案 |
|------|----------|
| 將敏感檔案複製到 S3 導致資料擴散 | 透過 S3 AP 直接讀取，無需複製 |
| 檔案權限遺失 | 透過 ONTAP REST API 擷取 ACL，在 RAG 回應時過濾 |
| 資料新鮮度問題 | FlexCache + S3 AP 提供最新資料 |
| 大型檔案伺服器的全卷處理 | EventBridge Scheduler + 增量偵測提高效率 |
| AI 處理與資料之間的距離 | FlexCache 將資料放置在 AI 處理 VPC 附近 |

## Permission-aware RAG 概念

1. **索引時**: 透過 ONTAP REST API 擷取每個文件的 ACL/權限資訊，作為中繼資料儲存在向量儲存中
2. **查詢時**: 根據使用者的 AD SID / 群組成員資格，將搜尋範圍過濾為僅使用者可存取的文件
3. **回應時**: 僅將過濾後的文件傳遞給 Bedrock 生成答案

## 成功指標

| 指標 | 目標 |
|------|------|
| 每次執行處理的檔案數 | > 200 檔案 |
| ACL 擷取成功率 | > 95% |
| 嵌入生成時間 | < 5 分鐘 / 100 檔案 |
| Permission-aware 過濾準確率 | > 99% |
| Human Review 比率 | < 10%（低信賴度區塊） |

---

## Governance Note

> 本模式提供技術架構指導。不構成法律、合規或監管建議。組織應諮詢合格的專業人員。
