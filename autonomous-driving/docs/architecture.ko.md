# UC9: 자율주행 / ADAS — 영상 및 LiDAR 전처리, 품질 검사, 어노테이션

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | 한국어 | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## 엔드투엔드 아키텍처 (입력 → 출력)

---

## 아키텍처 다이어그램

```mermaid
flowchart TB
    subgraph INPUT["📥 입력 — FSx for NetApp ONTAP"]
        DATA["영상 / LiDAR 데이터<br/>.bag, .pcd, .mp4, .h264"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ 트리거"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions 워크플로"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 내부에서 실행<br/>• S3 AP 파일 탐색<br/>• .bag/.pcd/.mp4/.h264 필터<br/>• 매니페스트 생성"]
        FE["2️⃣ Frame Extraction Lambda<br/>• 영상에서 키 프레임 추출<br/>• Rekognition DetectLabels<br/>  (차량, 보행자, 교통 표지판)<br/>• 프레임 이미지 S3 출력"]
        PC["3️⃣ Point Cloud QC Lambda<br/>• LiDAR 포인트 클라우드 검색<br/>• 품질 검사<br/>  (포인트 밀도, 좌표 무결성, NaN 검증)<br/>• QC 보고서 생성"]
        AM["4️⃣ Annotation Manager Lambda<br/>• Bedrock 어노테이션 제안<br/>• COCO 호환 JSON 생성<br/>• 어노테이션 작업 관리"]
        SM["5️⃣ SageMaker Invoke Lambda<br/>• Batch Transform 실행<br/>• 포인트 클라우드 세그멘테이션 추론<br/>• 객체 탐지 결과 출력"]
    end

    subgraph OUTPUT["📤 출력 — S3 Bucket"]
        FRAMES["frames/*.jpg<br/>추출된 키 프레임"]
        QCR["qc-reports/*.json<br/>포인트 클라우드 품질 보고서"]
        ANNOT["annotations/*.json<br/>COCO 어노테이션"]
        INFER["inference/*.json<br/>ML 추론 결과"]
    end

    subgraph NOTIFY["📧 알림"]
        SNS["Amazon SNS<br/>처리 완료 알림"]
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

## 데이터 흐름 상세

### 입력
| 항목 | 설명 |
|------|------|
| **소스** | FSx for NetApp ONTAP 볼륨 |
| **파일 유형** | .bag, .pcd, .mp4, .h264 (ROS bag, LiDAR 포인트 클라우드, 대시캠 영상) |
| **접근 방식** | S3 Access Point (ListObjectsV2 + GetObject) |
| **읽기 전략** | 전체 파일 검색 (프레임 추출 및 포인트 클라우드 분석에 필요) |

### 처리
| 단계 | 서비스 | 기능 |
|------|--------|------|
| Discovery | Lambda (VPC) | S3 AP를 통해 영상/LiDAR 데이터 탐색, 매니페스트 생성 |
| Frame Extraction | Lambda + Rekognition | 영상에서 키 프레임 추출, 객체 탐지 |
| Point Cloud QC | Lambda | LiDAR 포인트 클라우드 품질 검사 (포인트 밀도, 좌표 무결성, NaN 검증) |
| Annotation Manager | Lambda + Bedrock | 어노테이션 제안 생성, COCO JSON 출력 |
| SageMaker Invoke | Lambda + SageMaker | 포인트 클라우드 세그멘테이션 추론을 위한 Batch Transform |

### 출력
| 산출물 | 형식 | 설명 |
|--------|------|------|
| 키 프레임 | `frames/YYYY/MM/DD/{stem}_frame_{n}.jpg` | 추출된 키 프레임 이미지 |
| QC 보고서 | `qc-reports/YYYY/MM/DD/{stem}_qc.json` | 포인트 클라우드 품질 검사 결과 |
| 어노테이션 | `annotations/YYYY/MM/DD/{stem}_coco.json` | COCO 호환 어노테이션 |
| 추론 결과 | `inference/YYYY/MM/DD/{stem}_segmentation.json` | ML 추론 결과 |
| SNS 알림 | 이메일 | 처리 완료 알림 (건수 및 품질 점수) |

---

## 주요 설계 결정

1. **NFS 대신 S3 AP** — Lambda에서 NFS 마운트 불필요; 대용량 데이터를 S3 API로 검색
2. **병렬 처리** — Frame Extraction과 Point Cloud QC를 병렬 실행하여 처리 시간 단축
3. **Rekognition + SageMaker 2단계** — Rekognition으로 즉시 객체 탐지, SageMaker로 고정밀 세그멘테이션
4. **COCO 호환 형식** — 업계 표준 어노테이션 형식으로 다운스트림 ML 파이프라인과의 호환성 보장
5. **품질 게이트** — Point Cloud QC가 파이프라인 초기에 품질 기준 미달 데이터를 필터링
6. **폴링 (이벤트 기반 아님)** — S3 AP는 이벤트 알림을 지원하지 않으므로 주기적 스케줄 실행 사용

---

## 사용 AWS 서비스

| 서비스 | 역할 |
|--------|------|
| FSx for NetApp ONTAP | 자율주행 데이터 스토리지 (영상 및 LiDAR) |
| S3 Access Points | ONTAP 볼륨에 대한 서버리스 접근 |
| EventBridge Scheduler | 주기적 트리거 |
| Step Functions | 워크플로 오케스트레이션 |
| Lambda | 컴퓨팅 (Discovery, Frame Extraction, Point Cloud QC, Annotation Manager, SageMaker Invoke) |
| Amazon Rekognition | 객체 탐지 (차량, 보행자, 교통 표지판) |
| Amazon SageMaker | Batch Transform (포인트 클라우드 세그멘테이션 추론) |
| Amazon Bedrock | 어노테이션 제안 생성 |
| SNS | 처리 완료 알림 |
| Secrets Manager | ONTAP REST API 자격 증명 관리 |
| CloudWatch + X-Ray | 관측 가능성 |
