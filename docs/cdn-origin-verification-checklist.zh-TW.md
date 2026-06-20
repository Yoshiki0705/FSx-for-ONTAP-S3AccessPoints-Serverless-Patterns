# ORIGIN_PULL SigV4 × S3 AP alias — 實機驗證清單

🌐 **Language / 言語**: [日本語](cdn-origin-verification-checklist.md) | [English](cdn-origin-verification-checklist.en.md) | [한국어](cdn-origin-verification-checklist.ko.md) | [简体中文](cdn-origin-verification-checklist.zh-CN.md) | [繁體中文](cdn-origin-verification-checklist.zh-TW.md) | [Français](cdn-origin-verification-checklist.fr.md) | [Deutsch](cdn-origin-verification-checklist.de.md) | [Español](cdn-origin-verification-checklist.es.md)

## 目的

為在實機上確定 [CDN 比較文件](cdn-comparison.zh-TW.md) 中標記為 **需驗證（TBV）** 的項目，亦即
**「各 CDN 的 SigV4 來源簽章對 FSx for ONTAP S3 Access Point 的 `accesspoint alias` 主機是否與標準 S3 儲存桶一樣運作」**
而提供的可重現步驟。

本清單用於 `content-edge-delivery` UC 的 `DeliveryMode=ORIGIN_PULL`（M1/M2）採用判斷。
**M3（PUBLISH_PUSH）不依賴本驗證**（因其規避來源驗證）。

> **區分說明**：本驗證為「特定測試環境下的實測」。請勿將一般 S3 行為或各 CDN 在標準桶上的實績當作對 S3 AP
> alias 的保證。

---

## 0. 前提條件

- FSx for ONTAP 檔案系統與 **Internet-origin** S3 Access Point（VPC-origin 不可用於 CDN）
- S3 AP alias（如 `<alias>-ext-s3alias`）與目標區域
- **已核准前綴**下的測試物件（如 `delivery-approved/test-1mb.bin`）
  - 遵循 permission-aware 原則，不將受 ACL 控管的主資料用於驗證
- 用於來源簽章的**最小權限 IAM 憑證**（僅對目標 AP 的 `s3:GetObject`）。盡量使用短期憑證
- 驗證終端（curl 7.75 以上支援 `--aws-sigv4`）、AWS CLI v2

> **安全**：驗證期間也不要將存取金鑰留在日誌·截圖·提交中。以金鑰名而非值參照（公開儲存庫政策）。

---

## 1. 基線驗證（無 CDN / 最重要）

不經 CDN，直接確認 **S3 AP alias 主機是否接受 SigV4**。這是所有 CDN 共通的核心。

### 1.1 AWS CLI（SDK 簽章）

```bash
aws s3api get-object \
  --bucket "<alias>-ext-s3alias" \
  --key "delivery-approved/test-1mb.bin" \
  /tmp/out.bin --region <region>
```

- 期望：HTTP 200 + 物件取得成功。
- 失敗時：分離 IAM / AP 政策 / ONTAP 側身分（UNIX UID / AD）的雙層授權進行排查。

### 1.2 原始 SigV4（近似 CDN 的來源簽章行為）

CDN 通常以固定存取金鑰進行 SigV4 簽章回源。以 `curl --aws-sigv4` 近似等效行為：

```bash
curl -sS -o /tmp/out.bin -w "%{http_code}\n" \
  --aws-sigv4 "aws:amz:<region>:s3" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" \
  "https://<alias>-ext-s3alias.s3.<region>.amazonaws.com/delivery-approved/test-1mb.bin"
```

- **若回傳 200**：alias 主機與標準桶一樣接受 SigV4 → M1/M4 實現可能性高。
- **若失敗**：可能是 alias 專屬定址差異所致 → 在各 CDN 的來源設定中逐一驗證主機格式·區域·服務名（`s3`）·
  路徑風格/虛擬主機的處理。
- 使用臨時憑證時追加 `-H "x-amz-security-token: $AWS_SESSION_TOKEN"`。

### 1.3 負向確認（重申規範）

- 無簽章 GET 應為 **403/AccessDenied**（確認 Block Public Access 強制）。
- Presigned URL 不可用（無法產生/不支援）→ 觀眾權杖走 CDN 原生機制。

---

## 2. 各 CDN 驗證步驟

在每個 CDN 設定「來源=S3 AP alias 主機」，確認快取未命中時的回源是否為 200。

### 2.1 Amazon CloudFront（M1 / OAC）— 參考
- 以 `EnableCloudFront=true` 部署 `content-edge-delivery` 範本（OAC + `SigningProtocol: sigv4`）。
- 驗證：`curl -I https://<distribution-domain>/delivery-approved/test-1mb.bin` → 200。
- 期望：依 AWS 官方教學成立（**有實績**）。

### 2.2 Fastly（M1 / SigV4 原生）
- 將 alias 主機設定為 S3 相容私有來源並啟用 SigV4 簽章（區域·服務 `s3`）。
- 驗證：經 Fastly 服務 GET → 200。確認 alias 虛擬主機格式在 Fastly SigV4 實作中被正確簽章。

### 2.3 Cloudflare（M2 / Workers 簽章）
- 於 Worker 實作 SigV4 並對 alias 主機做簽章回源（直接以 S3 AP 為來源而非 R2 時）。
- 驗證：經 Worker GET → 200。確認簽章標頭·酬載雜湊的處理。

### 2.4 Akamai（M1 / Cloud Access Manager）
- 於 Cloud Access Manager 設定 AWS 簽章方式，並以 Origin Characteristics 指定 alias 主機。
- 驗證：經 Akamai 屬性 GET → 200。確認於 AP alias 主機上是否可套用簽章。

### 2.5 Bunny.net（M1 / S3 來源回源）
- 將 Pull Zone 來源以 AWS S3 來源類型設定為 alias 主機。驗證：經 Pull Zone GET → 200。

### 2.6 Google Cloud CDN / Media CDN（M1 / private S3 origin）
- 以 private S3 相容來源 SigV4 驗證設定 alias 主機。驗證：經 Media CDN GET → 200。並確認跨雲 egress 路徑。

---

## 3. 合格/不合格標準

| 判定 | 條件 |
|------|------|
| **PASS** | 基線 1.2 為 200 且該 CDN 經由的快取未命中 GET 為 200；觀眾權杖以 CDN 原生機制運作 |
| **CONDITIONAL** | CDN 經由為 200，但需額外設定（路徑風格等）或限制（特定標頭） |
| **FAIL** | 對 alias 主機的 SigV4 在該 CDN 不成立，需迴避方案（M2 簽章實作/M4 簽章代理/轉 M3） |
| **BLOCKED** | 前提（Internet-origin、IAM、測試物件）未就緒，無法驗證 |

---

## 4. 驗證時的安全/治理確認

- [ ] 測試物件僅限 `delivery-approved/` 下（不使用受 ACL 控管的主資料）
- [ ] 來源簽章 IAM 僅對目標 AP 的 `s3:GetObject` 最小權限
- [ ] 不在邊緣/設定留存長期金鑰（優先短期憑證，驗證後失效）
- [ ] 不將存取金鑰·alias 實值·帳戶 ID 留在日誌/截圖/提交
- [ ] 觀眾權杖使用 CDN 原生機制（不用 S3 Presigned URL）
- [ ] 清理驗證中建立的臨時資源（Distribution、Pull Zone 等）

---

## 5. 結果記錄表（證據）

| CDN | 機制 | 設定完成 | 1.2 基線 | 經 CDN GET | 觀眾權杖 | 判定 | 證據（HTTP 狀態/標頭/時間） | 驗證日 | 負責角色 |
|-----|------|:---:|:---:|:---:|:---:|:---:|---|---|---|
| CloudFront | M1/OAC |  |  |  |  |  |  |  | Storage |
| Fastly | M1 |  |  |  |  |  |  |  | Storage |
| Cloudflare | M2 |  |  |  |  |  |  |  | Storage |
| Akamai | M1 |  |  |  |  |  |  |  | Storage/Partner |
| Bunny.net | M1 |  |  |  |  |  |  |  | Storage |
| Google Media CDN | M1 |  |  |  |  |  |  |  | Storage |

> 記錄注意：alias 實值·帳戶 ID·IP 用佔位符（`<alias>-ext-s3alias`、`123456789012`）。
> 驗證結果作為「特定測試環境下的實測」，不作為一般保證記載。

---

## 6. 驗證結果回饋

- 已確定的結果反映到 [CDN 比較文件](cdn-comparison.zh-TW.md) 第 3 節「S3 AP 專屬 TBV」欄 / 4.1「需驗證」的更新（TBV → 實測結果）。
- FAIL 的 CDN 在 `content-edge-delivery` 中以 `DeliveryMode=PUBLISH_PUSH`（M3）為建議路徑。

## 相關文件

- [CDN/邊緣傳遞整合比較](cdn-comparison.zh-TW.md)
- [content-edge-delivery UC](../content-edge-delivery/README.zh-TW.md)
- [S3AP 相容性說明](s3ap-compatibility-notes.md)
