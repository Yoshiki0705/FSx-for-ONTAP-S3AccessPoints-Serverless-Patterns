# UC9: 自动驾驶 / ADAS — 视频与 LiDAR 预处理、质量检查与标注

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | 简体中文 | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## 端到端架构（输入 → 输出）

---

## 高层级流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FSx for NetApp ONTAP                                 │
│                                                                              │
│  /vol/driving_data/                                                          │
│  ├── rosbag/drive_20240315_001.bag       (ROS bag video+LiDAR)               │
│  ├── lidar/scan_20240315_001.pcd         (LiDAR point cloud)                 │
│  ├── camera/front_20240315_001.mp4       (Dashcam video)                     │
│  └── camera/rear_20240315_001.h264       (Rear camera video)                 │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      S3 Access Point (Data Path)                              │
│                                                                              │
│  Alias: fsxn-driving-vol-ext-s3alias                                         │
│  • ListObjectsV2 (video/LiDAR data discovery)                                │
│  • GetObject (BAG/PCD/MP4/H264 retrieval)                                    │
│  • No NFS/SMB mount required from Lambda                                     │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    EventBridge Scheduler (Trigger)                            │
│                                                                              │
│  Schedule: rate(1 hour) — configurable                                       │
│  Target: Step Functions State Machine                                        │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    AWS Step Functions (Orchestration)                         │
│                                                                              │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Discovery  │─▶│Frame Extract │─▶│Point Cloud QC│─▶│Annotation Manager│   │
│  │ Lambda     │  │ Lambda       │  │ Lambda       │  │ Lambda           │   │
│  │           │  │             │  │             │  │                 │   │
│  │ • VPC内    │  │ • Key frame │  │ • Point     │  │ • Bedrock       │   │
│  │ • S3 AP   │  │   extraction│  │   density   │  │   suggestions   │   │
│  │ • BAG/PCD │  │ • Rekognition│  │ • Coordinate│  │ • SageMaker     │   │
│  │   /MP4    │  │   detection │  │   integrity │  │   inference     │   │
│  └───────────┘  └──────────────┘  │ • NaN check │  │ • COCO JSON     │   │
│                                    └──────────────┘  └──────────────────┘   │
│                                                          │                   │
│                                                          ▼                   │
│                                                 ┌────────────────┐          │
│                                                 │SageMaker Invoke │          │
│                                                 │ Lambda          │          │
│                                                 │                │          │
│                                                 │ • Batch Transform│         │
│                                                 │ • Point cloud   │          │
│                                                 │   segmentation  │          │
│                                                 └────────────────┘          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Output (S3 Bucket)                                    │
│                                                                              │
│  s3://{stack}-output-{account}/                                              │
│  ├── frames/YYYY/MM/DD/                                                      │
│  │   └── drive_001_frame_0001.jpg    ← Extracted key frames                 │
│  ├── qc-reports/YYYY/MM/DD/                                                  │
│  │   └── scan_001_qc.json           ← Point cloud quality report            │
│  ├── annotations/YYYY/MM/DD/                                                 │
│  │   └── drive_001_coco.json        ← COCO format annotations              │
│  └── inference/YYYY/MM/DD/                                                   │
│      └── scan_001_segmentation.json  ← Segmentation results                │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Mermaid 图表

```mermaid
flowchart TB
    subgraph INPUT["📥 输入 — FSx for NetApp ONTAP"]
        DATA["视频 / LiDAR 数据<br/>.bag, .pcd, .mp4, .h264"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ 触发器"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions 工作流"]
        DISC["1️⃣ Discovery Lambda<br/>• 在 VPC 内运行<br/>• S3 AP 文件发现<br/>• .bag/.pcd/.mp4/.h264 过滤<br/>• 清单生成"]
        FE["2️⃣ Frame Extraction Lambda<br/>• 从视频中提取关键帧<br/>• Rekognition DetectLabels<br/>  （车辆、行人、交通标志）<br/>• 帧图像 S3 输出"]
        PC["3️⃣ Point Cloud QC Lambda<br/>• LiDAR 点云检索<br/>• 质量检查<br/>  （点密度、坐标完整性、NaN 验证）<br/>• QC 报告生成"]
        AM["4️⃣ Annotation Manager Lambda<br/>• Bedrock 标注建议<br/>• COCO 兼容 JSON 生成<br/>• 标注任务管理"]
        SM["5️⃣ SageMaker Invoke Lambda<br/>• Batch Transform 执行<br/>• 点云分割推理<br/>• 目标检测结果输出"]
    end

    subgraph OUTPUT["📤 输出 — S3 Bucket"]
        FRAMES["frames/*.jpg<br/>提取的关键帧"]
        QCR["qc-reports/*.json<br/>点云质量报告"]
        ANNOT["annotations/*.json<br/>COCO 标注"]
        INFER["inference/*.json<br/>ML 推理结果"]
    end

    subgraph NOTIFY["📧 通知"]
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

## 数据流详情

### 输入
| 项目 | 说明 |
|------|------|
| **来源** | FSx for NetApp ONTAP 卷 |
| **文件类型** | .bag, .pcd, .mp4, .h264（ROS bag、LiDAR 点云、行车记录仪视频） |
| **访问方式** | S3 Access Point（ListObjectsV2 + GetObject） |
| **读取策略** | 完整文件检索（帧提取和点云分析所需） |

### 处理
| 步骤 | 服务 | 功能 |
|------|------|------|
| Discovery | Lambda（VPC） | 通过 S3 AP 发现视频/LiDAR 数据，生成清单 |
| Frame Extraction | Lambda + Rekognition | 从视频中提取关键帧，目标检测 |
| Point Cloud QC | Lambda | LiDAR 点云质量检查（点密度、坐标完整性、NaN 验证） |
| Annotation Manager | Lambda + Bedrock | 生成标注建议，COCO JSON 输出 |
| SageMaker Invoke | Lambda + SageMaker | 点云分割推理的 Batch Transform |

### 输出
| 产出物 | 格式 | 说明 |
|--------|------|------|
| 关键帧 | `frames/YYYY/MM/DD/{stem}_frame_{n}.jpg` | 提取的关键帧图像 |
| QC 报告 | `qc-reports/YYYY/MM/DD/{stem}_qc.json` | 点云质量检查结果 |
| 标注 | `annotations/YYYY/MM/DD/{stem}_coco.json` | COCO 兼容标注 |
| 推理结果 | `inference/YYYY/MM/DD/{stem}_segmentation.json` | ML 推理结果 |
| SNS 通知 | 电子邮件 | 处理完成通知（数量和质量分数） |

---

## 关键设计决策

1. **S3 AP 优于 NFS** — Lambda 无需 NFS 挂载；通过 S3 API 检索大数据
2. **并行处理** — Frame Extraction 和 Point Cloud QC 并行运行以缩短处理时间
3. **Rekognition + SageMaker 两阶段** — Rekognition 用于即时目标检测，SageMaker 用于高精度分割
4. **COCO 兼容格式** — 行业标准标注格式确保与下游 ML 管道的兼容性
5. **质量门控** — Point Cloud QC 在管道早期过滤不满足质量标准的数据
6. **轮询（非事件驱动）** — S3 AP 不支持事件通知，因此使用定期计划执行

---

## 使用的 AWS 服务

| 服务 | 角色 |
|------|------|
| FSx for NetApp ONTAP | 自动驾驶数据存储（视频和 LiDAR） |
| S3 Access Points | 对 ONTAP 卷的无服务器访问 |
| EventBridge Scheduler | 定期触发器 |
| Step Functions | 工作流编排 |
| Lambda | 计算（Discovery、Frame Extraction、Point Cloud QC、Annotation Manager、SageMaker Invoke） |
| Amazon Rekognition | 目标检测（车辆、行人、交通标志） |
| Amazon SageMaker | Batch Transform（点云分割推理） |
| Amazon Bedrock | 标注建议生成 |
| SNS | 处理完成通知 |
| Secrets Manager | ONTAP REST API 凭证管理 |
| CloudWatch + X-Ray | 可观测性 |
