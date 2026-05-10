# 檔案伺服器權限稽核 — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示了自動偵測檔案伺服器過度存取權限的稽核工作流程。分析NTFS ACL，識別違反最小權限原則的項目，並自動產生合規報告。

**核心訊息**: 將需要數週的檔案伺服器權限稽核自動化，即時視覺化過度權限風險。

**預計時間**: 3–5 min

---

## 輸出目標: FSxN S3 Access Point (Pattern A)

此 UC 屬於 **Pattern A: Native S3AP Output**
(請參閱 `docs/output-destination-patterns.md`)。

**設計**: 所有 AI/ML 產物透過 FSxN S3 Access Point 寫回與來源資料**相同的 FSx ONTAP 磁碟區**。
不建立獨立的標準 S3 儲存貯體 ("no data movement" 模式)。

**CloudFormation 參數**:
- `S3AccessPointAlias`: 輸入用 S3 AP Alias
- `S3AccessPointOutputAlias`: 輸出用 S3 AP Alias (可以與輸入相同)

AWS 規格約束與解決方案請參閱
[README.zh-TW.md — AWS 規格約束](../../README.zh-TW.md#aws-規格約束及解決方案)。

---
## Workflow



---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 問題陳述：手動稽核數千個資料夾的權限不切實際

### Section 2 (0:45–1:30)
> 工作流程觸發：指定目標磁碟區並啟動稽核

### Section 3 (1:30–2:30)
> ACL分析：自動收集ACL並偵測策略違規

### Section 4 (2:30–3:45)
> 結果審查：即時掌握違規數量和風險等級

### Section 5 (3:45–5:00)
> 合規報告：自動產生包含優先順序操作的稽核報告

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (ACL Collector) | NTFS ACL中繼資料收集 |
| Lambda (Policy Checker) | 策略違規規則比對 |
| Lambda (Report Generator) | 透過Bedrock產生稽核報告 |
| Amazon Athena | 違規資料SQL分析 |

---

*本文件是技術演示影片的製作指南。*
