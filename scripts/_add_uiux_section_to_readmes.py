#!/usr/bin/env python3
"""Add UI/UX Screenshot section (17 UCs covering end-users/staff/personnel)
to non-Japanese README files.

Insertion point: before the "AWS Specification Constraints and Workarounds"
section (which already exists in all 7 language READMEs from earlier translation).
"""

from __future__ import annotations

import sys
from pathlib import Path


SECTIONS = {
    "en": {
        "heading": "## UI/UX Screenshots (End Users / Staff / Personnel Views)",
        "intro": """UI/UX screens that **end users, staff, and personnel actually see
during their daily work** are featured in each UC's README and demo-guide.
Technical views such as Step Functions workflow graphs are consolidated
in phase verification documents (`docs/verification-results-phase*.md`).

The same approach is applied across all industries, not just Public Sector
(UC15/16/17):

- **Operational staff / personnel view**: verifying outputs in the S3 Console,
  reading Bedrock reports, receiving SNS notifications, searching DynamoDB
  histories, etc.
- **Technical views excluded**: CloudFormation stack events, Lambda logs,
  Step Functions graphs (except those for workflow visualization) are
  kept in `verification-results-*.md`""",
        "table_header": "| UC | Industry | Screenshot Count | Main Content | Location |\n|----|----------|------------------|--------------|----------|",
        "rows": [
            "| UC1 | Legal & Compliance | 1 | Step Functions graph (workflow visualization for compliance auditors) | [`legal-compliance/docs/demo-guide.en.md`](legal-compliance/docs/demo-guide.en.md) |",
            "| UC2 | Financial IDP | 1 | Step Functions graph (workflow visualization for invoice processing staff) | [`financial-idp/docs/demo-guide.en.md`](financial-idp/docs/demo-guide.en.md) |",
            "| UC3 | Manufacturing Analytics | 1 | Step Functions graph (workflow visualization for quality control staff) | [`manufacturing-analytics/docs/demo-guide.en.md`](manufacturing-analytics/docs/demo-guide.en.md) |",
            "| UC4 | Media & VFX | Not yet captured | (rendering technician views, planned for capture) | [`media-vfx/docs/demo-guide.en.md`](media-vfx/docs/demo-guide.en.md) |",
            "| UC5 | Healthcare DICOM | 1 | Step Functions graph (workflow visualization for medical records managers) | [`healthcare-dicom/docs/demo-guide.en.md`](healthcare-dicom/docs/demo-guide.en.md) |",
            "| UC6 | Semiconductor EDA | 4 | FSx Volumes / S3 output bucket / Athena query results / Bedrock design review report | [`semiconductor-eda/docs/demo-guide.en.md`](semiconductor-eda/docs/demo-guide.en.md) |",
            "| UC7 | Genomics Pipeline | 1 | Step Functions graph (workflow visualization for researchers) | [`genomics-pipeline/docs/demo-guide.en.md`](genomics-pipeline/docs/demo-guide.en.md) |",
            "| UC8 | Energy & Seismic | 1 | Step Functions graph (workflow visualization for geological analysts) | [`energy-seismic/docs/demo-guide.en.md`](energy-seismic/docs/demo-guide.en.md) |",
            "| UC9 | Autonomous Driving | Not yet captured | (ADAS analyst views, planned for capture) | [`autonomous-driving/docs/demo-guide.en.md`](autonomous-driving/docs/demo-guide.en.md) |",
            "| UC10 | Construction BIM | 1 | Step Functions graph (workflow visualization for BIM managers / safety officers) | [`construction-bim/docs/demo-guide.en.md`](construction-bim/docs/demo-guide.en.md) |",
            "| UC11 | Retail Catalog | 2 | Product tagging results / S3 output bucket (for e-commerce operators) | [`retail-catalog/docs/demo-guide.en.md`](retail-catalog/docs/demo-guide.en.md) |",
            "| UC12 | Logistics OCR | 1 | Step Functions graph (workflow visualization for delivery operators) | [`logistics-ocr/docs/demo-guide.en.md`](logistics-ocr/docs/demo-guide.en.md) |",
            "| UC13 | Education & Research | 1 | Step Functions graph (workflow visualization for research administration staff) | [`education-research/docs/demo-guide.en.md`](education-research/docs/demo-guide.en.md) |",
            "| UC14 | Insurance | 2 | Claims report / S3 output bucket (for insurance adjusters) | [`insurance-claims/docs/demo-guide.en.md`](insurance-claims/docs/demo-guide.en.md) |",
            "| UC15 | Defense & Satellite Imagery (Public Sector) | 4 | S3 upload / output / SNS email / JSON artifacts (for satellite imagery analysts) | [`defense-satellite/README.md`](defense-satellite/README.md) |",
            "| UC16 | Government FOIA (Public Sector) | 5 | Upload / redacted preview / metadata / FOIA reminder email / DynamoDB retention history (for public records officers) | [`government-archives/README.md`](government-archives/README.md) |",
            "| UC17 | Smart City (Public Sector) | 5 | GIS upload / Bedrock report / risk map / land use distribution / time-series history (for urban planners) | [`smart-city-geospatial/README.md`](smart-city-geospatial/README.md) |",
        ],
        "common_note": """**Common screenshots** (cross-industry generic views, under `docs/screenshots/masked/common/`):
- `fsx-s3ap-detail.png` — FSxN S3 Access Point detail view (referenced by storage administrators regardless of industry)
- `s3ap-list.png` — S3 Access Points list (referenced by IT administrators regardless of industry)

**Phase-specific views** (`docs/screenshots/masked/phase{1..7}/`):
- Phase 1-6b: Infrastructure build / feature addition technical views (CloudFormation stacks, Lambda function lists, SageMaker Endpoints, etc.)
- Phase 7: Common FSx S3 Access Points views etc. for UC15/16/17

Image file specifications are managed under `docs/screenshots/masked/phase{N}/README.md`.
Masking target guide: [`docs/screenshots/MASK_GUIDE.md`](docs/screenshots/MASK_GUIDE.md).
Industry mapping table (8 languages): [`docs/screenshots/uc-industry-mapping.md`](docs/screenshots/uc-industry-mapping.md).
Addition workflow: [`docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md`](docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md).

> All documents are available in 8 languages (日本語・English・한국어・简体中文・繁體中文・Français・Deutsch・Español). Use the Language Switcher at the top of each document to switch languages.""",
    },
    "ko": {
        "heading": "## UI/UX 스크린샷 (엔드유저 / 직원 / 담당자 뷰)",
        "intro": """각 UC의 **엔드유저, 직원, 담당자가 일상 업무에서 실제로 보는 UI/UX 화면**을
각 UC의 README 및 demo-guide에 게재합니다. Step Functions 워크플로 그래프와 같은
기술자용 뷰는 각 phase의 검증 결과 문서(`docs/verification-results-phase*.md`)에
정리되어 있습니다.

Public Sector (UC15/16/17)뿐만 아니라 모든 업종의 UC에서 동일한 방침을 채택:

- **담당자 시점**: S3 콘솔에서 결과물 확인, Bedrock 리포트 열람, SNS 메일 수신,
  DynamoDB로 이력 검색 등의 일상 업무 화면
- **기술자 시점 제외**: CloudFormation 스택 이벤트, Lambda 로그, Step Functions
  그래프(워크플로 시각화 목적 제외)는 `verification-results-*.md` 쪽에 분리""",
        "table_header": "| UC | 업종 | 화면 수 | 주요 내용 | 위치 |\n|----|------|---------|----------|------|",
        "rows": [
            "| UC1 | 법무·컴플라이언스 | 1 | Step Functions 그래프 (감사 담당자용 워크플로 시각화) | [`legal-compliance/docs/demo-guide.ko.md`](legal-compliance/docs/demo-guide.ko.md) |",
            "| UC2 | 금융·IDP | 1 | Step Functions 그래프 (청구서 처리 담당자용 워크플로 시각화) | [`financial-idp/docs/demo-guide.ko.md`](financial-idp/docs/demo-guide.ko.md) |",
            "| UC3 | 제조·분석 | 1 | Step Functions 그래프 (품질관리 담당자용 워크플로 시각화) | [`manufacturing-analytics/docs/demo-guide.ko.md`](manufacturing-analytics/docs/demo-guide.ko.md) |",
            "| UC4 | 미디어·VFX | 미게재 | (렌더링 담당자용 화면, 향후 촬영 예정) | [`media-vfx/docs/demo-guide.ko.md`](media-vfx/docs/demo-guide.ko.md) |",
            "| UC5 | 의료·DICOM | 1 | Step Functions 그래프 (의료정보관리자용 워크플로 시각화) | [`healthcare-dicom/docs/demo-guide.ko.md`](healthcare-dicom/docs/demo-guide.ko.md) |",
            "| UC6 | 반도체·EDA | 4 | FSx Volumes / S3 출력 버킷 / Athena 쿼리 결과 / Bedrock 설계 리뷰 리포트 | [`semiconductor-eda/docs/demo-guide.ko.md`](semiconductor-eda/docs/demo-guide.ko.md) |",
            "| UC7 | 유전체학 파이프라인 | 1 | Step Functions 그래프 (연구자용 워크플로 시각화) | [`genomics-pipeline/docs/demo-guide.ko.md`](genomics-pipeline/docs/demo-guide.ko.md) |",
            "| UC8 | 에너지·지진 탐사 | 1 | Step Functions 그래프 (지질 해석 담당자용 워크플로 시각화) | [`energy-seismic/docs/demo-guide.ko.md`](energy-seismic/docs/demo-guide.ko.md) |",
            "| UC9 | 자율주행 | 미게재 | (ADAS 분석 담당자용 화면, 향후 촬영 예정) | [`autonomous-driving/docs/demo-guide.ko.md`](autonomous-driving/docs/demo-guide.ko.md) |",
            "| UC10 | 건설·BIM | 1 | Step Functions 그래프 (BIM 관리자 / 안전 담당자용 워크플로 시각화) | [`construction-bim/docs/demo-guide.ko.md`](construction-bim/docs/demo-guide.ko.md) |",
            "| UC11 | 소매·카탈로그 | 2 | 상품 태그 결과 / S3 출력 버킷 (EC 담당자용) | [`retail-catalog/docs/demo-guide.ko.md`](retail-catalog/docs/demo-guide.ko.md) |",
            "| UC12 | 물류·OCR | 1 | Step Functions 그래프 (배송 담당자용 워크플로 시각화) | [`logistics-ocr/docs/demo-guide.ko.md`](logistics-ocr/docs/demo-guide.ko.md) |",
            "| UC13 | 교육·연구 | 1 | Step Functions 그래프 (연구 사무 담당자용 워크플로 시각화) | [`education-research/docs/demo-guide.ko.md`](education-research/docs/demo-guide.ko.md) |",
            "| UC14 | 보험 | 2 | 청구 리포트 / S3 출력 버킷 (보험 조정 담당자용) | [`insurance-claims/docs/demo-guide.ko.md`](insurance-claims/docs/demo-guide.ko.md) |",
            "| UC15 | 방위·위성 이미지 (Public Sector) | 4 | S3 업로드 / 출력 / SNS 이메일 / JSON 결과물 (분석 담당자용) | [`defense-satellite/README.md`](defense-satellite/README.md) |",
            "| UC16 | 정부·FOIA (Public Sector) | 5 | 업로드 / 편집 프리뷰 / 메타데이터 / FOIA 알림 이메일 / DynamoDB 보존 이력 (공문서 담당자용) | [`government-archives/README.md`](government-archives/README.md) |",
            "| UC17 | 스마트시티 (Public Sector) | 5 | GIS 업로드 / Bedrock 리포트 / 리스크 맵 / 토지 이용 분포 / 시계열 이력 (도시 계획 담당자용) | [`smart-city-geospatial/README.md`](smart-city-geospatial/README.md) |",
        ],
        "common_note": """**공통 스크린샷** (업종 횡단 범용 화면, `docs/screenshots/masked/common/`):
- `fsx-s3ap-detail.png` — FSxN S3 Access Point 상세 뷰 (업종 무관하게 스토리지 관리자가 참조)
- `s3ap-list.png` — S3 Access Points 목록 (업종 무관하게 IT 관리자가 참조)

**Phase별 뷰** (`docs/screenshots/masked/phase{1..7}/`):
- Phase 1-6b: 인프라 구축 / 기능 추가 시 기술자용 화면
- Phase 7: UC15/16/17 공통 FSx S3 Access Points 뷰 등

산업 매핑 표 (8 언어): [`docs/screenshots/uc-industry-mapping.md`](docs/screenshots/uc-industry-mapping.md).
추가 워크플로: [`docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md`](docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md).

> 모든 문서는 8개 언어(일본어·English·한국어·간체 중국어·번체 중국어·Français·Deutsch·Español)로 제공됩니다.""",
    },
    "zh-CN": {
        "heading": "## UI/UX 截图 (最终用户 / 员工 / 负责人视图)",
        "intro": """每个 UC 的 **最终用户、员工、负责人在日常工作中实际看到的 UI/UX 界面**
在各 UC 的 README 和 demo-guide 中刊载。Step Functions 工作流图等技术人员视图
集中在各 phase 的验证结果文档 (`docs/verification-results-phase*.md`) 中。

不仅限于 Public Sector (UC15/16/17)，所有行业的 UC 采用相同方针:

- **担当人视角**: 在 S3 控制台确认输出物、阅读 Bedrock 报告、接收 SNS 邮件、
  在 DynamoDB 检索历史等日常业务界面
- **技术人员视角除外**: CloudFormation 堆栈事件、Lambda 日志、Step Functions 图
  (工作流可视化目的除外) 保留在 `verification-results-*.md` 中""",
        "table_header": "| UC | 行业 | 截图数 | 主要内容 | 位置 |\n|----|------|--------|---------|------|",
        "rows": [
            "| UC1 | 法务·合规 | 1 | Step Functions 图 (审计负责人工作流可视化) | [`legal-compliance/docs/demo-guide.zh-CN.md`](legal-compliance/docs/demo-guide.zh-CN.md) |",
            "| UC2 | 金融·IDP | 1 | Step Functions 图 (发票处理负责人工作流可视化) | [`financial-idp/docs/demo-guide.zh-CN.md`](financial-idp/docs/demo-guide.zh-CN.md) |",
            "| UC3 | 制造·分析 | 1 | Step Functions 图 (质量管理负责人工作流可视化) | [`manufacturing-analytics/docs/demo-guide.zh-CN.md`](manufacturing-analytics/docs/demo-guide.zh-CN.md) |",
            "| UC4 | 媒体·VFX | 未刊载 | (渲染负责人界面, 计划拍摄) | [`media-vfx/docs/demo-guide.zh-CN.md`](media-vfx/docs/demo-guide.zh-CN.md) |",
            "| UC5 | 医疗·DICOM | 1 | Step Functions 图 (医疗信息管理员工作流可视化) | [`healthcare-dicom/docs/demo-guide.zh-CN.md`](healthcare-dicom/docs/demo-guide.zh-CN.md) |",
            "| UC6 | 半导体·EDA | 4 | FSx Volumes / S3 输出桶 / Athena 查询结果 / Bedrock 设计审查报告 | [`semiconductor-eda/docs/demo-guide.zh-CN.md`](semiconductor-eda/docs/demo-guide.zh-CN.md) |",
            "| UC7 | 基因组学流水线 | 1 | Step Functions 图 (研究者工作流可视化) | [`genomics-pipeline/docs/demo-guide.zh-CN.md`](genomics-pipeline/docs/demo-guide.zh-CN.md) |",
            "| UC8 | 能源·地震勘探 | 1 | Step Functions 图 (地质解析负责人工作流可视化) | [`energy-seismic/docs/demo-guide.zh-CN.md`](energy-seismic/docs/demo-guide.zh-CN.md) |",
            "| UC9 | 自动驾驶 | 未刊载 | (ADAS 分析负责人界面, 计划拍摄) | [`autonomous-driving/docs/demo-guide.zh-CN.md`](autonomous-driving/docs/demo-guide.zh-CN.md) |",
            "| UC10 | 建筑·BIM | 1 | Step Functions 图 (BIM 管理员 / 安全负责人工作流可视化) | [`construction-bim/docs/demo-guide.zh-CN.md`](construction-bim/docs/demo-guide.zh-CN.md) |",
            "| UC11 | 零售·目录 | 2 | 产品标签结果 / S3 输出桶 (EC 负责人用) | [`retail-catalog/docs/demo-guide.zh-CN.md`](retail-catalog/docs/demo-guide.zh-CN.md) |",
            "| UC12 | 物流·OCR | 1 | Step Functions 图 (配送负责人工作流可视化) | [`logistics-ocr/docs/demo-guide.zh-CN.md`](logistics-ocr/docs/demo-guide.zh-CN.md) |",
            "| UC13 | 教育·研究 | 1 | Step Functions 图 (研究事务负责人工作流可视化) | [`education-research/docs/demo-guide.zh-CN.md`](education-research/docs/demo-guide.zh-CN.md) |",
            "| UC14 | 保险 | 2 | 理赔报告 / S3 输出桶 (保险理算员用) | [`insurance-claims/docs/demo-guide.zh-CN.md`](insurance-claims/docs/demo-guide.zh-CN.md) |",
            "| UC15 | 国防·卫星图像 (Public Sector) | 4 | S3 上传 / 输出 / SNS 邮件 / JSON 成果物 (分析负责人用) | [`defense-satellite/README.md`](defense-satellite/README.md) |",
            "| UC16 | 政府·FOIA (Public Sector) | 5 | 上传 / 编辑预览 / 元数据 / FOIA 提醒邮件 / DynamoDB 保留历史 (公文档负责人用) | [`government-archives/README.md`](government-archives/README.md) |",
            "| UC17 | 智慧城市 (Public Sector) | 5 | GIS 上传 / Bedrock 报告 / 风险地图 / 土地利用分布 / 时序历史 (城市规划负责人用) | [`smart-city-geospatial/README.md`](smart-city-geospatial/README.md) |",
        ],
        "common_note": """**通用截图** (跨行业通用视图, `docs/screenshots/masked/common/`):
- `fsx-s3ap-detail.png` — FSxN S3 Access Point 详情视图 (存储管理员参考)
- `s3ap-list.png` — S3 Access Points 列表 (IT 管理员参考)

**按 Phase 视图** (`docs/screenshots/masked/phase{1..7}/`):
- Phase 1-6b: 基础设施构建 / 功能添加时的技术人员视图
- Phase 7: UC15/16/17 公共 FSx S3 Access Points 视图等

行业映射表 (8 语言): [`docs/screenshots/uc-industry-mapping.md`](docs/screenshots/uc-industry-mapping.md).
添加工作流: [`docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md`](docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md).

> 所有文档均提供 8 种语言版本。""",
    },
    "zh-TW": {
        "heading": "## UI/UX 螢幕截圖 (最終使用者 / 員工 / 負責人檢視)",
        "intro": """每個 UC 的 **最終使用者、員工、負責人在日常工作中實際看到的 UI/UX 畫面**
在各 UC 的 README 和 demo-guide 中刊載。Step Functions 工作流程圖等技術人員
檢視集中在各 phase 的驗證結果文件 (`docs/verification-results-phase*.md`) 中。

不僅限於 Public Sector (UC15/16/17), 所有業種的 UC 採用相同方針:

- **擔當者視角**: 在 S3 控制台確認產物、閱讀 Bedrock 報告、接收 SNS 郵件、
  在 DynamoDB 檢索歷史等日常業務畫面
- **技術人員視角除外**: CloudFormation 堆疊事件、Lambda 日誌、Step Functions 圖
  (工作流程視覺化目的除外) 保留在 `verification-results-*.md` 中""",
        "table_header": "| UC | 業種 | 螢幕截圖數 | 主要內容 | 位置 |\n|----|------|-----------|---------|------|",
        "rows": [
            "| UC1 | 法務·合規 | 1 | Step Functions 圖 (稽核負責人工作流程視覺化) | [`legal-compliance/docs/demo-guide.zh-TW.md`](legal-compliance/docs/demo-guide.zh-TW.md) |",
            "| UC2 | 金融·IDP | 1 | Step Functions 圖 (發票處理負責人工作流程視覺化) | [`financial-idp/docs/demo-guide.zh-TW.md`](financial-idp/docs/demo-guide.zh-TW.md) |",
            "| UC3 | 製造·分析 | 1 | Step Functions 圖 (品質管理負責人工作流程視覺化) | [`manufacturing-analytics/docs/demo-guide.zh-TW.md`](manufacturing-analytics/docs/demo-guide.zh-TW.md) |",
            "| UC4 | 媒體·VFX | 未刊載 | (渲染負責人畫面, 計劃拍攝) | [`media-vfx/docs/demo-guide.zh-TW.md`](media-vfx/docs/demo-guide.zh-TW.md) |",
            "| UC5 | 醫療·DICOM | 1 | Step Functions 圖 (醫療資訊管理員工作流程視覺化) | [`healthcare-dicom/docs/demo-guide.zh-TW.md`](healthcare-dicom/docs/demo-guide.zh-TW.md) |",
            "| UC6 | 半導體·EDA | 4 | FSx Volumes / S3 輸出儲存貯體 / Athena 查詢結果 / Bedrock 設計審查報告 | [`semiconductor-eda/docs/demo-guide.zh-TW.md`](semiconductor-eda/docs/demo-guide.zh-TW.md) |",
            "| UC7 | 基因體學流水線 | 1 | Step Functions 圖 (研究者工作流程視覺化) | [`genomics-pipeline/docs/demo-guide.zh-TW.md`](genomics-pipeline/docs/demo-guide.zh-TW.md) |",
            "| UC8 | 能源·地震勘探 | 1 | Step Functions 圖 (地質解析負責人工作流程視覺化) | [`energy-seismic/docs/demo-guide.zh-TW.md`](energy-seismic/docs/demo-guide.zh-TW.md) |",
            "| UC9 | 自動駕駛 | 未刊載 | (ADAS 分析負責人畫面, 計劃拍攝) | [`autonomous-driving/docs/demo-guide.zh-TW.md`](autonomous-driving/docs/demo-guide.zh-TW.md) |",
            "| UC10 | 建築·BIM | 1 | Step Functions 圖 (BIM 管理員 / 安全負責人工作流程視覺化) | [`construction-bim/docs/demo-guide.zh-TW.md`](construction-bim/docs/demo-guide.zh-TW.md) |",
            "| UC11 | 零售·目錄 | 2 | 產品標籤結果 / S3 輸出儲存貯體 (EC 負責人用) | [`retail-catalog/docs/demo-guide.zh-TW.md`](retail-catalog/docs/demo-guide.zh-TW.md) |",
            "| UC12 | 物流·OCR | 1 | Step Functions 圖 (配送負責人工作流程視覺化) | [`logistics-ocr/docs/demo-guide.zh-TW.md`](logistics-ocr/docs/demo-guide.zh-TW.md) |",
            "| UC13 | 教育·研究 | 1 | Step Functions 圖 (研究事務負責人工作流程視覺化) | [`education-research/docs/demo-guide.zh-TW.md`](education-research/docs/demo-guide.zh-TW.md) |",
            "| UC14 | 保險 | 2 | 理賠報告 / S3 輸出儲存貯體 (保險理賠員用) | [`insurance-claims/docs/demo-guide.zh-TW.md`](insurance-claims/docs/demo-guide.zh-TW.md) |",
            "| UC15 | 國防·衛星圖像 (Public Sector) | 4 | S3 上傳 / 輸出 / SNS 郵件 / JSON 產物 (分析負責人用) | [`defense-satellite/README.md`](defense-satellite/README.md) |",
            "| UC16 | 政府·FOIA (Public Sector) | 5 | 上傳 / 編輯預覽 / 中繼資料 / FOIA 提醒郵件 / DynamoDB 保留歷史 (公文書負責人用) | [`government-archives/README.md`](government-archives/README.md) |",
            "| UC17 | 智慧城市 (Public Sector) | 5 | GIS 上傳 / Bedrock 報告 / 風險地圖 / 土地利用分布 / 時序歷史 (都市規劃負責人用) | [`smart-city-geospatial/README.md`](smart-city-geospatial/README.md) |",
        ],
        "common_note": """**通用螢幕截圖** (業種橫跨通用檢視, `docs/screenshots/masked/common/`):
- `fsx-s3ap-detail.png` — FSxN S3 Access Point 詳情檢視
- `s3ap-list.png` — S3 Access Points 清單

**依 Phase 檢視** (`docs/screenshots/masked/phase{1..7}/`):
- Phase 1-6b: 基礎設施建構 / 功能新增時的技術人員檢視
- Phase 7: UC15/16/17 共通 FSx S3 Access Points 檢視等

業種對映表 (8 語言): [`docs/screenshots/uc-industry-mapping.md`](docs/screenshots/uc-industry-mapping.md).
新增工作流程: [`docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md`](docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md).

> 所有文件均提供 8 種語言版本。""",
    },
    "fr": {
        "heading": "## Captures d'écran UI/UX (vues pour utilisateurs finaux / personnel / responsables)",
        "intro": """Les écrans UI/UX que **les utilisateurs finaux, le personnel et les
responsables voient réellement dans leur travail quotidien** sont présentés
dans le README et le demo-guide de chaque UC. Les vues techniques telles que
les graphiques de workflow Step Functions sont consolidées dans les
documents de vérification par phase (`docs/verification-results-phase*.md`).

La même approche est appliquée à tous les secteurs, pas seulement au
Secteur Public (UC15/16/17):

- **Vue personnel opérationnel**: vérification des sorties dans la console S3,
  lecture des rapports Bedrock, réception des notifications SNS, recherche
  dans l'historique DynamoDB, etc.
- **Vues techniques exclues**: événements de pile CloudFormation, logs Lambda,
  graphiques Step Functions (sauf pour la visualisation de workflow) sont
  conservés dans `verification-results-*.md`""",
        "table_header": "| UC | Secteur | Nombre de captures | Contenu principal | Emplacement |\n|----|---------|--------------------|-------------------|-------------|",
        "rows": [
            "| UC1 | Juridique & conformité | 1 | Graphique Step Functions (visualisation workflow pour auditeurs de conformité) | [`legal-compliance/docs/demo-guide.fr.md`](legal-compliance/docs/demo-guide.fr.md) |",
            "| UC2 | Financier IDP | 1 | Graphique Step Functions (visualisation workflow pour personnel de traitement des factures) | [`financial-idp/docs/demo-guide.fr.md`](financial-idp/docs/demo-guide.fr.md) |",
            "| UC3 | Fabrication & analytique | 1 | Graphique Step Functions (visualisation workflow pour personnel de contrôle qualité) | [`manufacturing-analytics/docs/demo-guide.fr.md`](manufacturing-analytics/docs/demo-guide.fr.md) |",
            "| UC4 | Médias & VFX | Non capturé | (vues techniciens de rendu, prévu pour capture) | [`media-vfx/docs/demo-guide.fr.md`](media-vfx/docs/demo-guide.fr.md) |",
            "| UC5 | Santé DICOM | 1 | Graphique Step Functions (visualisation workflow pour gestionnaires de dossiers médicaux) | [`healthcare-dicom/docs/demo-guide.fr.md`](healthcare-dicom/docs/demo-guide.fr.md) |",
            "| UC6 | Semi-conducteurs EDA | 4 | FSx Volumes / bucket de sortie S3 / résultats de requête Athena / rapport de revue de conception Bedrock | [`semiconductor-eda/docs/demo-guide.fr.md`](semiconductor-eda/docs/demo-guide.fr.md) |",
            "| UC7 | Pipeline génomique | 1 | Graphique Step Functions (visualisation workflow pour chercheurs) | [`genomics-pipeline/docs/demo-guide.fr.md`](genomics-pipeline/docs/demo-guide.fr.md) |",
            "| UC8 | Énergie & sismique | 1 | Graphique Step Functions (visualisation workflow pour analystes géologiques) | [`energy-seismic/docs/demo-guide.fr.md`](energy-seismic/docs/demo-guide.fr.md) |",
            "| UC9 | Conduite autonome | Non capturé | (vues analystes ADAS, prévu pour capture) | [`autonomous-driving/docs/demo-guide.fr.md`](autonomous-driving/docs/demo-guide.fr.md) |",
            "| UC10 | Construction BIM | 1 | Graphique Step Functions (visualisation workflow pour gestionnaires BIM / responsables sécurité) | [`construction-bim/docs/demo-guide.fr.md`](construction-bim/docs/demo-guide.fr.md) |",
            "| UC11 | Catalogue commerce | 2 | Résultats d'étiquetage de produit / bucket de sortie S3 (pour opérateurs e-commerce) | [`retail-catalog/docs/demo-guide.fr.md`](retail-catalog/docs/demo-guide.fr.md) |",
            "| UC12 | Logistique OCR | 1 | Graphique Step Functions (visualisation workflow pour opérateurs de livraison) | [`logistics-ocr/docs/demo-guide.fr.md`](logistics-ocr/docs/demo-guide.fr.md) |",
            "| UC13 | Éducation & recherche | 1 | Graphique Step Functions (visualisation workflow pour personnel administratif de recherche) | [`education-research/docs/demo-guide.fr.md`](education-research/docs/demo-guide.fr.md) |",
            "| UC14 | Assurance | 2 | Rapport de sinistre / bucket de sortie S3 (pour experts en sinistres) | [`insurance-claims/docs/demo-guide.fr.md`](insurance-claims/docs/demo-guide.fr.md) |",
            "| UC15 | Défense & imagerie satellite (Public Sector) | 4 | Upload S3 / sortie / email SNS / artefacts JSON (pour analystes d'imagerie satellite) | [`defense-satellite/README.md`](defense-satellite/README.md) |",
            "| UC16 | Gouvernement FOIA (Public Sector) | 5 | Upload / prévisualisation caviardée / métadonnées / email de rappel FOIA / historique de rétention DynamoDB (pour responsables des archives publiques) | [`government-archives/README.md`](government-archives/README.md) |",
            "| UC17 | Smart City (Public Sector) | 5 | Upload GIS / rapport Bedrock / carte des risques / distribution d'utilisation du sol / historique temporel (pour urbanistes) | [`smart-city-geospatial/README.md`](smart-city-geospatial/README.md) |",
        ],
        "common_note": """**Captures d'écran communes** (vues génériques intersectorielles, dans `docs/screenshots/masked/common/`):
- `fsx-s3ap-detail.png` — vue détail du S3 Access Point FSxN
- `s3ap-list.png` — liste des S3 Access Points

**Vues par phase** (`docs/screenshots/masked/phase{1..7}/`):
- Phase 1-6b: vues techniques pour construction infrastructure / ajout fonctionnalités
- Phase 7: vues communes FSx S3 Access Points pour UC15/16/17

Table de mappage sectoriel (8 langues): [`docs/screenshots/uc-industry-mapping.md`](docs/screenshots/uc-industry-mapping.md).
Workflow d'ajout: [`docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md`](docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md).

> Tous les documents sont disponibles en 8 langues.""",
    },
    "de": {
        "heading": "## UI/UX-Screenshots (Endnutzer / Mitarbeiter / Zuständige-Ansichten)",
        "intro": """UI/UX-Bildschirme, die **Endnutzer, Mitarbeiter und Zuständige tatsächlich
in ihrer täglichen Arbeit sehen**, werden im README und Demo-Guide jedes
UC präsentiert. Technische Ansichten wie Step Functions-Workflow-Grafiken
sind in phasenspezifischen Verifizierungsdokumenten (`docs/verification-results-phase*.md`)
zusammengefasst.

Derselbe Ansatz wird für alle Branchen angewendet, nicht nur für den
öffentlichen Sektor (UC15/16/17):

- **Betriebs-Mitarbeiter-Sicht**: Überprüfung von Ausgaben in der S3-Konsole,
  Lesen von Bedrock-Berichten, Empfangen von SNS-Benachrichtigungen,
  Durchsuchen von DynamoDB-Historien usw.
- **Technische Ansichten ausgeschlossen**: CloudFormation-Stack-Events,
  Lambda-Logs, Step Functions-Grafiken (außer für Workflow-Visualisierung)
  sind in `verification-results-*.md` aufbewahrt""",
        "table_header": "| UC | Branche | Anzahl Screenshots | Hauptinhalt | Speicherort |\n|----|---------|--------------------|-------------|-------------|",
        "rows": [
            "| UC1 | Recht & Compliance | 1 | Step Functions-Grafik (Workflow-Visualisierung für Compliance-Auditoren) | [`legal-compliance/docs/demo-guide.de.md`](legal-compliance/docs/demo-guide.de.md) |",
            "| UC2 | Finanz-IDP | 1 | Step Functions-Grafik (Workflow-Visualisierung für Rechnungsbearbeitungsmitarbeiter) | [`financial-idp/docs/demo-guide.de.md`](financial-idp/docs/demo-guide.de.md) |",
            "| UC3 | Fertigung & Analytik | 1 | Step Functions-Grafik (Workflow-Visualisierung für Qualitätskontrollmitarbeiter) | [`manufacturing-analytics/docs/demo-guide.de.md`](manufacturing-analytics/docs/demo-guide.de.md) |",
            "| UC4 | Medien & VFX | Noch nicht erfasst | (Ansichten für Rendering-Techniker, Erfassung geplant) | [`media-vfx/docs/demo-guide.de.md`](media-vfx/docs/demo-guide.de.md) |",
            "| UC5 | Healthcare DICOM | 1 | Step Functions-Grafik (Workflow-Visualisierung für medizinische Aktenmanager) | [`healthcare-dicom/docs/demo-guide.de.md`](healthcare-dicom/docs/demo-guide.de.md) |",
            "| UC6 | Halbleiter EDA | 4 | FSx Volumes / S3-Ausgabe-Bucket / Athena-Query-Ergebnisse / Bedrock-Designüberprüfungsbericht | [`semiconductor-eda/docs/demo-guide.de.md`](semiconductor-eda/docs/demo-guide.de.md) |",
            "| UC7 | Genomik-Pipeline | 1 | Step Functions-Grafik (Workflow-Visualisierung für Forscher) | [`genomics-pipeline/docs/demo-guide.de.md`](genomics-pipeline/docs/demo-guide.de.md) |",
            "| UC8 | Energie & Seismik | 1 | Step Functions-Grafik (Workflow-Visualisierung für geologische Analysten) | [`energy-seismic/docs/demo-guide.de.md`](energy-seismic/docs/demo-guide.de.md) |",
            "| UC9 | Autonomes Fahren | Noch nicht erfasst | (ADAS-Analysten-Ansichten, Erfassung geplant) | [`autonomous-driving/docs/demo-guide.de.md`](autonomous-driving/docs/demo-guide.de.md) |",
            "| UC10 | Bau BIM | 1 | Step Functions-Grafik (Workflow-Visualisierung für BIM-Manager / Sicherheitsbeauftragte) | [`construction-bim/docs/demo-guide.de.md`](construction-bim/docs/demo-guide.de.md) |",
            "| UC11 | Einzelhandel Katalog | 2 | Produkt-Tagging-Ergebnisse / S3-Ausgabe-Bucket (für E-Commerce-Betreiber) | [`retail-catalog/docs/demo-guide.de.md`](retail-catalog/docs/demo-guide.de.md) |",
            "| UC12 | Logistik OCR | 1 | Step Functions-Grafik (Workflow-Visualisierung für Lieferbetreiber) | [`logistics-ocr/docs/demo-guide.de.md`](logistics-ocr/docs/demo-guide.de.md) |",
            "| UC13 | Bildung & Forschung | 1 | Step Functions-Grafik (Workflow-Visualisierung für Forschungsverwaltungsmitarbeiter) | [`education-research/docs/demo-guide.de.md`](education-research/docs/demo-guide.de.md) |",
            "| UC14 | Versicherung | 2 | Schadensbericht / S3-Ausgabe-Bucket (für Versicherungsgutachter) | [`insurance-claims/docs/demo-guide.de.md`](insurance-claims/docs/demo-guide.de.md) |",
            "| UC15 | Verteidigung & Satellitenbilder (Public Sector) | 4 | S3-Upload / Ausgabe / SNS-E-Mail / JSON-Artefakte (für Satellitenbilder-Analysten) | [`defense-satellite/README.md`](defense-satellite/README.md) |",
            "| UC16 | Regierung FOIA (Public Sector) | 5 | Upload / redaktierte Vorschau / Metadaten / FOIA-Erinnerungs-E-Mail / DynamoDB-Aufbewahrungshistorie (für öffentliche Aktenverantwortliche) | [`government-archives/README.md`](government-archives/README.md) |",
            "| UC17 | Smart City (Public Sector) | 5 | GIS-Upload / Bedrock-Bericht / Risikokarte / Landnutzungsverteilung / Zeitreihenhistorie (für Stadtplaner) | [`smart-city-geospatial/README.md`](smart-city-geospatial/README.md) |",
        ],
        "common_note": """**Gemeinsame Screenshots** (branchenübergreifende generische Ansichten in `docs/screenshots/masked/common/`):
- `fsx-s3ap-detail.png` — FSxN S3 Access Point Detailansicht
- `s3ap-list.png` — S3 Access Points Liste

**Phase-spezifische Ansichten** (`docs/screenshots/masked/phase{1..7}/`):
- Phase 1-6b: technische Ansichten für Infrastrukturaufbau / Funktionserweiterung
- Phase 7: gemeinsame FSx S3 Access Points-Ansichten für UC15/16/17

Branchen-Mapping-Tabelle (8 Sprachen): [`docs/screenshots/uc-industry-mapping.md`](docs/screenshots/uc-industry-mapping.md).
Hinzufügungs-Workflow: [`docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md`](docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md).

> Alle Dokumente sind in 8 Sprachen verfügbar.""",
    },
    "es": {
        "heading": "## Capturas de pantalla UI/UX (vistas para usuarios finales / personal / responsables)",
        "intro": """Las pantallas UI/UX que **los usuarios finales, el personal y los
responsables realmente ven en su trabajo diario** se presentan en el README
y demo-guide de cada UC. Las vistas técnicas como los gráficos de flujo de
trabajo de Step Functions se consolidan en documentos de verificación por
fase (`docs/verification-results-phase*.md`).

Se aplica el mismo enfoque a todas las industrias, no solo al Sector
Público (UC15/16/17):

- **Vista de personal operativo**: verificación de salidas en la consola S3,
  lectura de informes Bedrock, recepción de notificaciones SNS, búsqueda
  en historiales DynamoDB, etc.
- **Vistas técnicas excluidas**: eventos de pila CloudFormation, logs Lambda,
  gráficos Step Functions (excepto para visualización de flujo de trabajo)
  se mantienen en `verification-results-*.md`""",
        "table_header": "| UC | Sector | Número de capturas | Contenido principal | Ubicación |\n|----|--------|--------------------|---------------------|-----------|",
        "rows": [
            "| UC1 | Legal y cumplimiento | 1 | Gráfico Step Functions (visualización de flujo para auditores de cumplimiento) | [`legal-compliance/docs/demo-guide.es.md`](legal-compliance/docs/demo-guide.es.md) |",
            "| UC2 | Financiero IDP | 1 | Gráfico Step Functions (visualización de flujo para personal de procesamiento de facturas) | [`financial-idp/docs/demo-guide.es.md`](financial-idp/docs/demo-guide.es.md) |",
            "| UC3 | Fabricación y análisis | 1 | Gráfico Step Functions (visualización de flujo para personal de control de calidad) | [`manufacturing-analytics/docs/demo-guide.es.md`](manufacturing-analytics/docs/demo-guide.es.md) |",
            "| UC4 | Medios y VFX | No capturado | (vistas de técnicos de renderizado, planificado para captura) | [`media-vfx/docs/demo-guide.es.md`](media-vfx/docs/demo-guide.es.md) |",
            "| UC5 | Sanidad DICOM | 1 | Gráfico Step Functions (visualización de flujo para gestores de historiales médicos) | [`healthcare-dicom/docs/demo-guide.es.md`](healthcare-dicom/docs/demo-guide.es.md) |",
            "| UC6 | Semiconductores EDA | 4 | FSx Volumes / bucket de salida S3 / resultados de consulta Athena / informe de revisión de diseño Bedrock | [`semiconductor-eda/docs/demo-guide.es.md`](semiconductor-eda/docs/demo-guide.es.md) |",
            "| UC7 | Pipeline genómica | 1 | Gráfico Step Functions (visualización de flujo para investigadores) | [`genomics-pipeline/docs/demo-guide.es.md`](genomics-pipeline/docs/demo-guide.es.md) |",
            "| UC8 | Energía y sísmica | 1 | Gráfico Step Functions (visualización de flujo para analistas geológicos) | [`energy-seismic/docs/demo-guide.es.md`](energy-seismic/docs/demo-guide.es.md) |",
            "| UC9 | Conducción autónoma | No capturado | (vistas de analistas ADAS, planificado para captura) | [`autonomous-driving/docs/demo-guide.es.md`](autonomous-driving/docs/demo-guide.es.md) |",
            "| UC10 | Construcción BIM | 1 | Gráfico Step Functions (visualización de flujo para gestores BIM / responsables de seguridad) | [`construction-bim/docs/demo-guide.es.md`](construction-bim/docs/demo-guide.es.md) |",
            "| UC11 | Catálogo minorista | 2 | Resultados de etiquetado de productos / bucket de salida S3 (para operadores de e-commerce) | [`retail-catalog/docs/demo-guide.es.md`](retail-catalog/docs/demo-guide.es.md) |",
            "| UC12 | Logística OCR | 1 | Gráfico Step Functions (visualización de flujo para operadores de entrega) | [`logistics-ocr/docs/demo-guide.es.md`](logistics-ocr/docs/demo-guide.es.md) |",
            "| UC13 | Educación e investigación | 1 | Gráfico Step Functions (visualización de flujo para personal administrativo de investigación) | [`education-research/docs/demo-guide.es.md`](education-research/docs/demo-guide.es.md) |",
            "| UC14 | Seguros | 2 | Informe de reclamaciones / bucket de salida S3 (para ajustadores de seguros) | [`insurance-claims/docs/demo-guide.es.md`](insurance-claims/docs/demo-guide.es.md) |",
            "| UC15 | Defensa e imágenes satelitales (Public Sector) | 4 | Subida S3 / salida / email SNS / artefactos JSON (para analistas de imágenes satelitales) | [`defense-satellite/README.md`](defense-satellite/README.md) |",
            "| UC16 | Gobierno FOIA (Public Sector) | 5 | Subida / vista previa redactada / metadatos / email recordatorio FOIA / historial de retención DynamoDB (para responsables de archivos públicos) | [`government-archives/README.md`](government-archives/README.md) |",
            "| UC17 | Smart City (Public Sector) | 5 | Subida GIS / informe Bedrock / mapa de riesgos / distribución de uso del suelo / historial temporal (para urbanistas) | [`smart-city-geospatial/README.md`](smart-city-geospatial/README.md) |",
        ],
        "common_note": """**Capturas de pantalla comunes** (vistas genéricas intersectoriales, en `docs/screenshots/masked/common/`):
- `fsx-s3ap-detail.png` — vista de detalle del S3 Access Point FSxN
- `s3ap-list.png` — lista de S3 Access Points

**Vistas por fase** (`docs/screenshots/masked/phase{1..7}/`):
- Phase 1-6b: vistas técnicas para construcción de infraestructura / adición de características
- Phase 7: vistas comunes FSx S3 Access Points para UC15/16/17

Tabla de mapeo sectorial (8 idiomas): [`docs/screenshots/uc-industry-mapping.md`](docs/screenshots/uc-industry-mapping.md).
Flujo de adición: [`docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md`](docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md).

> Todos los documentos están disponibles en 8 idiomas.""",
    },
}


# Insertion point: immediately before the AWS Specification Constraints section
INSERT_BEFORE = {
    "en": "## AWS Specification Constraints and Workarounds",
    "ko": "## AWS 사양상의 제약 및 해결 방법",
    "zh-CN": "## AWS 规格约束及解决方案",
    "zh-TW": "## AWS 規格約束及解決方案",
    "fr": "## Contraintes de spécification AWS et solutions de contournement",
    "de": "## AWS-Spezifikationsbeschränkungen und Workarounds",
    "es": "## Restricciones de especificación de AWS y soluciones alternativas",
}


def build_section(lang_code: str) -> str:
    s = SECTIONS[lang_code]
    lines = [
        s["heading"],
        "",
        s["intro"],
        "",
        s["table_header"],
        *s["rows"],
        "",
        s["common_note"],
        "",
    ]
    return "\n".join(lines)


def patch(path: Path, lang_code: str) -> bool:
    text = path.read_text()
    s = SECTIONS[lang_code]

    # Check if already patched
    if s["heading"] in text:
        print(f"ALREADY PATCHED: {path}")
        return False

    marker = INSERT_BEFORE[lang_code]
    if marker not in text:
        print(f"MARKER NOT FOUND in {path}: '{marker}'")
        return False

    section = build_section(lang_code)
    new_text = text.replace(marker, section + marker, 1)
    path.write_text(new_text)
    print(f"PATCHED: {path} (inserted {len(section.splitlines())} lines)")
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
