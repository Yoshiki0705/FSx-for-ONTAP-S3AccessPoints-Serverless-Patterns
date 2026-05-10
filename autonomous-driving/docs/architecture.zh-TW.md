# UC9: 自動駕駛 / ADAS — 影像・LiDAR 前處理・品質檢查・標註

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | 繁體中文 | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for NetApp ONTAP"]
        DATA["影片 / LiDAR 資料<br/>.bag, .pcd, .mp4, .h264"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 內執行<br/>• S3 AP 檔案偵測<br/>• .bag/.pcd/.mp4/.h264 篩選<br/>• Manifest 生成"]
        FE["2️⃣ Frame Extraction Lambda<br/>• 從影片提取關鍵影格<br/>• Rekognition DetectLabels<br/>  (車輛, 行人, 交通標誌)<br/>• 影格影像 S3 輸出"]
        PC["3️⃣ Point Cloud QC Lambda<br/>• LiDAR 點雲資料取得<br/>• 品質檢查<br/>  (點密度, 座標一致性, NaN 驗證)<br/>• QC 報告生成"]
        AM["4️⃣ Annotation Manager Lambda<br/>• Bedrock 標註建議<br/>• COCO 相容 JSON 生成<br/>• 標註作業管理"]
        SM["5️⃣ SageMaker Invoke Lambda<br/>• Batch Transform 執行<br/>• 點雲分割推論<br/>• 物體偵測結果輸出"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        FRAMES["frames/*.jpg<br/>提取關鍵影格"]
        QCR["qc-reports/*.json<br/>點雲品質報告"]
        ANNOT["annotations/*.json<br/>COCO 標註"]
        INFER["inference/*.json<br/>ML 推論結果"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>處理完成通知"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> FE
    DISC --> PC
    FE --> AM
    PC --> AM
    AM --> SM
    FE --> FRAMES
    PC --> QCR
    AM --> ANNOT
    SM --> INFER
    SM --> SNS
```

---

## Data Flow Detail

### Input
| Item | Description |
|------|-------------|
| **Source** | FSx for NetApp ONTAP volume |
| **File Types** | .bag, .pcd, .mp4, .h264 (ROS bag, LiDAR 點雲, 行車記錄器影片) |
| **Access Method** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Read Strategy** | 取得完整檔案(影格提取・點雲分析所需) |

### Processing
| Step | Service | Function |
|------|---------|----------|
| Discovery | Lambda (VPC) | 透過 S3 AP 偵測影片/LiDAR 資料，生成 Manifest |
| Frame Extraction | Lambda + Rekognition | 從影片提取關鍵影格，物體偵測 |
| Point Cloud QC | Lambda | LiDAR 點雲品質檢查(點密度、座標一致性、NaN 驗證) |
| Annotation Manager | Lambda + Bedrock | 生成標註建議，輸出 COCO JSON |
| SageMaker Invoke | Lambda + SageMaker | 透過 Batch Transform 進行點雲分割推論 |

### Output
| Artifact | Format | Description |
|----------|--------|-------------|
| Key Frames | `frames/YYYY/MM/DD/{stem}_frame_{n}.jpg` | 提取關鍵影格影像 |
| QC Report | `qc-reports/YYYY/MM/DD/{stem}_qc.json` | 點雲品質檢查結果 |
| Annotations | `annotations/YYYY/MM/DD/{stem}_coco.json` | COCO 相容標註 |
| Inference | `inference/YYYY/MM/DD/{stem}_segmentation.json` | ML 推論結果 |
| SNS Notification | Email | 處理完成通知(處理數量・品質分數) |

---

## Key Design Decisions

1. **S3 AP over NFS** — Lambda 無需 NFS 掛載，透過 S3 API 取得大容量資料
2. **並行處理** — Frame Extraction 與 Point Cloud QC 並行執行，縮短處理時間
3. **Rekognition + SageMaker 二階段架構** — Rekognition 進行即時物體偵測，SageMaker 進行高精度分割
4. **COCO 相容格式** — 採用業界標準標註格式，確保與下游 ML 管線的相容性
5. **品質閘門** — Point Cloud QC 提早篩選不符品質標準的資料
6. **輪詢基礎** — S3 AP 不支援事件通知，因此採用定期排程執行

---

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for NetApp ONTAP | 自動駕駛資料儲存(影片・LiDAR 保管) |
| S3 Access Points | 對 ONTAP volume 的無伺服器存取 |
| EventBridge Scheduler | 定期觸發器 |
| Step Functions | 工作流程編排 |
| Lambda (Python 3.13) | 運算(Discovery, Frame Extraction, Point Cloud QC, Annotation Manager, SageMaker Invoke) |
| Lambda SnapStart | 減少冷啟動(選擇性啟用，Phase 6A) |
| Amazon Rekognition | 物體偵測(車輛、行人、交通標誌) |
| Amazon SageMaker | 推論(4-way 路由: Batch / Serverless / Provisioned / Components) |
| SageMaker Inference Components | 真正的 scale-to-zero(MinInstanceCount=0，Phase 6B) |
| Amazon Bedrock | 標註建議生成 |
| SNS | 處理完成通知 |
| Secrets Manager | ONTAP REST API 認證資訊管理 |
| CloudWatch + X-Ray | 可觀測性 |
| CloudFormation Guard Hooks | 部署時政策強制執行(Phase 6B) |

---

## Inference Routing (Phase 4/5/6B)

UC9 支援 4-way 推論路由。透過 `InferenceType` 參數選擇:

| 路徑 | 條件 | 延遲 | 閒置成本 |
|------|------|-----------|-------------|
| Batch Transform | `InferenceType=none` or `file_count >= threshold` | 分鐘〜小時 | $0 |
| Serverless Inference | `InferenceType=serverless` | 6–45 秒 (cold) | $0 |
| Provisioned Endpoint | `InferenceType=provisioned` | 毫秒 | ~$140/月 |
| **Inference Components** | `InferenceType=components` | 2–5 分鐘 (scale-from-zero) | **$0** |

### Inference Components (Phase 6B)

Inference Components 透過 `MinInstanceCount=0` 實現真正的 scale-to-zero:

```
SageMaker Endpoint (持續存在，閒置時成本 $0)
  └── Inference Component (MinInstanceCount=0)
       ├── [閒置] → 0 個執行個體 → $0/小時
       ├── [請求到達] → Auto Scaling → 執行個體啟動 (2–5 分鐘)
       └── [閒置逾時] → Scale-in → 0 個執行個體
```

啟用: `EnableInferenceComponents=true` + `InferenceType=components`

---

## Lambda SnapStart (Phase 6A)

所有 Lambda 函數可選擇性啟用 SnapStart:

- **啟用**: `EnableSnapStart=true` 更新堆疊 + `scripts/enable-snapstart.sh` 發布版本
- **效果**: 冷啟動 1–3 秒 → 100–500ms
- **限制**: 僅適用於 Published Versions($LATEST 無效)

詳細資訊: [SnapStart 指南](../../docs/snapstart-guide.md)
