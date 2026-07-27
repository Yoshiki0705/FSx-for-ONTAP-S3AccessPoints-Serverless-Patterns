# 檔案入口 — 快速參考卡

> 🌐 Language: [English](../en/portal-quick-reference.md) | [日本語](../ja/portal-quick-reference.md) | [한국어](../ko/portal-quick-reference.md) | [简体中文](../zh-CN/portal-quick-reference.md) | **繁體中文** | [Français](../fr/portal-quick-reference.md) | [Deutsch](../de/portal-quick-reference.md) | [Español](../es/portal-quick-reference.md)

入口日常操作的單頁速查手冊。可列印或加入書籤。

---

## 導覽

| 側邊欄區域 | 功能 |
|:---:|------|
| 📂 All Files | 瀏覽、預覽、下載、共用、AI 問答 |
| ⭐ Favorites | 已釘選的檔案 |
| 🕐 Recent | 您的存取歷史 |
| 📤 Upload | 拖放上傳（最大 5 GB/檔案） |
| ⚡ AI Processing | 對資料夾觸發 AI/ML 工作流程 |
| 📋 Job History | 歷史作業結果 + 狀態 |
| 📊 Analytics | Athena SQL 查詢 |
| 📸 Snapshots | 時間點副本 + FlexClone 還原 |
| 🔒 Lock | SnapLock / S3 Object Lock / Tamperproof |
| 🛡️ ARP/AI | 勒索軟體保護狀態 |
| 🔧 Resources | 儲存管理面板（僅管理員） |
| 🔄 Version Diff | 跨快照比較檔案 |
| 🔍 Audit Trail | 誰在何時存取了什麼 |

---

## 常見任務（所有使用者）

| 我想... | 操作方法 |
|---------|----------|
| 瀏覽檔案 | 側邊欄 → 📂 All Files → 點擊資料夾 |
| 預覽 PDF | 點擊檔案旁的 📕 |
| 預覽 Word 文件 | 點擊檔案旁的 📝 |
| 下載檔案 | 點擊檔案旁的 📄 |
| 共用檔案連結 | 點擊 🔗 → 選擇 TTL → 複製 URL |
| 向 AI 詢問檔案內容 | 選擇檔案 → 在右側面板輸入問題 |
| 偵測影像中的物件 | 選擇影像 → 右側面板中的 "Detect Objects" |
| 上傳檔案 | 側邊欄 → 📤 Upload → 拖放 |
| 對資料夾執行 AI | 在 All Files 中，點擊檔案清單上方的 ⚡ |
| 檢視作業結果 | 側邊欄 → 📋 Job History → 點擊作業 |
| 從快照還原 | 側邊欄 → 📸 Snapshots → "Restore" 按鈕 |
| 切換語言 | 點擊頂部列的 🌐 |

---

## 常見任務（合規 / 安全）

| 我想... | 操作方法 |
|---------|----------|
| 檢查勒索軟體狀態 | 側邊欄 → 🛡️ ARP/AI |
| 驗證 WORM 鎖定 | 側邊欄 → 🔒 Lock → SnapLock 標籤 |
| 檢查輸出儲存貯體鎖定 | 側邊欄 → 🔒 Lock → S3 Object Lock 標籤 |
| 檢視已鎖定快照 | 側邊欄 → 🔒 Lock → Tamperproof 標籤 |
| 檢閱存取稽核 | 側邊欄 → 🔍 Audit Trail |
| 驗證 PHI 防護欄 | All Files → 導覽至 `/dicom/` → 按鈕顯示 🚫 |

---

## 常見任務（儲存管理員）

| 我想... | 操作方法 |
|---------|----------|
| 檢視健康儀表板 | 側邊欄 → 🔧 Resources（儀表板首先顯示） |
| 管理卷 | Resources → Storage → Volumes |
| 設定匯出政策 | Resources → Access Control → Export Policies |
| 在卷上啟用 ARP | Resources → Protection → ARP Admin |
| 鎖定快照 | Resources → Protection → Snapshot Admin → Lock 表單 |
| 阻止受感染使用者 | 側邊欄 → 🛡️ ARP/AI → Contain 標籤 → Block SMB User |
| 解決後解除阻止 | 側邊欄 → 🛡️ ARP/AI → Unblock 標籤 |
| 檢視 EMS 警示 | Resources →（監控中顯示 EMS 事件） |

---

## 鍵盤快速鍵

| 按鍵 | 操作 |
|------|------|
| `Tab` | 在互動元素間移動 |
| `Enter` | 啟用按鈕 / 開啟資料夾 |
| `Escape` | 關閉對話方塊 / 關閉面板 |

---

## 狀態指示器

| 圖示 | 意義 |
|:---:|------|
| 🟢 | 健康 / 無威脅 / 已解決 |
| 🔴 | 偵測到威脅 / 錯誤 |
| 🟠 | 已遏制（事件進行中） |
| 🟡 | 調查中 |
| 🚫 | PHI — AI 已阻止（防護欄啟用） |
| ⚠️ | 警告（容量 > 85% 等） |

---

## 存取層級

| 群組 | 可執行操作 | 不可執行操作 |
|------|-----------|-------------|
| `authenticated` | 瀏覽、下載、上傳、AI、檢視保護狀態 | 修改儲存設定 |
| `storage-admin` | 以上所有 + 建立/刪除卷、鎖定快照、阻止使用者、管理政策 | — |

---

## 快速疑難排解

| 症狀 | 解決方法 |
|------|----------|
| "ONTAP Connection Required" | DemoMode 下正常。請聯繫管理員設定 VPC。 |
| AI 按鈕顯示 🚫 | 您在 PHI 保護資料夾中。請導覽至其他位置。 |
| 共用連結已過期 | 產生新連結（🔗）。最大 TTL = 1 小時。 |
| NFS 寫入後檔案未顯示 | 重新整理檔案清單。應立即顯示。 |
| 持續載入中 | 檢查網路。嘗試登出 → 重新登入。 |

---

## 文件導覽

| 您的角色 | 從這裡開始 |
|---------|-----------|
| 一般使用者（日常任務） | [使用者指南](portal-user-guide.md) |
| 安全 / 合規人員 | [合規指南](portal-compliance-guide.md) |
| 儲存管理員 | [管理員示範指南](admin-resource-management-demo.md) |
| IT 管理員（部署） | [入門指南](../../solutions/amplify-portal/docs/GETTING-STARTED.md) |
| 開發者（客製化） | [實作指南](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) |
