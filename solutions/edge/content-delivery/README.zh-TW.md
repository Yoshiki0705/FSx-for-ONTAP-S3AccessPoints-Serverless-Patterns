# Content Edge Delivery — FSx for ONTAP S3 AP × CDN/邊緣（供應商中立）

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

將 FSx for NetApp ONTAP 作為**單一可信來源（主資料）**保留，同時讓 S3 Access Points（S3 AP）上的
**已核准傳遞的成品（rendition）**可透過 CDN/邊緣網路傳遞的**供應商中立**無伺服器模式。

各傳遞網路的技術可行性比較（CloudFront / Akamai / Fastly / Cloudflare / Bunny.net /
Google Media CDN 等）請參閱 **[CDN 比較](../docs/cdn-comparison.zh-TW.md)**。

> 本模式為參考實作。傳遞供應商選型、版權處理、地區限制與合規由客戶負責。

> **TL;DR（30秒）**：不移動 ONTAP/NAS 主資料，**僅傳遞已核准成品**，經 CloudFront 或第三方 CDN。
> 從驗證風險最低的 `PUBLISH_PUSH`（M3）開始。SigV4 直接回源（ORIGIN_PULL）需先用
> [驗證清單](../docs/cdn-origin-verification-checklist.zh-TW.md)實測再採用。

## 業務成果與採用（Outcome / Adoption）

以**業務成果**評估，而非「部署成功」。

| 區分 | Outcome / Metric / 測量方法 |
|---|---|
| Business Outcome | 不雙份保存主資料即實現邊緣傳遞（傳遞用複製僅限已核准成品） |
| Metric | 流入傳遞層的主資料筆數 = 0 / 核准軌跡 `unrecorded` 筆數 |
| 測量方法 | 彙總 publish 清單的 `provenance` 與 `skipped`/`published` |

- **安全實驗邊界**：`DemoMode=true` 可在無 FSx/外部 CDN 時驗證邏輯。
- **Business Sponsor**：任命傳遞負責人（媒體/傳遞平台團隊）並核准 Go/No-Go。
- **Go/No-Go 清單**：`ApprovedPrefix` 外不被納入對象 / 記錄核准軌跡 / 觀眾權杖以 CDN 原生機制運作 /
  採用 ORIGIN_PULL 時 SigV4×alias 實測為 PASS。
- 將未來工作定位為**證據擴展**（TBV → 實測），而非未完成。

## Partner/SI 使用指南

- **首個客戶問題**：「是否希望將既有 NAS/ONTAP 資產在不複製的情況下接入邊緣傳遞？傳遞走 CloudFront，
  還是既有合約 CDN（如 Akamai）？」
- **PoC 產出**：DemoMode 示範 → 已核准成品的傳遞清單 →（選用）實機 SigV4 驗證結果。可將
  [CDN 比較](../docs/cdn-comparison.zh-TW.md)直接用於客戶對話。

## 兩種整合機制

- **ORIGIN_PULL**：不複製物件，產生供 CDN 透過 SigV4 直接回源 S3 AP 的來源參考清單。CloudFront 透過 OAC
  原生支援（參考實作）。第三方 CDN 的 SigV4 回源簽章**需驗證**。
- **PUBLISH_PUSH**：將已核准成品複製到 CDN 側 S3 相容物件儲存。規避回源驗證問題，且供應商中立——驗證風險最低的首選。

## 主要元件

| 元件 | 職責 |
|---|---|
| `functions/publish/handler.py` | 將已核准成品反映至傳遞層，並將傳遞清單寫回 S3 AP |
| `functions/delivery_log_sync/handler.py` | 將 CDN 傳遞日誌正規化（IP 遮罩）並寫回 S3 AP，以便與製作資料勾稽 |
| Step Functions | Publish → SNS 通知 |
| CloudFront（選用） | ORIGIN_PULL 的參考傳遞（OAC + SigV4） |

## 部署

```bash
sam build --template content-edge-delivery/template.yaml
sam deploy --guided \
  --template content-edge-delivery/template.yaml \
  --stack-name fsxn-content-edge-delivery
```

## 安全 / 治理

- **permission-aware**：傳遞對象僅限 `ApprovedPrefix` 之下。不直接傳遞受 ACL 控管的主資料。
- **觀眾驗證**：不支援 S3 Presigned URL → 使用 CDN 原生權杖機制。
- **PII**：寫回傳遞日誌時對用戶端 IP 遮罩（`RedactClientIp=true`）。
- **最小權限**：傳遞 Lambda 因存取 Internet-origin S3 AP 而於 **VPC 外**執行。

> **Governance Note**：傳遞不強制套用 ONTAP 檔案權限。傳遞邊界由「僅傳遞已核准成品」的維運規則、核准軌跡記錄
> 以及傳遞目標的存取控制來確保。

### 責任分擔（RACI / 公共部門觀點）

| 角色 | 職責 |
|---|---|
| Data Owner | 傳遞對象資料的分類·落地·可否公開的最終責任 |
| Approver | 核准置於 `ApprovedPrefix`；賦予核准軌跡（approved-by / approval-id） |
| Audit Reviewer | 定期審查 publish 清單的 `provenance` 與傳遞日誌 |
| Ops Owner | 接收告警·處理事件·執行回復 |

- AI/自動判定為**輔助訊號**；可否公開由人（Data Owner / Approver）決定。
- 驗證用資料使用**非機密合成/樣本**（不將生產個人資料用於驗證）。
- 技術驗證**不替代**法務·合規·隱私評估。

## 維運 / Runbook

- **告警**：`EnableCloudWatchAlarms=true` 時，Lambda 錯誤（publish/log-sync）與 Step Functions 失敗經 SNS 通知
  （`NotificationEmail`）。
- **排查**：publish 錯誤 → 檢視 `/aws/lambda/<stack>-publish`；分離 S3 AP 授權（IAM + AP policy + ONTAP 身分）
  與外部儲存驗證（Secrets Manager）。外部 push 失敗 → 檢查 `ExternalStoreSecretName`·端點·儲存桶。疑似邊界破壞 →
  [事件回應 Playbook](../docs/incident-response-playbook.md)。
- **回復**：傳遞僅 publish 已核准成品；誤公開時從傳遞目標（CDN 儲存/Distribution）移除該物件，從 `ApprovedPrefix`
  撤回後重新 publish。
- **外部儲存驗證**：PUBLISH_PUSH 推送至 Akamai/R2/Fastly 等時，AWS 預設憑證不通用，需設定
  `ExternalStoreSecretName`（Secrets Manager，`{"access_key_id","secret_access_key"}`）。

## 相關文件

- [CDN/邊緣傳遞整合比較](../docs/cdn-comparison.zh-TW.md)
- [ORIGIN_PULL SigV4 驗證清單](../docs/cdn-origin-verification-checklist.zh-TW.md)（實機驗證步驟）
- [替代架構比較](../docs/comparison-alternatives.md)
- [事件回應 Playbook](../docs/incident-response-playbook.md)
