# 檔案入口 — 使用者指南

> 🌐 Language: [English](../en/portal-user-guide.md) | [日本語](../ja/portal-user-guide.md) | [한국어](../ko/portal-user-guide.md) | [简体中文](../zh-CN/portal-user-guide.md) | **繁體中文** | [Français](../fr/portal-user-guide.md) | [Deutsch](../de/portal-user-guide.md) | [Español](../es/portal-user-guide.md)

本指南適用於已受邀使用已部署 File Portal 的終端使用者。本文件假設入口管理員已完成部署並建立了您的帳戶 — 您不需要 AWS CLI 存取權限或部署知識。

**此入口的功能**: 透過瀏覽器瀏覽 NAS 檔案、觸發 AI/ML 分析、檢視結果並查看資料保護狀態 — 無需 VPN 或 SMB/NFS 用戶端設定。

---

## 開始使用

### 1. 登入

1. 開啟管理員提供的入口 URL
2. 輸入您的電子郵件和密碼（依設定為管理員提供或自行註冊）
3. 若已啟用 MFA，請輸入驗證器應用程式中的 TOTP 代碼
4. 首次登入時，**Welcome Modal** 將引導您了解 3 項關鍵功能：
   - 📂 檔案瀏覽 — 在瀏覽器中瀏覽 NAS 檔案
   - ⚡ AI 處理 — 選取檔案並觸發工作流程
   - 🔒 資料保護 — 快照、鎖定和勒索軟體狀態

> **提示**: 勾選「不再顯示」可在後續登入時跳過 Welcome Modal。

### 2. 入口版面配置

```
┌─────────────────────────────────────────────────────────┐
│ [☰] File Portal              🌐 ZH ▾   user@example.com │
├───────────────┬─────────────────────────────────────────┤
│ 側邊欄       │  主要內容                               │
│ (導覽)        │                                         │
│               │                      AI 助理面板 →      │
└───────────────┴─────────────────────────────────────────┘
```

- **左側邊欄**: 依瀏覽、AI & 處理、資料保護、管理分組的導覽
- **主要內容**: 作用中區域（點擊側邊欄項目時切換）
- **右側面板**: AI 助理（在 All Files 中選取檔案時顯示）
- **頂部列**: 語言切換器、使用者電子郵件、登出

### 3. 語言

點擊頂部列的 🌐 語言選擇器可在 8 種語言間切換：日本語、English、한국어、简体中文、繁體中文、Français、Deutsch、Español。切換即時生效，無需重新載入頁面。

---

## 瀏覽 — 檔案操作

### All Files

您的主要檔案瀏覽器。透過 S3 Access Point 顯示 FSx for ONTAP 磁碟區的內容。

| 操作 | 方法 |
|------|------|
| 瀏覽資料夾 | 點擊資料夾名稱 |
| 返回上一層 | 點擊檔案清單頂部的 `..` |
| 預覽圖片 | 點擊圖片檔案旁的 🖼️ 圖示 |
| 預覽 PDF | 點擊 📕 圖示 — 在瀏覽器內建檢視器中開啟 |
| 預覽 Word 文件 | 點擊 📝 圖示 — 在瀏覽器中呈現 |
| 下載檔案 | 點擊 📄 圖示 |
| 建立分享連結 | 點擊 🔗 → 選擇 TTL（5 分鐘 / 15 分鐘 / 1 小時）→ 複製 URL |
| 向 AI 詢問檔案相關問題 | 選取檔案 → 在右側 AI 面板中輸入問題 |
| 偵測圖片中的物件 | 選取圖片 → 在 AI 面板中點擊 "Detect Objects" |
| 處理此資料夾 | 點擊檔案清單上方的 ⚡ 按鈕 |

**PHI 保護資料夾**: 若您進入名為 `/dicom/`、`/phi/`、`/pii/` 等的資料夾，AI 處理按鈕將顯示 `🚫 PHI — AI Blocked`。這是安全護欄 — 無論您的權限為何，這些資料夾中的檔案都無法傳送至 AI 服務。

### Favorites

點擊檔案清單中的 ⭐ 圖示釘選常用檔案。釘選的檔案顯示在 Favorites 區段，便於快速存取。

### Recent

顯示您最近檢視、下載或 AI 查詢的檔案，附帶相對時間戳記（「3 分鐘前」、「2 小時前」）。僅顯示您自己的歷史記錄，其他使用者的活動不可見。

### Upload

基於 Storage Browser for S3 的拖放檔案上傳。另支援：
- 建立資料夾
- 檔案複製和刪除
- 多檔案上傳（每個檔案最大 50 GB）

---

## AI & 處理

### AI Processing

對資料夾或檔案集觸發 AI/ML 工作流程。

1. 從下拉選單選擇處理模式（如 Legal Compliance、Financial IDP、Semiconductor EDA）
2. 設定輸入前綴（若從 All Files 點擊 ⚡ 則已預填）
3. 點擊 **Start Processing**
4. 頁面將跳轉至 Job History，狀態每 5 秒更新一次

### Job History

檢視所有過去的處理工作及其狀態、時間戳記和輸出資料。

| 狀態 | 含義 |
|------|------|
| 🔵 RUNNING | 處理中 |
| 🟢 SUCCEEDED | 已完成 — 點擊檢視結果 |
| 🔴 FAILED | 發生錯誤 — 查看輸出了解詳情 |
| ⚪ TIMED_OUT | 超過最大執行時間 |

點擊任何工作可展開其輸出。若結果已寫回磁碟區，導覽連結可直接跳轉至 All Files 中的輸出資料夾。

### Analytics

使用 Amazon Athena 對資料執行 SQL 查詢。此功能需要管理員預先設定的 Glue Data Catalog 資料表。

---

## 資料保護

### Snapshots

檢視磁碟區快照 — 資料的時間點副本。

- **清單**: 檢視所有可用快照及其建立時間戳記
- **還原**: 點擊 "Restore" 從任何快照建立 FlexClone（即時建立的空間高效副本）。克隆擁有自己的 S3 Access Point，數秒內即可使用。

### Lock (WORM)

檢視三種機制下資料的不可變性狀態：

| 標籤頁 | 顯示內容 |
|--------|----------|
| ONTAP SnapLock | 磁碟區是否使用 Compliance 或 Enterprise 模式及保留期限 |
| S3 Object Lock | AI 輸出儲存貯體是否啟用了物件層級 WORM |
| Tamperproof Snapshot | 哪些快照已鎖定及到期時間 |

> **注意**: 設定鎖定選項需要 `storage-admin` 角色。一般使用者對此區段僅有唯讀存取權限。

### ARP/AI（勒索軟體防護）

檢視磁碟區的自主勒索軟體防護狀態。

| 顯示內容 | 含義 |
|----------|------|
| 🟢 No threats | 所有磁碟區健康 |
| 🔴 Threat detected | ARP/AI 標記了可疑活動 |
| Incident badge | 顯示目前回應階段（Detected → Contained → Investigating → Resolved） |

若偵測到威脅且您屬於 `storage-admin` 群組，可以直接從此面板執行隔離動作。

---

## 管理（需要 `storage-admin` 群組）

以下區段僅在您的帳戶屬於 `storage-admin` Cognito 群組時可見/可操作。

### Storage Dashboard

管理員登陸頁面。顯示四張卡片：
- 💾 磁碟區數量 + 平均容量使用率
- 🛡️ ARP 保護的磁碟區 + 作用中威脅
- 🔐 已鎖定（防竄改）快照
- 📊 儲存效率比率

點擊任何卡片可深入檢視詳情面板。

### Resources

卡片網格管理面板，10 個管理區域依類別組織：

| 類別 | 面板 |
|------|------|
| 儲存 | Volumes、Qtrees、Quotas、Efficiency |
| 存取控制 | Export Policies、CIFS Shares、QoS |
| 保護 | ARP Admin、Snapshot Admin、SnapLock |

### Version Diff

並排比較兩個快照之間的檔案內容。

### Audit Trail

查詢 CloudTrail S3 資料事件，回答「誰在什麼時候存取了什麼」。

---

### 4. 在手機上使用

沒有專用應用程式。在手機瀏覽器中開啟**與桌面相同的 URL**（已在 iOS Safari 與 Android
Chrome 上驗證）。

<img src="../../solutions/amplify-portal/docs/screenshots/portal-files-mobile-dark.png" alt="手機上的檔案清單（深色主題）" width="300">

**步驟**

1. 在瀏覽器中開啟管理員提供的 URL
2. 以電子郵件與密碼登入（若啟用 MFA，另需輸入 TOTP 驗證碼）。密碼管理程式的自動填入可正常使用
3. 畫面上緣有 **☰**、主題切換、語言切換與登出（⏻）。側邊欄預設隱藏
4. 點按 **☰** 會在內容上方開啟導覽。選擇區段後會自動關閉；若不選擇而想關閉，點按變暗的區域
5. 要開啟檔案，請點按該列的圖示（📄 / 🖼️ / 📕 / 📝）。預覽會以從畫面底部升起的面板開啟，
   以 **✕** 關閉
6. 要同時處理多個檔案，請點按每列左側的核取方塊。已選數量與可用操作會顯示在清單上方

**與桌面的差異**

| 項目 | 在手機上 |
|------|---------|
| 側邊欄 | 覆蓋內容的抽屜，以 **☰** 開關 |
| 大小 / 修改時間欄 | 因寬度不足而省略；仍可依名稱排序 |
| 電子郵件位址 | 隱藏（登出僅顯示圖示） |
| 檔案預覽 | 從底部升起的面板（最多佔畫面 70%）。PDF 橫向閱讀較為方便 |
| AI 助理面板 | 從右側開啟的抽屜 |

> **關於主題中的 🖥️**：它不是「切換為電腦版」按鈕。三個選項是 ☀️ 淺色、🌙 深色與
> 🖥️ **依裝置設定**，選擇 🖥️ 會跟隨 iOS 或 Android 的外觀設定（包含夜間自動切換）。

> **流量提醒**：資料夾 ZIP 下載會傳輸該資料夾底下的全部內容。使用行動網路時，請先確認檔案數量與大小。

---

## 提示與常見問題

**Q: 某些面板顯示 "ONTAP Connection Required"。**
A: 入口處於 DemoMode 或管理員尚未設定 VPC 連線。檔案瀏覽和 AI 功能仍可正常使用 — 只有 ONTAP 專屬面板（Snapshots、ARP、Lock）需要該連線。

**Q: AI 處理按鈕顯示 "PHI — AI Blocked"。**
A: 您位於受保護資料夾（`/dicom/`、`/phi/`、`/pii/` 等）中。這是設計行為 — 這些路徑中的檔案無法傳送至 AI 服務。請導覽至非保護資料夾以使用 AI 功能。

**Q: 分享連結過期太快。**
A: 分享連結使用您選擇的有效時間（5 分鐘、15 分鐘或 1 小時）的 Presigned URL。如需更長期的分享，請洽詢管理員關於 Nextcloud 整合或調整 TTL 選項。

**Q: 透過 NFS/SMB 上傳的檔案未顯示。**
A: 檔案應立即顯示（ONTAP 保證跨協定強一致性）。請嘗試重新整理檔案清單。若仍未顯示，檔案可能在子資料夾中 — 請檢查路徑。

**Q: 可以在行動裝置上使用入口嗎？**
A: 可以。步驟見「開始使用」中的「4. 在手機上使用」。

**Q: 如何變更密碼？**
A: 使用 Cognito Hosted UI 或請管理員重設。

---

## 相關文件

| 文件 | 對象 | 用途 |
|------|------|------|
| [Getting Started (Deploy)](../../solutions/amplify-portal/docs/GETTING-STARTED.md) | 管理員 | 從零開始部署入口 |
| [Admin Demo Guide](admin-resource-management-demo.md) | 儲存管理員 | 管理操作 E2E 展示 |
| [AI Features Quick Start](ai-features-quick-start.md) | 所有使用者 | 試用 Bedrock、Rekognition、Athena |
| [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) | 開發者 | 架構與自訂 |
| [Authorization Model](portal-authorization-model.md) | 安全團隊 | Cognito 群組、IAM、檔案層級存取 |
| [Compliance Guide](portal-compliance-guide.md) | 安全/合規 | 驗證監管控制 |
| [Quick Reference](portal-quick-reference.md) | 所有角色 | 單頁速查表 |
