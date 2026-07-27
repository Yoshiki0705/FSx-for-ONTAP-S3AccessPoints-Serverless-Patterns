# 檔案入口 — 安全與合規人員指南

> 🌐 Language: [English](../en/portal-compliance-guide.md) | [日本語](../ja/portal-compliance-guide.md) | [한국어](../ko/portal-compliance-guide.md) | [简体中文](../zh-CN/portal-compliance-guide.md) | **繁體中文** | [Français](../fr/portal-compliance-guide.md) | [Deutsch](../de/portal-compliance-guide.md) | [Español](../es/portal-compliance-guide.md)

本指南面向安全官員、合規分析師和資料保護人員，協助您透過入口**驗證**法規管控措施，無需執行儲存管理操作。您不需要 `storage-admin` 權限 — 以下所有任務均使用唯讀存取完成。

---

## 您在入口中的角色

| 可執行的操作 | 入口位置 |
|-------------|----------|
| 驗證勒索軟體保護狀態 | 側邊欄 → 🛡️ ARP/AI |
| 確認快照鎖定與保留期限 | 側邊欄 → 🔒 Lock |
| 檢閱稽核軌跡（誰存取了什麼） | 側邊欄 → 🔍 Audit Trail |
| 檢查 PHI 防護欄的執行情況 | 側邊欄 → 📂 All Files（導覽至 `/dicom/` 或 `/phi/`） |
| 驗證輸出儲存貯體的 S3 Object Lock | 側邊欄 → 🔒 Lock → S3 Object Lock 標籤 |
| 檢視 EMS 警示（ONTAP 系統事件） | Admin → Resources（非 `storage-admin` 為唯讀） |

> **注意**：您無法變更設定（鎖定設定、ARP 狀態、匯出政策）。如需變更，請聯繫 `storage-admin` 使用者。

---

## 任務 1：驗證勒索軟體保護 (ARP/AI)

**法規背景**：FISC、NIST CSF DE.CM-4、ISO 27001 A.12.2

1. 點擊側邊欄中的 **🛡️ ARP/AI**
2. 確認每個受監控卷顯示綠色狀態（🟢 無威脅）
3. 如果出現威脅標記（🔴），記錄卷名稱和偵測時間戳
4. 檢查**事件生命週期標記**以了解目前回應階段：
   - 🔴 已偵測 — 威脅已識別，等待遏制
   - 🟠 已遏制 — 攻擊者存取已阻止，快照已保留
   - 🟡 調查中 — 鑑識分析進行中
   - 🟢 已解決 — 事件關閉

**稽核證據**：擷取 ARP 面板畫面，顯示所有卷的保護狀態 + 活動事件標記及時間戳。

---

## 任務 2：確認快照不可變性 (WORM)

**法規背景**：SEC 17a-4、FISC 7 年保留、HIPAA 6 年、SOX 5 年、NARA

1. 點擊側邊欄中的 **🔒 Lock**
2. 檢閱三個標籤：

### 標籤 A：ONTAP SnapLock
- 驗證卷類型：**Compliance**（包含 root 在內任何人都無法刪除）或 **Enterprise**（管理員可釋放）
- 檢查保留期限是否符合您的政策：
  - 最短期限 ≥ 法規要求
  - Compliance Clock 已初始化並執行中

### 標籤 B：S3 Object Lock
- 驗證輸出儲存貯體已啟用 Object Lock
- 確認模式：法規歸檔用 **Compliance**，AI 輸出用 **Governance**
- 檢查預設保留天數是否符合要求

### 標籤 C：Tamperproof Snapshots
- 檢閱已鎖定快照表格：名稱、建立時間、到期時間
- 驗證到期日期是否符合法規保留要求：

| 法規 | 必要保留期限 | 預期到期時間 |
|------|-------------|-------------|
| FISC | 7 年（2,557 天） | 建立 + 7 年 |
| HIPAA | 6 年（2,192 天） | 建立 + 6 年 |
| SOX/J-SOX | 5 年（1,825 天） | 建立 + 5 年 |
| NARA | 3-75 年（不等） | 按紀錄排程 |

**稽核證據**：擷取每個標籤的畫面，顯示鎖定狀態 + 保留期限。

---

## 任務 3：檢閱稽核軌跡

**法規背景**：FISC、SOX Section 302/404、HIPAA §164.312(b)、PCI DSS 10.x

1. 點擊側邊欄中的 **🔍 Audit Trail**
2. 面板顯示 S3 Access Point 的 CloudTrail S3 資料事件
3. 需要檢閱的關鍵欄位：
   - **誰**：IAM 主體（Cognito 使用者身分）
   - **何時**：事件時間戳 (UTC)
   - **做了什麼**：API 操作（`GetObject`、`PutObject`、`ListObjectsV2`）
   - **哪個檔案**：S3 金鑰（檔案路徑）
4. 如果調查特定事件，按日期範圍或使用者進行篩選

**稽核證據**：匯出或擷取按檢閱期間篩選的稽核軌跡畫面。

---

## 任務 4：驗證 PHI 防護欄

**法規背景**：HIPAA §164.502（最小必要原則）、45 CFR 164.514

1. 點擊側邊欄中的 **📂 All Files**
2. 導覽至名為 `/dicom/`、`/phi/`、`/pii/` 或 `/hipaa/` 的資料夾
3. 觀察 AI 處理按鈕顯示：**🚫 PHI — AI Blocked**
4. 驗證按鈕已停用（無論使用者角色如何都無法點擊）

**意義**：這些受保護路徑中的檔案在結構上被阻止傳送至外部 AI 服務（Bedrock、Rekognition、Textract、Comprehend）。這在 UI 層透過路徑模式比對實現，任何使用者都無法覆寫。

**限制**：此防護欄依賴資料夾命名慣例。放置在非受保護路徑中包含 PHI 內容的檔案不會被阻止。請確保組織的資料夾結構政策在上游得到執行。

**稽核證據**：擷取顯示 `/dicom/` 資料夾中已停用 AI 按鈕的畫面。

---

## 任務 5：驗證 AI 輸出的 S3 Object Lock

**法規背景**：SEC 17a-4(f)、CFTC 1.31、FINRA 4511

1. 點擊 **🔒 Lock** → **S3 Object Lock** 標籤
2. 驗證：
   - 輸出儲存貯體已**啟用** Object Lock
   - 模式適當：法規歸檔用 **Compliance**（不可變）或 AI 輸出用 **Governance**（有權限可覆寫）
   - 預設保留期限與您的保留排程一致
3. 如果未設定 Object Lock，請上報給 `storage-admin` 使用者

**重要性**：儲存在 S3 中的 AI 處理結果（分類標籤、擷取的文字、合規報告）本身可能是法規紀錄。Object Lock 確保這些輸出在保留期間內不能被更改或刪除。

---

## 任務 6：事件回應驗證

當偵測到勒索軟體事件時：

1. 前往 **🛡️ ARP/AI** → 檢查事件標記狀態
2. 驗證遏制已執行：
   - 快照已擷取（保留證據）
   - 可疑使用者/IP 已阻止
3. 前往 **🔍 Audit Trail** → 篩選偵測時間戳前後的事件
4. 記錄時間線：偵測時間 → 遏制時間 → 調查開始
5. 解決後，驗證事件標記顯示 🟢 已解決

**事件時間線 SLA 參考**：

| 階段 | 典型時長 | 您的 SLA |
|------|:---:|:---:|
| 偵測 → 遏制 | < 5 分鐘（自動） | _____ |
| 遏制 → 調查開始 | < 1 小時 | _____ |
| 調查 → 解決 | 視情況而定 | _____ |

---

## 法規對應

| 入口功能 | FISC | HIPAA | SOX | NIST CSF | ISO 27001 |
|---------|:---:|:---:|:---:|:---:|:---:|
| ARP/AI 勒索軟體偵測 | ✅ | ✅ | — | DE.CM-4 | A.12.2 |
| SnapLock (Compliance 模式) | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| S3 Object Lock | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| Tamperproof Snapshots | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| PHI 防護欄 | — | ✅ | — | PR.AC-4 | A.9.4 |
| Audit Trail (CloudTrail) | ✅ | ✅ | ✅ | DE.AE-3 | A.12.4 |
| 事件生命週期追蹤 | ✅ | ✅ | — | RS.RP-1 | A.16.1 |

---

## 您無法執行的操作（及負責人）

| 操作 | 所需群組 | 聯繫人 |
|------|:---:|--------|
| 變更 ARP/AI 狀態 | `storage-admin` | 儲存管理員 |
| 鎖定/解鎖快照 | `storage-admin` | 儲存管理員 |
| 設定 S3 Object Lock | `storage-admin` | 儲存管理員 |
| 阻止/解除使用者（遏制） | `storage-admin` | 安全營運 + 儲存管理員 |
| 建立/刪除卷 | `storage-admin` | 儲存管理員 |
| 修改匯出政策 | `storage-admin` | 儲存管理員 |

---

## 相關文件

| 文件 | 用途 |
|------|------|
| [使用者指南](portal-user-guide.md) | 一般使用者日常操作 |
| [授權模型](portal-authorization-model.md) | 完整權限矩陣 |
| [管理員示範指南](admin-resource-management-demo.md) | 儲存管理操作 |
| [事件回應手冊](../../docs/incident-response-playbook.md) | 完整事件回應流程 |
| [快速參考卡](portal-quick-reference.md) | 1 頁速查 |
