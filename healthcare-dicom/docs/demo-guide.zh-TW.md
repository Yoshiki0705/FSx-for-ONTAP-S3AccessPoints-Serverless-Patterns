# DICOM 匿名化工作流程 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## Executive Summary

本示範展示醫療影像（DICOM）的匿名化工作流程。展示為了研究資料共享而自動移除患者個人資訊，並驗證匿名化品質的流程。

**示範的核心訊息**：從 DICOM 檔案中自動移除患者識別資訊，安全地生成可用於研究的匿名化資料集。

**預估時間**：3〜5 分鐘

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **職位** | 醫療資訊管理者 / 臨床研究資料管理員 |
| **日常業務** | 醫療影像管理、研究資料提供、隱私保護 |
| **挑戰** | 大量 DICOM 檔案的手動匿名化耗時且有錯誤風險 |
| **期望成果** | 安全可靠的匿名化與稽核軌跡自動化 |

### Persona：高橋先生（臨床研究資料管理員）

- 多機構合作研究需要匿名化 10,000+ DICOM 檔案
- 需要確實移除患者姓名、ID、出生日期等
- 「希望在保證零匿名化遺漏的同時，維持影像品質」

---

## Demo Scenario：研究資料共享的 DICOM 匿名化

### 工作流程全貌

```
DICOM 檔案     標籤解析        匿名化處理        品質驗證
(含患者資訊) →  中繼資料   →   個人資訊移除  →   匿名化確認
                  擷取            雜湊化        報告生成
```

---

## Storyboard（5 個段落 / 3〜5 分鐘）

### Section 1: Problem Statement（0:00–0:45）

**旁白要旨**：
> 為了多機構合作研究需要匿名化 10,000 個 DICOM 檔案。手動處理有錯誤風險，個人資訊外洩是不被允許的。

**Key Visual**：DICOM 檔案清單、患者資訊標籤的重點標示

### Section 2: Workflow Trigger（0:45–1:30）

**旁白要旨**：
> 指定匿名化對象資料集，啟動匿名化工作流程。設定匿名化規則（移除・雜湊化・一般化）。

**Key Visual**：工作流程啟動、匿名化規則設定畫面

### Section 3: De-identification（1:30–2:30）

**旁白要旨**：
> 自動處理各 DICOM 檔案的個人資訊標籤。患者姓名→雜湊、出生日期→年齡範圍、機構名稱→匿名代碼。影像像素資料保留。

**Key Visual**：匿名化處理進度、標籤轉換的 before/after

### Section 4: Quality Verification（2:30–3:45）

**旁白要旨**：
> 自動驗證匿名化後的檔案。掃描所有標籤確認是否有殘留的個人資訊。同時確認影像的完整性。

**Key Visual**：驗證結果 — 匿名化成功率、殘留風險標籤清單

### Section 5: Audit Report（3:45–5:00）

**旁白要旨**：
> 自動生成匿名化處理的稽核報告。記錄處理件數、移除標籤數、驗證結果。可作為研究倫理委員會的提交資料使用。

**Key Visual**：稽核報告（處理摘要 + 合規軌跡）

---

## Screen Capture Plan

| # | 畫面 | 段落 |
|---|------|-----------|
| 1 | DICOM 檔案清單（匿名化前） | Section 1 |
| 2 | 工作流程啟動・規則設定 | Section 2 |
| 3 | 匿名化處理進度 | Section 3 |
| 4 | 品質驗證結果 | Section 4 |
| 5 | 稽核報告 | Section 5 |

---

## Narration Outline

| 段落 | 時間 | 關鍵訊息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「大量 DICOM 的匿名化遺漏是不被允許的」 |
| Trigger | 0:45–1:30 | 「設定匿名化規則並啟動工作流程」 |
| Processing | 1:30–2:30 | 「自動移除個人資訊標籤，維持影像品質」 |
| Verification | 2:30–3:45 | 「全標籤掃描確認零匿名化遺漏」 |
| Report | 3:45–5:00 | 「自動生成稽核軌跡，可提交倫理委員會」 |

---

## Sample Data Requirements

| # | 資料 | 用途 |
|---|--------|------|
| 1 | 測試 DICOM 檔案（20 個） | 主要處理對象 |
| 2 | 複雜標籤結構的 DICOM（5 個） | 邊緣案例 |
| 3 | 含私有標籤的 DICOM（3 個） | 高風險驗證 |

---

## Timeline

### 1 週內可達成

| 任務 | 所需時間 |
|--------|---------|
| 測試 DICOM 資料準備 | 3 小時 |
| 管線執行確認 | 2 小時 |
| 畫面擷取取得 | 2 小時 |
| 旁白稿撰寫 | 2 小時 |
| 影片編輯 | 4 小時 |

### Future Enhancements

- 影像內文字（燒入）的自動偵測・移除
- FHIR 連動的匿名化對應管理
- 差分匿名化（追加資料的增量處理）

---

## Technical Notes

| 元件 | 角色 |
|--------------|------|
| Step Functions | 工作流程編排 |
| Lambda (Tag Parser) | DICOM 標籤解析・個人資訊偵測 |
| Lambda (De-identifier) | 標籤匿名化處理 |
| Lambda (Verifier) | 匿名化品質驗證 |
| Lambda (Report Generator) | 稽核報告生成 |

### 備援方案

| 情境 | 對應 |
|---------|------|
| DICOM 解析失敗 | 使用預處理資料 |
| 驗證錯誤 | 切換至手動確認流程 |

---

*本文件為技術簡報用示範影片的製作指南。*

---

## 關於輸出目的地：FSxN S3 Access Point (Pattern A)

UC5 healthcare-dicom 分類為 **Pattern A: Native S3AP Output**
（參照 `docs/output-destination-patterns.md`）。

**設計**：DICOM 中繼資料、匿名化結果、PII 偵測日誌全部透過 FSxN S3 Access Point
寫回與原始 DICOM 醫用影像**相同的 FSx ONTAP 磁碟區**。不會建立標準 S3 儲存貯體
（"no data movement" 模式）。

**CloudFormation 參數**：
- `S3AccessPointAlias`：輸入資料讀取用 S3 AP Alias
- `S3AccessPointOutputAlias`：輸出寫入用 S3 AP Alias（可與輸入相同）

**部署範例**：
```bash
aws cloudformation deploy \
  --template-file healthcare-dicom/template-deploy.yaml \
  --stack-name fsxn-healthcare-dicom-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (其他必要參數)
```

**從 SMB/NFS 使用者的視角**：
```
/vol/dicom/
  ├── patient_001/study_A/image.dcm    # 原始 DICOM
  └── metadata/patient_001/             # AI 匿名化結果（同一磁碟區內）
      └── study_A_anonymized.json
```

關於 AWS 規格上的限制，請參照
[專案 README 的「AWS 規格上的限制與因應對策」段落](../../README.md#aws-仕様上の制約と回避策)
以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)。

---

## 已驗證的 UI/UX 螢幕截圖

與 Phase 7 UC15/16/17 和 UC6/11/14 的示範相同方針，以**終端使用者在日常業務中實際
看到的 UI/UX 畫面**為對象。技術人員視圖（Step Functions 圖表、CloudFormation
堆疊事件等）集中於 `docs/verification-results-*.md`。

### 此使用案例的驗證狀態

- ⚠️ **E2E 驗證**：僅部分功能（正式環境建議追加驗證）
- 📸 **UI/UX 截圖**: ✅ SFN Graph 完成 (Phase 8 Theme D, commit c66084f)

### 2026-05-10 重新部署驗證時拍攝（以 UI/UX 為中心）

#### UC5 Step Functions Graph view（SUCCEEDED）

![UC5 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc5-demo/uc5-stepfunctions-graph.png)

Step Functions Graph view 以顏色視覺化各 Lambda / Parallel / Map 狀態的執行狀況，
是終端使用者最重要的畫面。

### 既有螢幕截圖（Phase 1-6 的相關部分）

![UC5 Step Functions 圖表視圖 (SUCCEEDED)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-succeeded.png)

![UC5 Step Functions 圖表 (縮放 — 各步驟詳細)](../../docs/screenshots/masked/uc5-demo/step-functions-graph-zoomed.png)

### 重新驗證時的 UI/UX 對象畫面（建議拍攝清單）

- S3 輸出儲存貯體（dicom-metadata/、deid-reports/、diagnoses/）
- Comprehend Medical 實體偵測結果（Cross-Region）
- DICOM 匿名化後中繼資料 JSON

### 拍攝指南

1. **事前準備**：
   - `bash scripts/verify_phase7_prerequisites.sh` 確認前提（共用 VPC/S3 AP 有無）
   - `UC=healthcare-dicom bash scripts/package_generic_uc.sh` 打包 Lambda
   - `bash scripts/deploy_generic_ucs.sh UC5` 部署

2. **範例資料配置**：
   - 透過 S3 AP Alias 上傳範例檔案至 `dicom/` 前綴
   - 啟動 Step Functions `fsxn-healthcare-dicom-demo-workflow`（輸入 `{}`）

3. **拍攝**（關閉 CloudShell・終端機，瀏覽器右上角的使用者名稱塗黑）：
   - S3 輸出儲存貯體 `fsxn-healthcare-dicom-demo-output-<account>` 的俯瞰
   - AI/ML 輸出 JSON 的預覽（參考 `build/preview_*.html` 格式）
   - SNS 郵件通知（如適用）

4. **遮罩處理**：
   - `python3 scripts/mask_uc_demos.py healthcare-dicom-demo` 自動遮罩
   - 依照 `docs/screenshots/MASK_GUIDE.md` 追加遮罩（如需要）

5. **清理**：
   - `bash scripts/cleanup_generic_ucs.sh UC5` 刪除
   - VPC Lambda ENI 釋放需 15-30 分鐘（AWS 規格）
