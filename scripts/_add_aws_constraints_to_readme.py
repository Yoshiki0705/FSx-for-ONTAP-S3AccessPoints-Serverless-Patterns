#!/usr/bin/env python3
"""Insert 'AWS Specification Constraints and Workarounds' section into
non-Japanese README files, placing it between 'Use Case List' and
'Region Selection Guide' sections.

All translations target the same content as README.md (Japanese master).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Translations of the constraints section
TRANSLATIONS = {
    "en": {
        "title": "AWS Specification Constraints and Workarounds",
        "output_dest_title": "Output Destination Selection (OutputDestination Parameter)",
        "output_dest_body": """Each UC's CloudFormation template exposes an `OutputDestination` parameter
to choose where AI/ML artifacts are written (implemented in UC9/10/11/12/14;
other UCs are covered by Pattern A or Pattern C — see the Pattern table below):

- **`STANDARD_S3`** (default): Writes to a new S3 bucket (existing behavior)
- **`FSXN_S3AP`**: Writes back to the same FSx for NetApp ONTAP volume via the
  S3 Access Point (the **"no data movement" pattern**, enabling SMB/NFS users
  to view AI artifacts inside the existing directory structure)

```bash
# Deploy in FSXN_S3AP mode
aws cloudformation deploy \\
  --template-file retail-catalog/template-deploy.yaml \\
  --stack-name fsxn-retail-catalog-demo \\
  --parameter-overrides \\
    OutputDestination=FSXN_S3AP \\
    OutputS3APPrefix=ai-outputs/ \\
    ... (other required parameters)
```""",
        "constraints_title": "FSxN S3 Access Points AWS Specification Constraints",
        "constraints_intro": """FSxN S3 Access Points support only a subset of the S3 API (see
[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)).
The following constraints force some features to use standard S3 buckets:""",
        "constraints_table_header": "| AWS Specification Constraint | Impact | Project Workaround | Feature Request (FR) |\n|---|---|---|---|",
        "constraints_rows": [
            "| Athena query result location cannot specify S3AP<br>(Athena cannot write back to S3AP) | Athena results require standard S3 for UC6/7/8/13 | Each template creates a dedicated S3 bucket for Athena results | [FR-1](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-1) |",
            "| S3AP does not emit S3 Event Notifications / EventBridge events | Event-driven workflows are impossible | EventBridge Scheduler + Discovery Lambda polling pattern | [FR-2](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-2) |",
            "| S3AP does not support Object Lifecycle policies | 7-year retention (UC1 legal), permanent retention (UC16 archives), etc. cannot be automated | Custom Lambda sweeper for periodic deletion (not yet implemented, backlog) | [FR-3](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-3) |",
            "| S3AP does not support Object Versioning / Presigned URLs | Document version history, time-limited external sharing impossible | DynamoDB for version tracking, Presign via standard S3 copy | [FR-4](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-4) |",
            "| 5 GB upload size limit | Large binaries (4K video, uncompressed GeoTIFF) | `shared.s3ap_helper.multipart_upload()` supports up to 5 GB | (accepted AWS spec) |",
            "| SSE-FSX only (no SSE-KMS) | Cannot encrypt with custom KMS keys | Volume-level FSx KMS configuration encrypts at rest | (accepted AWS spec) |",
        ],
        "fr_summary": """Details and business impact of all 4 feature requests (FR-1 through FR-4)
are documented in [`docs/aws-feature-requests/fsxn-s3ap-improvements.md`](docs/aws-feature-requests/fsxn-s3ap-improvements.md).

The 3 output patterns (Pattern A/B/C) are compared in
[`docs/output-destination-patterns.md`](docs/output-destination-patterns.md).""",
        "per_uc_title": "Per-UC Output Destination Constraints",
        "per_uc_intro": """The 17 UCs fall into three output patterns:

- **🟢 UC1-5**: existing `S3AccessPointOutputAlias` parameter supports FSxN S3AP output (designed this way from day 1)
- **🟢🆕 UC9/10/11/12/14**: `OutputDestination` switch (STANDARD_S3 ⇄ FSXN_S3AP), implemented 2026-05-10. UC11/14 verified on AWS, UC9/10/12 unit-tested only
- **🟡 UC6/7/8/13**: currently `OUTPUT_BUCKET` only (standard S3 fixed). Athena results require standard S3 per AWS spec, so `OutputDestination` adoption is partial
- **🟢 UC15-17**: Pattern A (write back to FSxN S3AP, part of Phase 7)""",
        "per_uc_table_header": "| UC | Input | Output | Selection Mechanism | Notes |\n|----|------|------|----------|------|",
        "per_uc_rows": [
            "| UC1 legal-compliance | S3AP | S3AP (existing) | `S3AccessPointOutputAlias` parameter | Contract metadata / audit logs |",
            "| UC2 financial-idp | S3AP | S3AP (existing) | `S3AccessPointOutputAlias` | Invoice OCR results |",
            "| UC3 manufacturing-analytics | S3AP | S3AP (existing) | `S3AccessPointOutputAlias` | Inspection results / anomaly detection |",
            "| UC4 media-vfx | S3AP | S3AP (existing) | `S3AccessPointOutputAlias` | Render metadata |",
            "| UC5 healthcare-dicom | S3AP | S3AP (existing) | `S3AccessPointOutputAlias` | DICOM metadata / de-identification |",
            "| UC6 semiconductor-eda | S3AP | **Standard S3** | ⚠️ Not implemented | Bedrock/Athena results (Athena requires standard S3 per spec) |",
            "| UC7 genomics-pipeline | S3AP | **Standard S3** | ⚠️ Not implemented | Glue/Athena results (Athena requires standard S3 per spec) |",
            "| UC8 energy-seismic | S3AP | **Standard S3** | ⚠️ Not implemented | Glue/Athena results (Athena requires standard S3 per spec) |",
            "| UC9 autonomous-driving | S3AP | **Selectable** 🆕 | ✅ `OutputDestination` | ADAS analysis results |",
            "| UC10 construction-bim | S3AP | **Selectable** 🆕 | ✅ `OutputDestination` | BIM metadata / safety compliance reports |",
            "| **UC11 retail-catalog** | S3AP | **Selectable** | ✅ `OutputDestination` | AWS-verified 2026-05-10 |",
            "| UC12 logistics-ocr | S3AP | **Selectable** 🆕 | ✅ `OutputDestination` | Delivery waybill OCR |",
            "| UC13 education-research | S3AP | **Standard S3** | ⚠️ Not implemented | Includes Athena results (Athena requires standard S3 per spec) |",
            "| **UC14 insurance-claims** | S3AP | **Selectable** | ✅ `OutputDestination` | AWS-verified 2026-05-10 |",
            "| UC15 defense-satellite | S3AP | S3AP | existing pattern | Object detection / change detection |",
            "| UC16 government-archives | S3AP | S3AP | existing pattern | FOIA redaction / metadata |",
            "| UC17 smart-city-geospatial | S3AP | S3AP | existing pattern | GIS analysis / risk maps |",
        ],
        "roadmap_title": "**Roadmap**:",
        "roadmap_items": [
            "- ~~Part B: Documentation of existing `S3AccessPointOutputAlias` pattern in UC1-5~~ ✅ Complete (`docs/output-destination-patterns.md`)",
            "- UC6/7/8/13 Athena output must stay on standard S3 per spec, but non-Athena artifacts (e.g., Bedrock reports) could become `OutputDestination=FSXN_S3AP` selectable as a Pattern C → Pattern B hybrid (future enhancement)",
            "- UC9/10/12 AWS deployment verification (unit tests complete, deploy pending)",
        ],
    },
    "ko": {
        "title": "AWS 사양상의 제약 및 해결 방법",
        "output_dest_title": "출력 대상 선택 (OutputDestination 파라미터)",
        "output_dest_body": """각 UC의 CloudFormation 템플릿에는 `OutputDestination` 파라미터가 있어
AI/ML 아티팩트의 쓰기 대상을 선택할 수 있습니다 (UC9/10/11/12/14에서 구현됨,
다른 UC는 Pattern A 또는 Pattern C로 커버됨 - 아래의 Pattern 표 참조):

- **`STANDARD_S3`** (기본값): 새 S3 버킷에 쓰기 (기존 동작)
- **`FSXN_S3AP`**: S3 Access Point를 통해 동일한 FSx for NetApp ONTAP 볼륨에 다시 쓰기
  (**"no data movement" 패턴**, SMB/NFS 사용자가 기존 디렉토리 구조 내에서
  AI 아티팩트를 볼 수 있음)

```bash
# FSXN_S3AP 모드로 배포
aws cloudformation deploy \\
  --template-file retail-catalog/template-deploy.yaml \\
  --stack-name fsxn-retail-catalog-demo \\
  --parameter-overrides \\
    OutputDestination=FSXN_S3AP \\
    OutputS3APPrefix=ai-outputs/ \\
    ... (기타 필수 파라미터)
```""",
        "constraints_title": "FSxN S3 Access Points의 AWS 사양 제약",
        "constraints_intro": """FSxN S3 Access Points는 S3 API의 일부만 지원합니다
([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) 참조).
다음 제약 사항으로 인해 일부 기능은 표준 S3 버킷을 사용해야 합니다:""",
        "constraints_table_header": "| AWS 사양 제약 | 영향 | 프로젝트 해결 방법 | 기능 개선 요청 (FR) |\n|---|---|---|---|",
        "constraints_rows": [
            "| Athena 쿼리 결과 출력 위치에 S3AP 지정 불가<br>(Athena는 S3AP에 write back 불가) | UC6/7/8/13에서 Athena 결과는 표준 S3 필수 | 각 템플릿에서 Athena 결과 전용 S3 버킷 생성 | [FR-1](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-1) |",
            "| S3AP에서 S3 Event Notifications / EventBridge 이벤트 발행 불가 | 이벤트 기반 워크플로 구현 불가 | EventBridge Scheduler + Discovery Lambda 폴링 방식 | [FR-2](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-2) |",
            "| S3AP에서 Object Lifecycle 정책 미지원 | 7년 보관(UC1 법무), 영구 보관(UC16 정부 아카이브) 등의 자동화 곤란 | 정기 삭제 Lambda 스위퍼 (미구현, 백로그) | [FR-3](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-3) |",
            "| S3AP에서 Object Versioning / Presigned URL 미지원 | 문서 버전 관리, 외부 감사인을 위한 시간 제한 공유 불가 | DynamoDB로 버전 관리, 표준 S3 복사 + Presign | [FR-4](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-4) |",
            "| 5GB 업로드 상한 | 대형 바이너리(4K 비디오, 비압축 GeoTIFF 등) | `shared.s3ap_helper.multipart_upload()`으로 5GB 미만까지 지원 | (AWS 사양으로 수용) |",
            "| SSE-FSX만 지원 (SSE-KMS 불가) | 커스텀 KMS 키로 암호화 불가 | FSx 볼륨 자체의 KMS 설정으로 암호화 | (AWS 사양으로 수용) |",
        ],
        "fr_summary": """4가지 기능 개선 요청(FR-1~FR-4)의 자세한 내용과 비즈니스 영향은
[`docs/aws-feature-requests/fsxn-s3ap-improvements.md`](docs/aws-feature-requests/fsxn-s3ap-improvements.md)
에 정리되어 있습니다.

3가지 출력 패턴(Pattern A/B/C)의 자세한 비교는
[`docs/output-destination-patterns.md`](docs/output-destination-patterns.md)를 참조하세요.""",
        "per_uc_title": "UC별 출력 대상 제약",
        "per_uc_intro": """17개 UC는 3가지 출력 패턴으로 분류됩니다:

- **🟢 UC1-5**: 기존 `S3AccessPointOutputAlias` 파라미터로 FSxN S3AP 출력 지원 (처음부터 이렇게 설계됨)
- **🟢🆕 UC9/10/11/12/14**: `OutputDestination` 전환 메커니즘 (STANDARD_S3 ⇄ FSXN_S3AP), 2026-05-10 구현. UC11/14는 AWS 실증, UC9/10/12는 단위 테스트만 완료
- **🟡 UC6/7/8/13**: 현재는 `OUTPUT_BUCKET`만 (표준 S3 고정). Athena 결과는 AWS 사양상 표준 S3 필수이므로 `OutputDestination` 적용은 부분적
- **🟢 UC15-17**: Pattern A (FSxN S3AP로 write back, Phase 7의 일부)""",
        "per_uc_table_header": "| UC | 입력 | 출력 | 선택 메커니즘 | 비고 |\n|----|------|------|----------|------|",
        "per_uc_rows": [
            "| UC1 legal-compliance | S3AP | S3AP (기존) | `S3AccessPointOutputAlias` 파라미터 | 계약 메타데이터 / 감사 로그 |",
            "| UC2 financial-idp | S3AP | S3AP (기존) | `S3AccessPointOutputAlias` | 청구서 OCR 결과 |",
            "| UC3 manufacturing-analytics | S3AP | S3AP (기존) | `S3AccessPointOutputAlias` | 검사 결과 / 이상 감지 |",
            "| UC4 media-vfx | S3AP | S3AP (기존) | `S3AccessPointOutputAlias` | 렌더링 메타데이터 |",
            "| UC5 healthcare-dicom | S3AP | S3AP (기존) | `S3AccessPointOutputAlias` | DICOM 메타데이터 / 익명화 결과 |",
            "| UC6 semiconductor-eda | S3AP | **표준 S3** | ⚠️ 미구현 | Bedrock/Athena 결과 (Athena는 사양상 표준 S3 필수) |",
            "| UC7 genomics-pipeline | S3AP | **표준 S3** | ⚠️ 미구현 | Glue/Athena 결과 (Athena는 사양상 표준 S3 필수) |",
            "| UC8 energy-seismic | S3AP | **표준 S3** | ⚠️ 미구현 | Glue/Athena 결과 (Athena는 사양상 표준 S3 필수) |",
            "| UC9 autonomous-driving | S3AP | **선택 가능** 🆕 | ✅ `OutputDestination` | ADAS 분석 결과 |",
            "| UC10 construction-bim | S3AP | **선택 가능** 🆕 | ✅ `OutputDestination` | BIM 메타데이터 / 안전 컴플라이언스 보고서 |",
            "| **UC11 retail-catalog** | S3AP | **선택 가능** | ✅ `OutputDestination` | AWS 실증 완료 2026-05-10 |",
            "| UC12 logistics-ocr | S3AP | **선택 가능** 🆕 | ✅ `OutputDestination` | 배송 화물 OCR |",
            "| UC13 education-research | S3AP | **표준 S3** | ⚠️ 미구현 | Athena 결과 포함 (Athena는 사양상 표준 S3 필수) |",
            "| **UC14 insurance-claims** | S3AP | **선택 가능** | ✅ `OutputDestination` | AWS 실증 완료 2026-05-10 |",
            "| UC15 defense-satellite | S3AP | S3AP | 기존 패턴 | 객체 감지 / 변화 감지 결과 |",
            "| UC16 government-archives | S3AP | S3AP | 기존 패턴 | FOIA 편집 결과 / 메타데이터 |",
            "| UC17 smart-city-geospatial | S3AP | S3AP | 기존 패턴 | GIS 분석 결과 / 리스크 맵 |",
        ],
        "roadmap_title": "**로드맵**:",
        "roadmap_items": [
            "- ~~Part B: UC1-5의 기존 `S3AccessPointOutputAlias` 패턴 문서화~~ ✅ 완료 (`docs/output-destination-patterns.md`)",
            "- UC6/7/8/13의 Athena 출력은 사양상 표준 S3 필수이지만, Bedrock 보고서 등 비 Athena 아티팩트는 `OutputDestination=FSXN_S3AP`로 write back할 수 있는 선택지를 추가 가능 (Pattern C → Pattern B 하이브리드, 향후 확장)",
            "- UC9/10/12의 AWS 실제 배포 검증 (단위 테스트는 완료, 배포는 미실시)",
        ],
    },
    "zh-CN": {
        "title": "AWS 规格约束及解决方案",
        "output_dest_title": "输出目标选择 (OutputDestination 参数)",
        "output_dest_body": """每个 UC 的 CloudFormation 模板都包含 `OutputDestination` 参数来选择
AI/ML 工件的写入目标（已在 UC9/10/11/12/14 实现,
其他 UC 由 Pattern A 或 Pattern C 覆盖 - 参见下面的 Pattern 表):

- **`STANDARD_S3`** (默认): 写入新的 S3 存储桶 (现有行为)
- **`FSXN_S3AP`**: 通过 S3 Access Point 将结果写回同一个 FSx for NetApp ONTAP 卷
  (**"no data movement" 模式**, 使 SMB/NFS 用户能够在现有目录结构中
  查看 AI 工件)

```bash
# 以 FSXN_S3AP 模式部署
aws cloudformation deploy \\
  --template-file retail-catalog/template-deploy.yaml \\
  --stack-name fsxn-retail-catalog-demo \\
  --parameter-overrides \\
    OutputDestination=FSXN_S3AP \\
    OutputS3APPrefix=ai-outputs/ \\
    ... (其他必需参数)
```""",
        "constraints_title": "FSxN S3 Access Points 的 AWS 规格约束",
        "constraints_intro": """FSxN S3 Access Points 仅支持 S3 API 的一部分
(参见 [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html))。
由于以下约束,某些功能需要使用标准 S3 存储桶:""",
        "constraints_table_header": "| AWS 规格约束 | 影响 | 项目解决方案 | 功能改进请求 (FR) |\n|---|---|---|---|",
        "constraints_rows": [
            "| Athena 查询结果输出位置无法指定 S3AP<br>(Athena 无法 write back 到 S3AP) | UC6/7/8/13 的 Athena 结果需要标准 S3 | 每个模板创建专用于 Athena 结果的 S3 存储桶 | [FR-1](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-1) |",
            "| S3AP 不发出 S3 Event Notifications / EventBridge 事件 | 无法实现事件驱动的工作流 | EventBridge Scheduler + Discovery Lambda 轮询方式 | [FR-2](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-2) |",
            "| S3AP 不支持 Object Lifecycle 策略 | 7 年保留 (UC1 法务), 永久保留 (UC16 政府档案) 等自动化困难 | 定期删除的 Lambda 清理器 (未实现, 待办事项) | [FR-3](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-3) |",
            "| S3AP 不支持 Object Versioning / Presigned URL | 文档版本管理, 外部审计员的限时共享不可能 | DynamoDB 用于版本管理, 标准 S3 复制 + Presign | [FR-4](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-4) |",
            "| 5GB 上传大小限制 | 大型二进制文件 (4K 视频, 未压缩 GeoTIFF 等) | `shared.s3ap_helper.multipart_upload()` 支持到 5GB | (接受的 AWS 规格) |",
            "| 仅支持 SSE-FSX (不支持 SSE-KMS) | 无法使用自定义 KMS 密钥加密 | 通过 FSx 卷级别的 KMS 配置进行加密 | (接受的 AWS 规格) |",
        ],
        "fr_summary": """全部 4 个功能改进请求 (FR-1 ~ FR-4) 的详细内容和业务影响整理在
[`docs/aws-feature-requests/fsxn-s3ap-improvements.md`](docs/aws-feature-requests/fsxn-s3ap-improvements.md)
中。

3 种输出模式 (Pattern A/B/C) 的详细比较请参阅
[`docs/output-destination-patterns.md`](docs/output-destination-patterns.md)。""",
        "per_uc_title": "每个 UC 的输出目标约束",
        "per_uc_intro": """17 个 UC 分为 3 种输出模式:

- **🟢 UC1-5**: 现有的 `S3AccessPointOutputAlias` 参数支持 FSxN S3AP 输出 (从一开始就这样设计)
- **🟢🆕 UC9/10/11/12/14**: `OutputDestination` 切换机制 (STANDARD_S3 ⇄ FSXN_S3AP), 2026-05-10 实现。UC11/14 已在 AWS 上验证, UC9/10/12 仅完成单元测试
- **🟡 UC6/7/8/13**: 当前仅为 `OUTPUT_BUCKET` (固定为标准 S3)。Athena 结果在规格上需要标准 S3, 因此 `OutputDestination` 应用是部分性的
- **🟢 UC15-17**: Pattern A (write back 到 FSxN S3AP, Phase 7 的一部分)""",
        "per_uc_table_header": "| UC | 输入 | 输出 | 选择机制 | 备注 |\n|----|------|------|----------|------|",
        "per_uc_rows": [
            "| UC1 legal-compliance | S3AP | S3AP (现有) | `S3AccessPointOutputAlias` 参数 | 合同元数据 / 审计日志 |",
            "| UC2 financial-idp | S3AP | S3AP (现有) | `S3AccessPointOutputAlias` | 发票 OCR 结果 |",
            "| UC3 manufacturing-analytics | S3AP | S3AP (现有) | `S3AccessPointOutputAlias` | 检查结果 / 异常检测 |",
            "| UC4 media-vfx | S3AP | S3AP (现有) | `S3AccessPointOutputAlias` | 渲染元数据 |",
            "| UC5 healthcare-dicom | S3AP | S3AP (现有) | `S3AccessPointOutputAlias` | DICOM 元数据 / 匿名化结果 |",
            "| UC6 semiconductor-eda | S3AP | **标准 S3** | ⚠️ 未实现 | Bedrock/Athena 结果 (Athena 在规格上需要标准 S3) |",
            "| UC7 genomics-pipeline | S3AP | **标准 S3** | ⚠️ 未实现 | Glue/Athena 结果 (Athena 在规格上需要标准 S3) |",
            "| UC8 energy-seismic | S3AP | **标准 S3** | ⚠️ 未实现 | Glue/Athena 结果 (Athena 在规格上需要标准 S3) |",
            "| UC9 autonomous-driving | S3AP | **可选择** 🆕 | ✅ `OutputDestination` | ADAS 分析结果 |",
            "| UC10 construction-bim | S3AP | **可选择** 🆕 | ✅ `OutputDestination` | BIM 元数据 / 安全合规报告 |",
            "| **UC11 retail-catalog** | S3AP | **可选择** | ✅ `OutputDestination` | AWS 实证完成 2026-05-10 |",
            "| UC12 logistics-ocr | S3AP | **可选择** 🆕 | ✅ `OutputDestination` | 配送运单 OCR |",
            "| UC13 education-research | S3AP | **标准 S3** | ⚠️ 未实现 | 包括 Athena 结果 (Athena 在规格上需要标准 S3) |",
            "| **UC14 insurance-claims** | S3AP | **可选择** | ✅ `OutputDestination` | AWS 实证完成 2026-05-10 |",
            "| UC15 defense-satellite | S3AP | S3AP | 现有模式 | 对象检测 / 变化检测结果 |",
            "| UC16 government-archives | S3AP | S3AP | 现有模式 | FOIA 编辑结果 / 元数据 |",
            "| UC17 smart-city-geospatial | S3AP | S3AP | 现有模式 | GIS 分析结果 / 风险地图 |",
        ],
        "roadmap_title": "**路线图**:",
        "roadmap_items": [
            "- ~~Part B: UC1-5 现有 `S3AccessPointOutputAlias` 模式的文档整理~~ ✅ 完成 (`docs/output-destination-patterns.md`)",
            "- UC6/7/8/13 的 Athena 输出在规格上需要标准 S3, 但 Bedrock 报告等非 Athena 工件可以通过 `OutputDestination=FSXN_S3AP` write back 的选项 (Pattern C → Pattern B 混合, 未来扩展)",
            "- UC9/10/12 的 AWS 实际部署验证 (单元测试已完成, 部署未实施)",
        ],
    },
    "zh-TW": {
        "title": "AWS 規格約束及解決方案",
        "output_dest_title": "輸出目標選擇 (OutputDestination 參數)",
        "output_dest_body": """每個 UC 的 CloudFormation 範本都包含 `OutputDestination` 參數來選擇
AI/ML 產物的寫入目標 (已在 UC9/10/11/12/14 實作,
其他 UC 由 Pattern A 或 Pattern C 涵蓋 - 請參閱下面的 Pattern 表):

- **`STANDARD_S3`** (預設): 寫入新的 S3 儲存貯體 (現有行為)
- **`FSXN_S3AP`**: 透過 S3 Access Point 將結果寫回同一個 FSx for NetApp ONTAP 磁碟區
  (**"no data movement" 模式**, 使 SMB/NFS 使用者能夠在現有目錄結構中
  檢視 AI 產物)

```bash
# 以 FSXN_S3AP 模式部署
aws cloudformation deploy \\
  --template-file retail-catalog/template-deploy.yaml \\
  --stack-name fsxn-retail-catalog-demo \\
  --parameter-overrides \\
    OutputDestination=FSXN_S3AP \\
    OutputS3APPrefix=ai-outputs/ \\
    ... (其他必要參數)
```""",
        "constraints_title": "FSxN S3 Access Points 的 AWS 規格約束",
        "constraints_intro": """FSxN S3 Access Points 僅支援 S3 API 的一部分
(請參閱 [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html))。
由於下列約束, 某些功能需要使用標準 S3 儲存貯體:""",
        "constraints_table_header": "| AWS 規格約束 | 影響 | 專案解決方案 | 功能改進需求 (FR) |\n|---|---|---|---|",
        "constraints_rows": [
            "| Athena 查詢結果輸出位置無法指定 S3AP<br>(Athena 無法 write back 到 S3AP) | UC6/7/8/13 的 Athena 結果需要標準 S3 | 每個範本建立專用於 Athena 結果的 S3 儲存貯體 | [FR-1](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-1) |",
            "| S3AP 不發出 S3 Event Notifications / EventBridge 事件 | 無法實現事件驅動的工作流程 | EventBridge Scheduler + Discovery Lambda 輪詢方式 | [FR-2](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-2) |",
            "| S3AP 不支援 Object Lifecycle 政策 | 7 年保留 (UC1 法務), 永久保留 (UC16 政府檔案) 等自動化困難 | 定期刪除的 Lambda 清理器 (未實作, 待辦事項) | [FR-3](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-3) |",
            "| S3AP 不支援 Object Versioning / Presigned URL | 文件版本管理, 外部稽核員的限時共享無法實現 | DynamoDB 用於版本管理, 標準 S3 複製 + Presign | [FR-4](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-4) |",
            "| 5GB 上傳大小限制 | 大型二進位檔案 (4K 影片, 未壓縮 GeoTIFF 等) | `shared.s3ap_helper.multipart_upload()` 支援到 5GB | (接受的 AWS 規格) |",
            "| 僅支援 SSE-FSX (不支援 SSE-KMS) | 無法使用自訂 KMS 金鑰加密 | 透過 FSx 磁碟區層級的 KMS 設定進行加密 | (接受的 AWS 規格) |",
        ],
        "fr_summary": """所有 4 個功能改進需求 (FR-1 ~ FR-4) 的詳細內容與業務影響整理在
[`docs/aws-feature-requests/fsxn-s3ap-improvements.md`](docs/aws-feature-requests/fsxn-s3ap-improvements.md)
中。

3 種輸出模式 (Pattern A/B/C) 的詳細比較請參閱
[`docs/output-destination-patterns.md`](docs/output-destination-patterns.md)。""",
        "per_uc_title": "每個 UC 的輸出目標約束",
        "per_uc_intro": """17 個 UC 分為 3 種輸出模式:

- **🟢 UC1-5**: 現有的 `S3AccessPointOutputAlias` 參數支援 FSxN S3AP 輸出 (從一開始就這樣設計)
- **🟢🆕 UC9/10/11/12/14**: `OutputDestination` 切換機制 (STANDARD_S3 ⇄ FSXN_S3AP), 2026-05-10 實作。UC11/14 已在 AWS 上驗證, UC9/10/12 僅完成單元測試
- **🟡 UC6/7/8/13**: 目前僅為 `OUTPUT_BUCKET` (固定為標準 S3)。Athena 結果在規格上需要標準 S3, 因此 `OutputDestination` 應用是部分性的
- **🟢 UC15-17**: Pattern A (write back 到 FSxN S3AP, Phase 7 的一部分)""",
        "per_uc_table_header": "| UC | 輸入 | 輸出 | 選擇機制 | 備註 |\n|----|------|------|----------|------|",
        "per_uc_rows": [
            "| UC1 legal-compliance | S3AP | S3AP (現有) | `S3AccessPointOutputAlias` 參數 | 合約中繼資料 / 稽核日誌 |",
            "| UC2 financial-idp | S3AP | S3AP (現有) | `S3AccessPointOutputAlias` | 發票 OCR 結果 |",
            "| UC3 manufacturing-analytics | S3AP | S3AP (現有) | `S3AccessPointOutputAlias` | 檢查結果 / 異常偵測 |",
            "| UC4 media-vfx | S3AP | S3AP (現有) | `S3AccessPointOutputAlias` | 渲染中繼資料 |",
            "| UC5 healthcare-dicom | S3AP | S3AP (現有) | `S3AccessPointOutputAlias` | DICOM 中繼資料 / 匿名化結果 |",
            "| UC6 semiconductor-eda | S3AP | **標準 S3** | ⚠️ 未實作 | Bedrock/Athena 結果 (Athena 在規格上需要標準 S3) |",
            "| UC7 genomics-pipeline | S3AP | **標準 S3** | ⚠️ 未實作 | Glue/Athena 結果 (Athena 在規格上需要標準 S3) |",
            "| UC8 energy-seismic | S3AP | **標準 S3** | ⚠️ 未實作 | Glue/Athena 結果 (Athena 在規格上需要標準 S3) |",
            "| UC9 autonomous-driving | S3AP | **可選擇** 🆕 | ✅ `OutputDestination` | ADAS 分析結果 |",
            "| UC10 construction-bim | S3AP | **可選擇** 🆕 | ✅ `OutputDestination` | BIM 中繼資料 / 安全合規報告 |",
            "| **UC11 retail-catalog** | S3AP | **可選擇** | ✅ `OutputDestination` | AWS 實證完成 2026-05-10 |",
            "| UC12 logistics-ocr | S3AP | **可選擇** 🆕 | ✅ `OutputDestination` | 配送運單 OCR |",
            "| UC13 education-research | S3AP | **標準 S3** | ⚠️ 未實作 | 包含 Athena 結果 (Athena 在規格上需要標準 S3) |",
            "| **UC14 insurance-claims** | S3AP | **可選擇** | ✅ `OutputDestination` | AWS 實證完成 2026-05-10 |",
            "| UC15 defense-satellite | S3AP | S3AP | 現有模式 | 物件偵測 / 變化偵測結果 |",
            "| UC16 government-archives | S3AP | S3AP | 現有模式 | FOIA 編輯結果 / 中繼資料 |",
            "| UC17 smart-city-geospatial | S3AP | S3AP | 現有模式 | GIS 分析結果 / 風險地圖 |",
        ],
        "roadmap_title": "**藍圖**:",
        "roadmap_items": [
            "- ~~Part B: UC1-5 現有 `S3AccessPointOutputAlias` 模式的文件整理~~ ✅ 完成 (`docs/output-destination-patterns.md`)",
            "- UC6/7/8/13 的 Athena 輸出在規格上需要標準 S3, 但 Bedrock 報告等非 Athena 產物可以透過 `OutputDestination=FSXN_S3AP` write back 的選項 (Pattern C → Pattern B 混合, 未來擴充)",
            "- UC9/10/12 的 AWS 實際部署驗證 (單元測試已完成, 部署未實施)",
        ],
    },
    "fr": {
        "title": "Contraintes de spécification AWS et solutions de contournement",
        "output_dest_title": "Sélection de la destination de sortie (paramètre OutputDestination)",
        "output_dest_body": """Le template CloudFormation de chaque UC expose un paramètre `OutputDestination`
pour choisir où les artefacts IA/ML sont écrits (implémenté dans UC9/10/11/12/14 ;
les autres UC sont couverts par Pattern A ou Pattern C — voir le tableau des
Patterns ci-dessous) :

- **`STANDARD_S3`** (par défaut) : écriture dans un nouveau bucket S3 (comportement existant)
- **`FSXN_S3AP`** : réécriture sur le même volume FSx for NetApp ONTAP via le
  S3 Access Point (le **pattern "no data movement"**, permettant aux utilisateurs
  SMB/NFS de voir les artefacts IA dans la structure de répertoires existante)

```bash
# Déploiement en mode FSXN_S3AP
aws cloudformation deploy \\
  --template-file retail-catalog/template-deploy.yaml \\
  --stack-name fsxn-retail-catalog-demo \\
  --parameter-overrides \\
    OutputDestination=FSXN_S3AP \\
    OutputS3APPrefix=ai-outputs/ \\
    ... (autres paramètres requis)
```""",
        "constraints_title": "Contraintes de spécification AWS des FSxN S3 Access Points",
        "constraints_intro": """Les FSxN S3 Access Points ne prennent en charge qu'un sous-ensemble de l'API S3
(voir [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)).
Les contraintes suivantes obligent certaines fonctionnalités à utiliser des buckets S3 standard :""",
        "constraints_table_header": "| Contrainte de spécification AWS | Impact | Solution de contournement du projet | Demande d'amélioration (FR) |\n|---|---|---|---|",
        "constraints_rows": [
            "| Impossible de spécifier S3AP comme emplacement de résultat de requête Athena<br>(Athena ne peut pas write back vers S3AP) | Les résultats Athena nécessitent S3 standard pour UC6/7/8/13 | Chaque template crée un bucket S3 dédié pour les résultats Athena | [FR-1](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-1) |",
            "| S3AP n'émet pas de S3 Event Notifications / EventBridge events | Workflows événementiels impossibles | Pattern de polling EventBridge Scheduler + Discovery Lambda | [FR-2](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-2) |",
            "| S3AP ne prend pas en charge les politiques Object Lifecycle | Rétention 7 ans (UC1 juridique), rétention permanente (UC16 archives gouvernementales), etc. difficiles à automatiser | Sweeper Lambda personnalisé pour suppression périodique (non implémenté, backlog) | [FR-3](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-3) |",
            "| S3AP ne prend pas en charge Object Versioning / Presigned URLs | Gestion des versions de documents, partage limité dans le temps pour audits externes impossibles | DynamoDB pour gestion des versions, copie S3 standard + Presign | [FR-4](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-4) |",
            "| Limite de taille d'upload de 5 Go | Binaires volumineux (vidéo 4K, GeoTIFF non compressé, etc.) | `shared.s3ap_helper.multipart_upload()` prend en charge jusqu'à 5 Go | (spécification AWS acceptée) |",
            "| SSE-FSX uniquement (pas SSE-KMS) | Impossible de chiffrer avec clés KMS personnalisées | Chiffrement via configuration KMS au niveau du volume FSx | (spécification AWS acceptée) |",
        ],
        "fr_summary": """Les détails et l'impact métier des 4 demandes d'amélioration (FR-1 à FR-4)
sont documentés dans [`docs/aws-feature-requests/fsxn-s3ap-improvements.md`](docs/aws-feature-requests/fsxn-s3ap-improvements.md).

Les 3 patterns de sortie (Pattern A/B/C) sont comparés dans
[`docs/output-destination-patterns.md`](docs/output-destination-patterns.md).""",
        "per_uc_title": "Contraintes de destination de sortie par UC",
        "per_uc_intro": """Les 17 UC se répartissent en 3 patterns de sortie :

- **🟢 UC1-5** : le paramètre existant `S3AccessPointOutputAlias` prend en charge la sortie FSxN S3AP (conçu ainsi dès le début)
- **🟢🆕 UC9/10/11/12/14** : mécanisme de commutation `OutputDestination` (STANDARD_S3 ⇄ FSXN_S3AP), implémenté le 2026-05-10. UC11/14 vérifiés sur AWS, UC9/10/12 uniquement en tests unitaires
- **🟡 UC6/7/8/13** : actuellement `OUTPUT_BUCKET` uniquement (S3 standard fixe). Les résultats Athena nécessitent S3 standard par spécification, donc l'adoption de `OutputDestination` est partielle
- **🟢 UC15-17** : Pattern A (write back vers FSxN S3AP, partie de Phase 7)""",
        "per_uc_table_header": "| UC | Entrée | Sortie | Mécanisme de sélection | Notes |\n|----|------|------|----------|------|",
        "per_uc_rows": [
            "| UC1 legal-compliance | S3AP | S3AP (existant) | paramètre `S3AccessPointOutputAlias` | Métadonnées de contrat / journaux d'audit |",
            "| UC2 financial-idp | S3AP | S3AP (existant) | `S3AccessPointOutputAlias` | Résultats OCR de factures |",
            "| UC3 manufacturing-analytics | S3AP | S3AP (existant) | `S3AccessPointOutputAlias` | Résultats d'inspection / détection d'anomalies |",
            "| UC4 media-vfx | S3AP | S3AP (existant) | `S3AccessPointOutputAlias` | Métadonnées de rendu |",
            "| UC5 healthcare-dicom | S3AP | S3AP (existant) | `S3AccessPointOutputAlias` | Métadonnées DICOM / anonymisation |",
            "| UC6 semiconductor-eda | S3AP | **S3 standard** | ⚠️ Non implémenté | Résultats Bedrock/Athena (Athena nécessite S3 standard par spécification) |",
            "| UC7 genomics-pipeline | S3AP | **S3 standard** | ⚠️ Non implémenté | Résultats Glue/Athena (Athena nécessite S3 standard par spécification) |",
            "| UC8 energy-seismic | S3AP | **S3 standard** | ⚠️ Non implémenté | Résultats Glue/Athena (Athena nécessite S3 standard par spécification) |",
            "| UC9 autonomous-driving | S3AP | **Sélectionnable** 🆕 | ✅ `OutputDestination` | Résultats d'analyse ADAS |",
            "| UC10 construction-bim | S3AP | **Sélectionnable** 🆕 | ✅ `OutputDestination` | Métadonnées BIM / rapports de conformité sécurité |",
            "| **UC11 retail-catalog** | S3AP | **Sélectionnable** | ✅ `OutputDestination` | Vérifié sur AWS 2026-05-10 |",
            "| UC12 logistics-ocr | S3AP | **Sélectionnable** 🆕 | ✅ `OutputDestination` | OCR de bordereaux de livraison |",
            "| UC13 education-research | S3AP | **S3 standard** | ⚠️ Non implémenté | Inclut des résultats Athena (Athena nécessite S3 standard par spécification) |",
            "| **UC14 insurance-claims** | S3AP | **Sélectionnable** | ✅ `OutputDestination` | Vérifié sur AWS 2026-05-10 |",
            "| UC15 defense-satellite | S3AP | S3AP | pattern existant | Détection d'objets / détection de changement |",
            "| UC16 government-archives | S3AP | S3AP | pattern existant | Caviardage FOIA / métadonnées |",
            "| UC17 smart-city-geospatial | S3AP | S3AP | pattern existant | Analyses SIG / cartes de risque |",
        ],
        "roadmap_title": "**Feuille de route** :",
        "roadmap_items": [
            "- ~~Partie B : documentation du pattern `S3AccessPointOutputAlias` existant dans UC1-5~~ ✅ Terminé (`docs/output-destination-patterns.md`)",
            "- La sortie Athena de UC6/7/8/13 doit rester sur S3 standard par spécification, mais les artefacts non-Athena (ex. rapports Bedrock) pourraient devenir sélectionnables avec `OutputDestination=FSXN_S3AP` en hybride Pattern C → Pattern B (amélioration future)",
            "- Vérification de déploiement AWS pour UC9/10/12 (tests unitaires terminés, déploiement en attente)",
        ],
    },
    "de": {
        "title": "AWS-Spezifikationsbeschränkungen und Workarounds",
        "output_dest_title": "Auswahl des Ausgabeziels (OutputDestination-Parameter)",
        "output_dest_body": """Das CloudFormation-Template jedes UC stellt einen `OutputDestination`-Parameter
bereit, um auszuwählen, wohin AI/ML-Artefakte geschrieben werden (implementiert in
UC9/10/11/12/14; andere UCs sind durch Pattern A oder Pattern C abgedeckt — siehe
Pattern-Tabelle unten):

- **`STANDARD_S3`** (Standard): Schreibt in einen neuen S3-Bucket (bestehendes Verhalten)
- **`FSXN_S3AP`**: Schreibt zurück auf dasselbe FSx for NetApp ONTAP Volume über den
  S3 Access Point (das **"no data movement"-Pattern**, ermöglicht SMB/NFS-Benutzern,
  AI-Artefakte innerhalb der bestehenden Verzeichnisstruktur zu sehen)

```bash
# Deployment im FSXN_S3AP-Modus
aws cloudformation deploy \\
  --template-file retail-catalog/template-deploy.yaml \\
  --stack-name fsxn-retail-catalog-demo \\
  --parameter-overrides \\
    OutputDestination=FSXN_S3AP \\
    OutputS3APPrefix=ai-outputs/ \\
    ... (andere erforderliche Parameter)
```""",
        "constraints_title": "AWS-Spezifikationsbeschränkungen der FSxN S3 Access Points",
        "constraints_intro": """FSxN S3 Access Points unterstützen nur eine Teilmenge der S3-API
(siehe [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)).
Die folgenden Beschränkungen zwingen einige Funktionen, Standard-S3-Buckets zu verwenden:""",
        "constraints_table_header": "| AWS-Spezifikationsbeschränkung | Auswirkung | Projekt-Workaround | Feature Request (FR) |\n|---|---|---|---|",
        "constraints_rows": [
            "| Athena-Abfrageergebnis-Location kann kein S3AP angeben<br>(Athena kann nicht zu S3AP write back) | Athena-Ergebnisse erfordern Standard S3 für UC6/7/8/13 | Jedes Template erstellt einen dedizierten S3-Bucket für Athena-Ergebnisse | [FR-1](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-1) |",
            "| S3AP sendet keine S3 Event Notifications / EventBridge-Events | Ereignisgesteuerte Workflows unmöglich | EventBridge Scheduler + Discovery Lambda Polling-Pattern | [FR-2](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-2) |",
            "| S3AP unterstützt keine Object Lifecycle-Richtlinien | 7-Jahres-Aufbewahrung (UC1 juristisch), permanente Aufbewahrung (UC16 Regierungsarchive) usw. können nicht automatisiert werden | Benutzerdefinierter Lambda-Sweeper für periodische Löschung (nicht implementiert, Backlog) | [FR-3](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-3) |",
            "| S3AP unterstützt kein Object Versioning / Presigned URLs | Dokumenten-Versionshistorie, zeitbegrenztes externes Sharing unmöglich | DynamoDB für Versionstracking, Presign via Standard-S3-Kopie | [FR-4](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-4) |",
            "| 5-GB-Upload-Größenlimit | Große Binärdateien (4K-Video, unkomprimiertes GeoTIFF) | `shared.s3ap_helper.multipart_upload()` unterstützt bis zu 5 GB | (akzeptierte AWS-Spezifikation) |",
            "| Nur SSE-FSX (kein SSE-KMS) | Keine Verschlüsselung mit benutzerdefinierten KMS-Schlüsseln möglich | Volume-Level FSx KMS-Konfiguration verschlüsselt ruhende Daten | (akzeptierte AWS-Spezifikation) |",
        ],
        "fr_summary": """Details und geschäftliche Auswirkungen aller 4 Feature Requests (FR-1 bis FR-4)
sind in [`docs/aws-feature-requests/fsxn-s3ap-improvements.md`](docs/aws-feature-requests/fsxn-s3ap-improvements.md)
dokumentiert.

Die 3 Ausgabe-Patterns (Pattern A/B/C) werden in
[`docs/output-destination-patterns.md`](docs/output-destination-patterns.md) verglichen.""",
        "per_uc_title": "Ausgabeziel-Beschränkungen pro UC",
        "per_uc_intro": """Die 17 UCs teilen sich in 3 Ausgabe-Patterns auf:

- **🟢 UC1-5**: Bestehender `S3AccessPointOutputAlias`-Parameter unterstützt FSxN S3AP-Ausgabe (von Anfang an so konzipiert)
- **🟢🆕 UC9/10/11/12/14**: `OutputDestination`-Schaltmechanismus (STANDARD_S3 ⇄ FSXN_S3AP), implementiert am 2026-05-10. UC11/14 auf AWS verifiziert, UC9/10/12 nur Unit-Tests
- **🟡 UC6/7/8/13**: Derzeit nur `OUTPUT_BUCKET` (Standard-S3 fest). Athena-Ergebnisse erfordern Standard-S3 per Spezifikation, daher ist die `OutputDestination`-Übernahme teilweise
- **🟢 UC15-17**: Pattern A (write back zu FSxN S3AP, Teil von Phase 7)""",
        "per_uc_table_header": "| UC | Eingabe | Ausgabe | Auswahlmechanismus | Hinweise |\n|----|------|------|----------|------|",
        "per_uc_rows": [
            "| UC1 legal-compliance | S3AP | S3AP (bestehend) | `S3AccessPointOutputAlias`-Parameter | Vertragsmetadaten / Audit-Logs |",
            "| UC2 financial-idp | S3AP | S3AP (bestehend) | `S3AccessPointOutputAlias` | Rechnungs-OCR-Ergebnisse |",
            "| UC3 manufacturing-analytics | S3AP | S3AP (bestehend) | `S3AccessPointOutputAlias` | Inspektionsergebnisse / Anomalieerkennung |",
            "| UC4 media-vfx | S3AP | S3AP (bestehend) | `S3AccessPointOutputAlias` | Rendering-Metadaten |",
            "| UC5 healthcare-dicom | S3AP | S3AP (bestehend) | `S3AccessPointOutputAlias` | DICOM-Metadaten / Anonymisierung |",
            "| UC6 semiconductor-eda | S3AP | **Standard S3** | ⚠️ Nicht implementiert | Bedrock/Athena-Ergebnisse (Athena erfordert Standard-S3 per Spezifikation) |",
            "| UC7 genomics-pipeline | S3AP | **Standard S3** | ⚠️ Nicht implementiert | Glue/Athena-Ergebnisse (Athena erfordert Standard-S3 per Spezifikation) |",
            "| UC8 energy-seismic | S3AP | **Standard S3** | ⚠️ Nicht implementiert | Glue/Athena-Ergebnisse (Athena erfordert Standard-S3 per Spezifikation) |",
            "| UC9 autonomous-driving | S3AP | **Auswählbar** 🆕 | ✅ `OutputDestination` | ADAS-Analyseergebnisse |",
            "| UC10 construction-bim | S3AP | **Auswählbar** 🆕 | ✅ `OutputDestination` | BIM-Metadaten / Sicherheits-Compliance-Berichte |",
            "| **UC11 retail-catalog** | S3AP | **Auswählbar** | ✅ `OutputDestination` | AWS-verifiziert 2026-05-10 |",
            "| UC12 logistics-ocr | S3AP | **Auswählbar** 🆕 | ✅ `OutputDestination` | Lieferschein-OCR |",
            "| UC13 education-research | S3AP | **Standard S3** | ⚠️ Nicht implementiert | Enthält Athena-Ergebnisse (Athena erfordert Standard-S3 per Spezifikation) |",
            "| **UC14 insurance-claims** | S3AP | **Auswählbar** | ✅ `OutputDestination` | AWS-verifiziert 2026-05-10 |",
            "| UC15 defense-satellite | S3AP | S3AP | bestehendes Pattern | Objekterkennung / Änderungserkennung |",
            "| UC16 government-archives | S3AP | S3AP | bestehendes Pattern | FOIA-Schwärzung / Metadaten |",
            "| UC17 smart-city-geospatial | S3AP | S3AP | bestehendes Pattern | GIS-Analyse / Risikokarten |",
        ],
        "roadmap_title": "**Roadmap**:",
        "roadmap_items": [
            "- ~~Teil B: Dokumentation des bestehenden `S3AccessPointOutputAlias`-Patterns in UC1-5~~ ✅ Abgeschlossen (`docs/output-destination-patterns.md`)",
            "- Die Athena-Ausgabe von UC6/7/8/13 muss per Spezifikation auf Standard-S3 bleiben, aber Nicht-Athena-Artefakte (z. B. Bedrock-Berichte) könnten als Pattern C → Pattern B-Hybrid mit `OutputDestination=FSXN_S3AP` wählbar werden (zukünftige Erweiterung)",
            "- AWS-Deployment-Verifizierung für UC9/10/12 (Unit-Tests abgeschlossen, Deployment ausstehend)",
        ],
    },
    "es": {
        "title": "Restricciones de especificación de AWS y soluciones alternativas",
        "output_dest_title": "Selección de destino de salida (parámetro OutputDestination)",
        "output_dest_body": """La plantilla CloudFormation de cada UC expone un parámetro `OutputDestination`
para elegir dónde se escriben los artefactos de IA/ML (implementado en UC9/10/11/12/14;
otros UC están cubiertos por Pattern A o Pattern C — ver la tabla de Patterns abajo):

- **`STANDARD_S3`** (predeterminado): Escribe en un nuevo bucket S3 (comportamiento existente)
- **`FSXN_S3AP`**: Escribe de vuelta al mismo volumen FSx for NetApp ONTAP a través del
  S3 Access Point (el **patrón "no data movement"**, permite a usuarios SMB/NFS
  ver artefactos de IA dentro de la estructura de directorios existente)

```bash
# Despliegue en modo FSXN_S3AP
aws cloudformation deploy \\
  --template-file retail-catalog/template-deploy.yaml \\
  --stack-name fsxn-retail-catalog-demo \\
  --parameter-overrides \\
    OutputDestination=FSXN_S3AP \\
    OutputS3APPrefix=ai-outputs/ \\
    ... (otros parámetros requeridos)
```""",
        "constraints_title": "Restricciones de especificación de AWS de FSxN S3 Access Points",
        "constraints_intro": """FSxN S3 Access Points solo admiten un subconjunto de la API de S3
(ver [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)).
Las siguientes restricciones obligan a algunas funciones a usar buckets S3 estándar:""",
        "constraints_table_header": "| Restricción de especificación AWS | Impacto | Solución alternativa del proyecto | Solicitud de mejora (FR) |\n|---|---|---|---|",
        "constraints_rows": [
            "| No se puede especificar S3AP como ubicación de resultado de consulta Athena<br>(Athena no puede write back a S3AP) | Los resultados de Athena requieren S3 estándar para UC6/7/8/13 | Cada plantilla crea un bucket S3 dedicado para resultados de Athena | [FR-1](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-1) |",
            "| S3AP no emite S3 Event Notifications / eventos EventBridge | Flujos de trabajo basados en eventos imposibles | Patrón de polling EventBridge Scheduler + Discovery Lambda | [FR-2](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-2) |",
            "| S3AP no admite políticas Object Lifecycle | Retención de 7 años (UC1 legal), retención permanente (UC16 archivos), etc. difíciles de automatizar | Sweeper Lambda personalizado para eliminación periódica (no implementado, backlog) | [FR-3](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-3) |",
            "| S3AP no admite Object Versioning / Presigned URLs | Gestión de versiones de documentos, compartición limitada en tiempo para auditores externos imposibles | DynamoDB para gestión de versiones, copia S3 estándar + Presign | [FR-4](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-4) |",
            "| Límite de tamaño de carga de 5 GB | Binarios grandes (video 4K, GeoTIFF sin comprimir, etc.) | `shared.s3ap_helper.multipart_upload()` admite hasta 5 GB | (especificación AWS aceptada) |",
            "| Solo SSE-FSX (no SSE-KMS) | No se puede cifrar con claves KMS personalizadas | Cifrado mediante configuración KMS a nivel de volumen FSx | (especificación AWS aceptada) |",
        ],
        "fr_summary": """Los detalles e impacto empresarial de las 4 solicitudes de mejora (FR-1 a FR-4)
están documentados en [`docs/aws-feature-requests/fsxn-s3ap-improvements.md`](docs/aws-feature-requests/fsxn-s3ap-improvements.md).

Los 3 patrones de salida (Pattern A/B/C) se comparan en
[`docs/output-destination-patterns.md`](docs/output-destination-patterns.md).""",
        "per_uc_title": "Restricciones de destino de salida por UC",
        "per_uc_intro": """Los 17 UC se dividen en 3 patrones de salida:

- **🟢 UC1-5**: el parámetro existente `S3AccessPointOutputAlias` admite salida FSxN S3AP (diseñado así desde el principio)
- **🟢🆕 UC9/10/11/12/14**: mecanismo de conmutación `OutputDestination` (STANDARD_S3 ⇄ FSXN_S3AP), implementado el 2026-05-10. UC11/14 verificados en AWS, UC9/10/12 solo pruebas unitarias
- **🟡 UC6/7/8/13**: actualmente solo `OUTPUT_BUCKET` (S3 estándar fijo). Los resultados de Athena requieren S3 estándar por especificación, por lo que la adopción de `OutputDestination` es parcial
- **🟢 UC15-17**: Pattern A (write back a FSxN S3AP, parte de Phase 7)""",
        "per_uc_table_header": "| UC | Entrada | Salida | Mecanismo de selección | Notas |\n|----|------|------|----------|------|",
        "per_uc_rows": [
            "| UC1 legal-compliance | S3AP | S3AP (existente) | parámetro `S3AccessPointOutputAlias` | Metadatos de contratos / registros de auditoría |",
            "| UC2 financial-idp | S3AP | S3AP (existente) | `S3AccessPointOutputAlias` | Resultados OCR de facturas |",
            "| UC3 manufacturing-analytics | S3AP | S3AP (existente) | `S3AccessPointOutputAlias` | Resultados de inspección / detección de anomalías |",
            "| UC4 media-vfx | S3AP | S3AP (existente) | `S3AccessPointOutputAlias` | Metadatos de renderizado |",
            "| UC5 healthcare-dicom | S3AP | S3AP (existente) | `S3AccessPointOutputAlias` | Metadatos DICOM / anonimización |",
            "| UC6 semiconductor-eda | S3AP | **S3 estándar** | ⚠️ No implementado | Resultados Bedrock/Athena (Athena requiere S3 estándar por especificación) |",
            "| UC7 genomics-pipeline | S3AP | **S3 estándar** | ⚠️ No implementado | Resultados Glue/Athena (Athena requiere S3 estándar por especificación) |",
            "| UC8 energy-seismic | S3AP | **S3 estándar** | ⚠️ No implementado | Resultados Glue/Athena (Athena requiere S3 estándar por especificación) |",
            "| UC9 autonomous-driving | S3AP | **Seleccionable** 🆕 | ✅ `OutputDestination` | Resultados de análisis ADAS |",
            "| UC10 construction-bim | S3AP | **Seleccionable** 🆕 | ✅ `OutputDestination` | Metadatos BIM / informes de cumplimiento de seguridad |",
            "| **UC11 retail-catalog** | S3AP | **Seleccionable** | ✅ `OutputDestination` | Verificado en AWS 2026-05-10 |",
            "| UC12 logistics-ocr | S3AP | **Seleccionable** 🆕 | ✅ `OutputDestination` | OCR de guías de entrega |",
            "| UC13 education-research | S3AP | **S3 estándar** | ⚠️ No implementado | Incluye resultados Athena (Athena requiere S3 estándar por especificación) |",
            "| **UC14 insurance-claims** | S3AP | **Seleccionable** | ✅ `OutputDestination` | Verificado en AWS 2026-05-10 |",
            "| UC15 defense-satellite | S3AP | S3AP | patrón existente | Detección de objetos / detección de cambios |",
            "| UC16 government-archives | S3AP | S3AP | patrón existente | Redacción FOIA / metadatos |",
            "| UC17 smart-city-geospatial | S3AP | S3AP | patrón existente | Análisis SIG / mapas de riesgo |",
        ],
        "roadmap_title": "**Hoja de ruta**:",
        "roadmap_items": [
            "- ~~Parte B: documentación del patrón `S3AccessPointOutputAlias` existente en UC1-5~~ ✅ Completado (`docs/output-destination-patterns.md`)",
            "- La salida Athena de UC6/7/8/13 debe permanecer en S3 estándar por especificación, pero los artefactos no-Athena (ej. informes Bedrock) podrían volverse seleccionables con `OutputDestination=FSXN_S3AP` como híbrido Pattern C → Pattern B (mejora futura)",
            "- Verificación de despliegue AWS para UC9/10/12 (pruebas unitarias completadas, despliegue pendiente)",
        ],
    },
}


# Marker strings (header of the following section in each language)
# Format: "region_section_heading" -> the translated "Region Selection Guide" heading
INSERT_BEFORE_MARKERS = {
    "en": "## Region Selection Guide",
    "ko": "## 리전 선택 가이드",
    "zh-CN": "## 区域选择指南",
    "zh-TW": "## 區域選擇指南",
    "fr": "## Guide de sélection de région",
    "de": "## Leitfaden zur Regionsauswahl",
    "es": "## Guía de selección de región",
}


def build_section(lang_code: str) -> str:
    t = TRANSLATIONS[lang_code]
    lines = [
        f"## {t['title']}",
        "",
        f"### {t['output_dest_title']}",
        "",
        t["output_dest_body"],
        "",
        f"### {t['constraints_title']}",
        "",
        t["constraints_intro"],
        "",
        t["constraints_table_header"],
        *t["constraints_rows"],
        "",
        t["fr_summary"],
        "",
        f"### {t['per_uc_title']}",
        "",
        t["per_uc_intro"],
        "",
        t["per_uc_table_header"],
        *t["per_uc_rows"],
        "",
        t["roadmap_title"],
        *t["roadmap_items"],
        "",
    ]
    return "\n".join(lines)


def patch(path: Path, lang_code: str) -> bool:
    text = path.read_text()
    marker = INSERT_BEFORE_MARKERS[lang_code]
    t = TRANSLATIONS[lang_code]

    # Use the translated section title as the "already patched" marker
    # (unique enough since it includes the AWS / section-specific wording)
    if f"## {t['title']}" in text:
        print(f"ALREADY PATCHED: {path}")
        return False

    if marker not in text:
        print(f"MARKER NOT FOUND: {path} (looking for '{marker}')")
        return False

    section = build_section(lang_code)
    new_text = text.replace(marker, section + marker, 1)
    path.write_text(new_text)
    print(f"PATCHED: {path} (inserted {len(section.splitlines())} lines before '{marker}')")
    return True


def main() -> int:
    files = [
        ("README.en.md", "en"),
        ("README.ko.md", "ko"),
        ("README.zh-CN.md", "zh-CN"),
        ("README.zh-TW.md", "zh-TW"),
        ("README.fr.md", "fr"),
        ("README.de.md", "de"),
        ("README.es.md", "es"),
    ]
    modified = 0
    for filename, lang in files:
        path = Path(filename)
        if not path.exists():
            print(f"MISSING: {path}")
            continue
        if patch(path, lang):
            modified += 1
    print(f"\nTotal modified: {modified}/{len(files)}")
    return 0 if modified else 1


if __name__ == "__main__":
    sys.exit(main())
