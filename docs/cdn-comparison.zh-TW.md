# CDN / 邊緣傳遞整合比較 — 從 FSx for ONTAP S3 Access Points 傳遞

🌐 **Language / 言語**: [日本語](cdn-comparison.md) | [English](cdn-comparison.en.md) | [한국어](cdn-comparison.ko.md) | [简体中文](cdn-comparison.zh-CN.md) | [繁體中文](cdn-comparison.zh-TW.md) | [Français](cdn-comparison.fr.md) | [Deutsch](cdn-comparison.de.md) | [Español](cdn-comparison.es.md)

## 0. 範圍

整理從 FSx for ONTAP S3 Access Points（S3 AP）上的資料透過 CDN/邊緣網路傳遞時的**技術可行性**之參考資料。
本文件**不**進行供應商優劣比較、價格/效能比較或行銷主張。僅討論針對 FSx for ONTAP S3 AP 的限制，**哪些可實現、
哪些不可實現、哪些需驗證**。傳遞供應商選型由客戶結合本文件範圍之外的因素（合約·SLA·維運體系·區域需求等）判斷。

## 1. 決定傳遞設計的 S3 AP 限制

| 限制 | 內容 | 對傳遞的影響 |
|------|------|------------|
| 強制 Block Public Access（不可停用） | 預設啟用·不可變更 | 無驗證的公開來源不可用；需來源驗證 |
| 來源驗證為 SigV4（IAM） | 由 IAM / AP 政策評估 | CDN 回源請求須以 AWS SigV4 簽章 |
| 雙層授權（AWS + ONTAP） | 先 IAM 再 ONTAP 檔案身分（UNIX UID / Windows AD） | 傳遞對象限於 ONTAP 身分可讀範圍 |
| 不支援 Presigned URL | 官方不支援 | 觀眾權杖驗證不能用 S3 Presigned URL；用 CDN 原生權杖 |
| NetworkOrigin（Internet/VPC，不可變更） | CDN 從受管/外部網路存取 | CDN 整合需 **Internet origin** |
| PutObject 最大 5 GB | 單次 PUT 限制 | 大檔寫回需分段上傳 |

## 2. 整合機制（供應商中立）

- **M1 — 原生 SigV4 回源**：CDN 以 SigV4 簽章直接回源 S3 AP。當 CDN 內建 SigV4 來源簽章時可實現。
  **需驗證**：S3 AP 的 `accesspoint alias` 主機與標準儲存桶不同，SigV4 行為須於實機驗證。
- **M2 — 邊緣運算 SigV4 簽章**：於 CDN 邊緣執行環境（Workers/Compute/EdgeWorkers）自行實作 SigV4。
  無原生來源簽章時可實現，簽章·金鑰管理需自持。
- **M3 — 推送至 CDN 原生 S3 相容儲存**：FSx 保留為主，僅將已核准成品複製到 CDN 側物件儲存。規避來源驗證問題，
  且供應商中立。驗證風險最低的首選。
- **M4 — 自管 SigV4 簽章代理**：將簽章中間層（Lambda Function URL / ALB）作為來源。幾乎所有 CDN 皆可用，
  但代理成為可用性·擴展的關注點。

> 通用絕對限制：觀眾權杖驗證不能用 S3 Presigned URL — 用 CDN 原生權杖。
> 公開傳遞繞過 NFS/SMB ACL，故僅傳遞已核准成品（見第 4 節）。

## 3. 各傳遞網路的機制支援（基於事實）

○ = 有官方功能 / △ = 有條件·自實作 / − = 無該功能 / TBV = 需 S3 AP 專屬驗證。

| 傳遞網 | M1 原生 SigV4 回源 | M2 邊緣簽章 | M3 自有 S3 相容儲存 | 觀眾權杖 | S3 AP 專屬 TBV |
|--------|:---:|:---:|:---:|---|---|
| Amazon CloudFront | ○ OAC (SigV4) | △ Lambda@Edge / Functions | （至標準 S3） | CloudFront 簽章 URL/Cookie | **有實績**（AWS 官方教學展示 S3 AP + OAC） |
| Akamai | ○ Cloud Access Manager（AWS 簽章） | △ EdgeWorkers | ○ NetStorage / Object Storage | Akamai Token Auth | AP alias 主機上的簽章 TBV |
| Fastly | ○ 對 S3 相容私有來源用 SigV4 | △ Compute | ○ Fastly Object Storage | Fastly 簽章 URL | AP alias 上的 SigV4 TBV |
| Cloudflare | −（代理本身未內建 SigV4） | ○ 以 Workers 做 SigV4 簽章 | ○ R2（S3 相容） | Cloudflare 簽章 URL | Workers 簽章 + AP alias TBV |
| Bunny.net | △ S3 回源（AWS S3 來源類型） | − | ○ Bunny Storage（S3 相容 API，beta） | Pull Zone 權杖驗證 | AP alias 上的簽章 TBV |
| Google Cloud CDN / Media CDN | ○ private S3 相容來源 SigV4 驗證 | △ Media CDN 路由 | （GCS / 任意 S3 相容） | Media CDN 簽章 URL/Cookie | 跨雲 egress + AP alias TBV |

### 不列入表格/作註解
- **Azure Front Door / Azure CDN**：同一機制（M1/M4）可能適用·TBV。非主要範圍。
- **Gcore**：S3 相容物件儲存 + 儲存作來源（M3）。非主要範圍。
- **Edgio（原 Limelight / Edgecast）**：**2025-01-15 停止 CDN 業務**，資產大部分由 Akamai 取得。
  **非在運選項** — 排除。

> 出處為各家公開文件（CloudFront OAC、Akamai Cloud Access Manager、Fastly S3 相容私有來源、Cloudflare
> Workers/R2、Bunny Storage、Google Media CDN）。均為針對**標準 S3 相容儲存桶**的描述；於 FSx for ONTAP S3 AP
> accesspoint alias 上的行為為 TBV。

## 4. 安全固定要求（機制通用）

1. 公開傳遞繞過 NFS/SMB ACL — **僅傳遞已核准成品**。不將受 ACL 控管的主資料直接送入傳遞層。
2. 分離主資料（受 ACL 控管·機密）與傳遞成品（公開/準公開）。M3 使該分離結構上自然。
3. 觀眾驗證用 CDN 原生權杖機制（不用 S3 Presigned URL）。
4. 最小權限來源憑證；不在邊緣放置長期金鑰，優先短期憑證。
5. 傳遞日誌：將日誌寫回 FSx 時，將觀眾 PII 處理納入設計。
6. **傳遞核准軌跡**：記錄哪個物件由誰於何時核准為公開傳遞。核准者未記錄的物件不阻斷，而以 `unrecorded` **可視化**。
7. **資料落地 / 地區限制**：CDN 全球傳遞。不可跨區的資料應從核准對象排除，或以 geo-blocking 控管；
   核准流程納入落地判定。

### 4.1 證據分類
- **公開證據**：第 3 節各傳遞網功能 — 基於公開文件、**時點相關**，採用前以最新資訊再確認。
- **需驗證（本專案）**：針對 FSx for ONTAP S3 AP accesspoint alias 的各 CDN SigV4 來源簽章實際行為。

## 5. 可行性小結

| 問題 | 回答 |
|------|------|
| 能否將 S3 AP 作為無驗證的 CDN 來源公開 | **否**（強制 BPA） |
| 能否從 S3 AP 經 CDN 直接傳遞 | **有條件可以** — 支援/實作 SigV4 時 M1/M2。AP alias 簽章為 TBV |
| 沒有 SigV4 的 CDN 能否傳遞 | **可以** — M3（推送）或 M4（簽章代理） |
| 觀眾能否用 S3 Presigned URL | **否** — 用 CDN 原生權杖 |
| 傳遞時能否強制 ONTAP ACL | **否** — 以「僅傳遞已核准成品」+ 軌跡保障 |
| 驗證風險最低的首選 | **M3（推送）** — 規避來源驗證，供應商中立，便於 DemoMode |

> **Governance Caveat**：本資料為技術參考資訊。各家功能會更新，採用前請以最新官方文件再確認。針對 S3 AP
> accesspoint alias 的 SigV4 來源簽章是本專案的驗證項（TBV）。傳遞供應商選型由客戶判斷。
