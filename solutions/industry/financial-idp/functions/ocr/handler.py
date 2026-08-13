"""金融・保険 OCR Lambda ハンドラ

Map ステートからドキュメント情報を受け取り、S3 AP 経由でドキュメントを取得し、
Amazon Textract で OCR を実行する。

ページ数に基づき同期 API (AnalyzeDocument) と非同期 API
(StartDocumentAnalysis) を自動選択する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN
"""

from __future__ import annotations

import logging
import os
import time

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler, xray_subsegment
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


def select_textract_api(page_count: int, threshold: int = 1) -> str:
    """Textract API の同期/非同期を選択する

    ページ数が閾値以下の場合は同期 API (AnalyzeDocument) を使用し、
    閾値を超える場合は非同期 API (StartDocumentAnalysis) を使用する。

    Args:
        page_count: ドキュメントのページ数
        threshold: 同期 API を使用する最大ページ数 (デフォルト: 1)

    Returns:
        str: "sync" (AnalyzeDocument) または "async" (StartDocumentAnalysis)
    """
    if page_count <= threshold:
        return "sync"
    return "async"


def _extract_text_sync(textract_client, document_bytes: bytes) -> str:
    """同期 Textract API (AnalyzeDocument) でテキスト抽出

    Args:
        textract_client: boto3 Textract クライアント
        document_bytes: ドキュメントのバイトデータ

    Returns:
        str: 抽出されたテキスト
    """
    with xray_subsegment(
        name="textract_analyzedocument",
        annotations={"service_name": "textract", "operation": "AnalyzeDocument", "use_case": "financial-idp"},
    ):
        response = textract_client.analyze_document(
            Document={"Bytes": document_bytes},
            FeatureTypes=["TABLES", "FORMS"],
        )

    lines = []
    for block in response.get("Blocks", []):
        if block["BlockType"] == "LINE":
            lines.append(block.get("Text", ""))

    return "\n".join(lines)


class TextractJobTimeout(RuntimeError):
    """非同期 Textract ジョブが待機上限内に完了しなかった

    専用の型にしているのは、待機打ち切りとジョブ自体の失敗
    （`Textract job ... failed`）を呼び出し側とログで区別できるようにするため。
    どちらも同じ except 節に入るが、原因と次の手が違う。
    """


# 残り実行時間からこの秒数を引いた分だけ待つ。Lambda に殺される前に戻り、
# 構造化した結果（handler の except が組み立てる error 付きの dict）を返すための余裕。
# 途中で殺されると Step Functions には Lambda.Unknown だけが残り、どの
# ドキュメントで何が起きたか分からなくなる。
_TIMEOUT_RESERVE_SECONDS = 15.0

# 残り実行時間が取れない場合の上限。OcrFunction の Timeout は 600 秒なので、
# その内側に収まる値にしている。
_DEFAULT_MAX_WAIT_SECONDS = 540.0

_DEFAULT_POLL_INTERVAL_SECONDS = 5.0

# NextToken のページ送りの上限。Textract は必ず None を返して終わるが、
# 応答が壊れた場合や代替実装を挟んだ場合に無限ループにしないための歯止め。
_MAX_RESULT_PAGES = 1000


def async_wait_budget(remaining_millis: float | None) -> float:
    """非同期ジョブの待機に使える秒数を返す

    Args:
        remaining_millis: Lambda の残り実行時間（ミリ秒）。
            取得できない場合は None。

    Returns:
        float: 待機に使える秒数。負にはならない。
    """
    if remaining_millis is None:
        return _DEFAULT_MAX_WAIT_SECONDS
    return max(0.0, remaining_millis / 1000.0 - _TIMEOUT_RESERVE_SECONDS)


def _extract_text_async(
    textract_client,
    s3_bucket: str,
    s3_key: str,
    *,
    wait_budget_seconds: float | None = None,
    poll_interval_seconds: float | None = None,
    sleep=time.sleep,
    monotonic=time.monotonic,
) -> str:
    """非同期 Textract API (StartDocumentAnalysis) でテキスト抽出

    完了待ちには上限がある。以前は `while True` に `time.sleep(5)` だけで、
    ジョブが SUCCEEDED も FAILED も返さない限り Lambda のタイムアウトまで回り
    続けた。OcrFunction の Timeout は 600 秒だが Textract の非同期ジョブは
    大きなドキュメントでそれを超えることがあるため、実際に到達しうる経路である。
    その場合 Lambda は待機中に停止させられ、Step Functions からはどの
    ドキュメントで何が起きたのか分からなくなる。

    Args:
        textract_client: boto3 Textract クライアント
        s3_bucket: ドキュメントが格納されている S3 バケット
        s3_key: ドキュメントの S3 キー
        wait_budget_seconds: 完了待ちの上限秒数。None なら
            `_DEFAULT_MAX_WAIT_SECONDS`。
        poll_interval_seconds: ポーリング間隔。None なら
            `_DEFAULT_POLL_INTERVAL_SECONDS`。
        sleep: 待機に使う関数。テストから差し替えるために引数にしている
            （実時間を待たずに打ち切り経路を検証できる）。
        monotonic: 経過時間の計測に使う関数。壁時計ではなく単調増加時計を
            使うのは、システム時刻の変更で待機が伸縮しないようにするため。

    Returns:
        str: 抽出されたテキスト

    Raises:
        TextractJobTimeout: 上限内にジョブが完了しなかった
        RuntimeError: ジョブが FAILED を返した、または結果ページが多すぎる
    """
    budget = _DEFAULT_MAX_WAIT_SECONDS if wait_budget_seconds is None else wait_budget_seconds
    interval = _DEFAULT_POLL_INTERVAL_SECONDS if poll_interval_seconds is None else poll_interval_seconds

    # 非同期 Textract は DocumentLocation.S3Object しか受け付けない（AWS リファレンスで
    # `DocumentLocation` のメンバは S3 オブジェクトのみ）。同期 API のように bytes を
    # inline で渡す経路が無いため、**FSx for ONTAP の S3 AP を直接指定できない**
    # （Rekognition/Textract は AP を S3 参照で読めない。詳細は
    # docs/agent/pitfalls-s3ap-ontap.md）。このパターンは通常の S3 バケットを前提とし、
    # AP 上のデータを扱う場合は先に S3 へ配置する必要がある。
    response = textract_client.start_document_analysis(
        DocumentLocation={
            "S3Object": {
                "Bucket": s3_bucket,
                "Name": s3_key,
            }
        },
        FeatureTypes=["TABLES", "FORMS"],
    )

    job_id = response["JobId"]
    logger.info(
        "Textract async job started: job_id=%s, wait_budget=%.1fs, poll_interval=%.1fs",
        job_id,
        budget,
        interval,
    )

    # ジョブ完了を待機（上限あり）
    started = monotonic()
    polls = 0
    while True:
        result = textract_client.get_document_analysis(JobId=job_id)
        status = result["JobStatus"]
        polls += 1

        if status == "SUCCEEDED":
            break
        if status == "FAILED":
            raise RuntimeError(f"Textract job {job_id} failed: {result.get('StatusMessage', 'Unknown error')}")

        elapsed = monotonic() - started
        # 次の sleep を終えた時点で上限を超えるなら、待たずに打ち切る。
        # 「上限を超えてから気付く」と、その 1 回分だけ確実に超過する。
        if elapsed + interval > budget:
            raise TextractJobTimeout(
                f"Textract job {job_id} did not finish within {budget:.1f}s "
                f"(status={status}, polls={polls}, elapsed={elapsed:.1f}s)"
            )

        sleep(interval)

    logger.info(
        "Textract async job finished: job_id=%s, polls=%d, elapsed=%.1fs",
        job_id,
        polls,
        monotonic() - started,
    )

    # 全ページのテキストを収集
    lines = []
    for block in result.get("Blocks", []):
        if block["BlockType"] == "LINE":
            lines.append(block.get("Text", ""))

    # ページネーション対応（ページ数にも上限を置く）
    next_token = result.get("NextToken")
    pages = 1
    while next_token:
        if pages >= _MAX_RESULT_PAGES:
            raise RuntimeError(f"Textract job {job_id} returned more than {_MAX_RESULT_PAGES} result pages")
        result = textract_client.get_document_analysis(JobId=job_id, NextToken=next_token)
        pages += 1
        for block in result.get("Blocks", []):
            if block["BlockType"] == "LINE":
                lines.append(block.get("Text", ""))
        next_token = result.get("NextToken")

    return "\n".join(lines)


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """OCR Lambda: ドキュメント取得 → Textract OCR 実行

    Map ステートから以下の形式でドキュメント情報を受け取る:
        {"Key": str, "Size": int, "page_count": int (optional)}

    Returns:
        dict: document_key, extracted_text, page_count, api_mode
    """
    document_key = event["Key"]
    document_size = event.get("Size", 0)

    # ページ数の決定: イベントから取得、なければファイルサイズから推定
    # PDF の平均ページサイズ ~100KB をヒューリスティックとして使用
    page_count = event.get("page_count")
    if page_count is None:
        page_count = max(1, document_size // 100_000)

    api_mode = select_textract_api(
        page_count,
        threshold=int(os.environ.get("TEXTRACT_PAGE_THRESHOLD", "1")),
    )

    logger.info(
        "OCR processing: key=%s, size=%d, page_count=%d, api_mode=%s",
        document_key,
        document_size,
        page_count,
        api_mode,
    )

    # Textract クライアント（ap-northeast-1 非対応のため TEXTRACT_REGION で指定）
    # 参考: https://docs.aws.amazon.com/general/latest/gr/textract.html
    textract_region = os.environ.get("TEXTRACT_REGION", "us-east-1")
    textract_client = boto3.client("textract", region_name=textract_region)

    try:
        if api_mode == "sync":
            # 同期 API: ドキュメントバイトを直接渡す
            s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
            response = s3ap.get_object(document_key)
            document_bytes = response["Body"].read()

            extracted_text = _extract_text_sync(textract_client, document_bytes)
        else:
            # 非同期 API: S3 ロケーションを渡す
            # 非同期 API は S3 バケット/キーを直接参照する
            s3_bucket = os.environ["S3_ACCESS_POINT"]

            # 完了待ちの上限は Lambda の残り時間から決める。固定値にすると、
            # Timeout を変えたときに上限が追従せず、また Map の同時実行で
            # 起動が遅れた分を考慮できない。
            remaining_millis = None
            get_remaining = getattr(context, "get_remaining_time_in_millis", None)
            if callable(get_remaining):
                try:
                    candidate = get_remaining()
                    # ローカル実行やテストダブルでは数値以外が返ることがある。
                    # その場合は既定の上限に倒す（比較で落とさない）。
                    if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                        remaining_millis = float(candidate)
                except Exception:  # pragma: no cover - 取得失敗時は既定値に倒す
                    remaining_millis = None

            extracted_text = _extract_text_async(
                textract_client,
                s3_bucket,
                document_key,
                wait_budget_seconds=async_wait_budget(remaining_millis),
            )

    except Exception as e:
        logger.error("Textract error for document %s: %s", document_key, str(e))
        # エラー時はログ出力して空テキストで続行（ワークフロー全体を停止しない）
        return {
            "document_key": document_key,
            "extracted_text": "",
            "page_count": page_count,
            "api_mode": api_mode,
            "error": str(e),
        }

    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="ocr")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "financial-idp"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "document_key": document_key,
        "extracted_text": extracted_text,
        "page_count": page_count,
        "api_mode": api_mode,
    }
