"""共通イベント/レスポンス型定義

全 UC の Lambda 関数で使用する入出力の型定義。
IDE 補完と型チェックを有効にするための TypedDict 定義。

Usage:
    from shared.schemas.events import DiscoveryOutput, ProcessingInput, ReportInput

    def handler(event: dict, context) -> DiscoveryOutput:
        ...
"""

from __future__ import annotations

from typing import Literal, TypedDict


# ============================================================
# Discovery Lambda
# ============================================================


class DiscoveredObject(TypedDict):
    """Discovery Lambda が検出した個別オブジェクト"""

    Key: str
    Size: int
    LastModified: str
    ETag: str


class DiscoveryOutput(TypedDict):
    """Discovery Lambda の出力"""

    status: Literal["completed", "error"]
    object_count: int
    objects: list[DiscoveredObject]
    prefix: str
    timestamp: int


class DiscoveryError(TypedDict):
    """Discovery Lambda のエラー出力"""

    status: Literal["error"]
    error: str
    object_count: int


# ============================================================
# Processing Lambda
# ============================================================


class ProcessingInput(TypedDict):
    """Processing Lambda の入力（Map state から渡される）"""

    Key: str
    Size: int
    LastModified: str
    ETag: str


class HumanReviewInfo(TypedDict):
    """Human Review 判定情報"""

    confidence_score: float
    requires_review: bool
    action: Literal["AUTO_APPROVE", "HUMAN_REVIEW", "REJECT"]
    reason: str


class ProcessingOutput(TypedDict, total=False):
    """Processing Lambda の出力"""

    key: str
    status: Literal["completed", "error", "skipped"]
    output_key: str
    content_type: str
    processing_time_ms: int
    human_review: HumanReviewInfo
    data_classification: str
    error: str


# ============================================================
# Report Lambda
# ============================================================


class ReportInput(TypedDict):
    """Report Lambda の入力"""

    discovery: DiscoveryOutput
    processing: list[ProcessingOutput]


class ReportSummary(TypedDict):
    """レポートサマリー"""

    total_files: int
    succeeded: int
    failed: int
    skipped: int
    success_rate_pct: float
    requires_human_review: int


class ReportOutput(TypedDict):
    """Report Lambda の出力"""

    status: Literal["completed", "error"]
    report_key: str
    summary: ReportSummary
    sns_message_id: str
    data_classification: str
    timestamp: int


# ============================================================
# Step Functions 全体出力
# ============================================================


class WorkflowOutput(TypedDict):
    """Step Functions ワークフロー全体の出力"""

    discovery: DiscoveryOutput
    processing: list[ProcessingOutput]
    report: ReportOutput


# ============================================================
# EventBridge Scheduler イベント
# ============================================================


class SchedulerEvent(TypedDict, total=False):
    """EventBridge Scheduler からの入力イベント"""

    source: str
    detail_type: str
    time: str
    resources: list[str]


# ============================================================
# FPolicy イベント (Phase 10+)
# ============================================================


class FPolicyEvent(TypedDict):
    """FPolicy イベント（SQS 経由）"""

    event_type: Literal["create", "write", "rename", "delete", "close"]
    protocol: Literal["nfsv3", "nfsv4", "cifs"]
    path: str
    volume_name: str
    svm_name: str
    client_ip: str
    timestamp: str
    user: str


# ============================================================
# Content Edge Delivery パターン固有
# ============================================================


class DeliveryPublishEntry(TypedDict, total=False):
    """publish 済み（または参照生成済み）エントリ"""

    key: str
    delivery_mode: str
    cdn_target: str
    origin_access_point: str
    target_bucket: str
    target_endpoint: str
    bytes: int
    note: str


class ApprovalProvenance(TypedDict):
    """配信承認の監査証跡（誰が/いつ公開配信を承認したか）"""

    source_key: str
    approver: str
    approval_id: str
    published_at: str
    execution_id: str


class DeliveryManifest(TypedDict, total=False):
    """配信マニフェスト（S3 AP に書き戻す JSON）"""

    execution_id: str
    timestamp: str
    delivery_mode: str
    cdn_target: str
    total_candidates: int
    total_targets: int
    published: list[DeliveryPublishEntry]
    skipped: list[dict]
    provenance: list[ApprovalProvenance]
    data_classification: str
    data_classification_label: str


class DeliveryPublishOutput(TypedDict):
    """Publish Lambda の出力"""

    manifest_key: str
    delivery_mode: str
    cdn_target: str
    published: list[DeliveryPublishEntry]
    total_objects: int
    data_classification: str


class DeliveryLogSummaryOutput(TypedDict):
    """Delivery Log Sync Lambda の出力"""

    summary_key: str
    record_count: int
    total_bytes: int
    data_classification: str


# ============================================================
# SAP/ERP パターン固有
# ============================================================


class SapDiscoveredFile(TypedDict):
    """SAP Discovery Lambda が検出したファイル"""

    key: str
    size: int
    last_modified: str
    category: Literal[
        "sap_idoc", "hulft_transfer", "edi_document", "batch_output", "sap_xml", "data_extract", "general_erp"
    ]


class SapProcessingOutput(TypedDict, total=False):
    """SAP Processing Lambda の出力"""

    key: str
    status: Literal["completed", "error"]
    category: str
    summary: str
    document_type: str
    key_fields: list[str]
    output_key: str
    error: str
    timestamp: int
