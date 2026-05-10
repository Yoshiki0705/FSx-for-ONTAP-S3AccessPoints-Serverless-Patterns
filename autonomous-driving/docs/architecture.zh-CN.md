# UC9: 自动驾驶 / ADAS — 视频·LiDAR 预处理·质量检查·标注

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | 简体中文 | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for NetApp ONTAP"]
        DATA["视频 / LiDAR 数据<br/>.bag, .pcd, .mp4, .h264"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC内执行<br/>• S3 AP 文件检测<br/>• .bag/.pcd/.mp4/.h264 过滤<br/>• Manifest 生成"]
        FE["2️⃣ Frame Extraction Lambda<br/>• 从视频提取关键帧<br/>• Rekognition DetectLabels<br/>  (车辆, 行人, 交通标志)<br/>• 帧图像 S3 输出"]
        PC["3️⃣ Point Cloud QC Lambda<br/>• LiDAR 点云数据获取<br/>• 质量检查<br/>  (点密度, 坐标一致性, NaN验证)<br/>• QC 报告生成"]
        AM["4️⃣ Annotation Manager Lambda<br/>• Bedrock 标注建议<br/>• COCO 兼容 JSON 生成<br/>• 标注作业管理"]
        SM["5️⃣ SageMaker Invoke Lambda<br/>• Batch Transform 执行<br/>• 点云分割推理<br/>• 物体检测结果输出"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        FRAMES["frames/*.jpg<br/>提取的关键帧"]
        QCR["qc-reports/*.json<br/>点云质量报告"]
        ANNOT["annotations/*.json<br/>COCO 标注"]
        INFER["inference/*.json<br/>ML 推理结果"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>处理完成通知"]
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
| **File Types** | .bag, .pcd, .mp4, .h264 (ROS bag, LiDAR 点云, 行车记录仪视频) |
| **Access Method** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Read Strategy** | 获取完整文件（帧提取和点云分析所需） |

### Processing
| Step | Service | Function |
|------|---------|----------|
| Discovery | Lambda (VPC) | 通过 S3 AP 检测视频/LiDAR 数据，生成 Manifest |
| Frame Extraction | Lambda + Rekognition | 从视频提取关键帧，物体检测 |
| Point Cloud QC | Lambda | LiDAR 点云质量检查（点密度、坐标一致性、NaN 验证） |
| Annotation Manager | Lambda + Bedrock | 生成标注建议，输出 COCO JSON |
| SageMaker Invoke | Lambda + SageMaker | 通过 Batch Transform 进行点云分割推理 |

### Output
| Artifact | Format | Description |
|----------|--------|-------------|
| Key Frames | `frames/YYYY/MM/DD/{stem}_frame_{n}.jpg` | 提取的关键帧图像 |
| QC Report | `qc-reports/YYYY/MM/DD/{stem}_qc.json` | 点云质量检查结果 |
| Annotations | `annotations/YYYY/MM/DD/{stem}_coco.json` | COCO 兼容标注 |
| Inference | `inference/YYYY/MM/DD/{stem}_segmentation.json` | ML 推理结果 |
| SNS Notification | Email | 处理完成通知（处理数量·质量评分） |

---

## Key Design Decisions

1. **S3 AP over NFS** — 无需从 Lambda 挂载 NFS，通过 S3 API 获取大容量数据
2. **并行处理** — Frame Extraction 和 Point Cloud QC 并行执行，缩短处理时间
3. **Rekognition + SageMaker 两阶段架构** — Rekognition 进行即时物体检测，SageMaker 进行高精度分割
4. **COCO 兼容格式** — 采用行业标准标注格式，确保与下游 ML 流水线的兼容性
5. **质量门控** — Point Cloud QC 早期过滤不符合质量标准的数据
6. **基于轮询** — 由于 S3 AP 不支持事件通知，采用定期调度执行

---

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for NetApp ONTAP | 自动驾驶数据存储（视频·LiDAR 保存） |
| S3 Access Points | 对 ONTAP 卷的无服务器访问 |
| EventBridge Scheduler | 定期触发器 |
| Step Functions | 工作流编排 |
| Lambda (Python 3.13) | 计算（Discovery, Frame Extraction, Point Cloud QC, Annotation Manager, SageMaker Invoke） |
| Lambda SnapStart | 减少冷启动（可选启用，Phase 6A） |
| Amazon Rekognition | 物体检测（车辆、行人、交通标志） |
| Amazon SageMaker | 推理（4路路由: Batch / Serverless / Provisioned / Components） |
| SageMaker Inference Components | 真正的 scale-to-zero（MinInstanceCount=0，Phase 6B） |
| Amazon Bedrock | 生成标注建议 |
| SNS | 处理完成通知 |
| Secrets Manager | ONTAP REST API 凭证管理 |
| CloudWatch + X-Ray | 可观测性 |
| CloudFormation Guard Hooks | 部署时策略强制执行（Phase 6B） |

---

## Inference Routing (Phase 4/5/6B)

UC9 支持 4路推理路由。通过 `InferenceType` 参数选择:

| 路径 | 条件 | 延迟 | 空闲成本 |
|------|------|-----------|-------------|
| Batch Transform | `InferenceType=none` or `file_count >= threshold` | 分钟~小时 | $0 |
| Serverless Inference | `InferenceType=serverless` | 6–45 秒 (cold) | $0 |
| Provisioned Endpoint | `InferenceType=provisioned` | 毫秒 | ~$140/月 |
| **Inference Components** | `InferenceType=components` | 2–5 分钟 (scale-from-zero) | **$0** |

### Inference Components (Phase 6B)

Inference Components 通过 `MinInstanceCount=0` 实现真正的 scale-to-zero:

```
SageMaker Endpoint (始终存在，空闲时成本 $0)
  └── Inference Component (MinInstanceCount=0)
       ├── [空闲] → 0 实例 → $0/小时
       ├── [请求到达] → Auto Scaling → 实例启动 (2–5 分钟)
       └── [空闲超时] → Scale-in → 0 实例
```

启用: `EnableInferenceComponents=true` + `InferenceType=components`

---

## Lambda SnapStart (Phase 6A)

所有 Lambda 函数可选启用 SnapStart:

- **启用**: 通过 `EnableSnapStart=true` 更新堆栈 + `scripts/enable-snapstart.sh` 发布版本
- **效果**: 冷启动 1–3 秒 → 100–500ms
- **限制**: 仅适用于 Published Versions（对 $LATEST 无效）

详情: [SnapStart 指南](../../docs/snapstart-guide.md)
