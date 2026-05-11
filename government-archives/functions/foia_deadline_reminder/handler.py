"""UC16 Government Archives FOIA Deadline Reminder Lambda

FOIA 請求（20 営業日以内の回答期限）を追跡し、期限が近いものに対して
SNS でリマインダー通知を送信する。

US 連邦祝日を除外した営業日計算を行う。

Environment Variables:
    FOIA_TABLE: DynamoDB FOIA Deadline テーブル名
    SNS_TOPIC_ARN: 通知先 SNS Topic ARN
    REMINDER_DAYS_BEFORE: リマインダー日数 (default: 3)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta

import boto3
from boto3.dynamodb.conditions import Attr

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


# US 連邦祝日（2026 年の例、実運用では holidays ライブラリ推奨）
US_FEDERAL_HOLIDAYS_2026 = frozenset({
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # MLK Day
    date(2026, 2, 16),   # Presidents Day
    date(2026, 5, 25),   # Memorial Day
    date(2026, 6, 19),   # Juneteenth
    date(2026, 7, 4),    # Independence Day
    date(2026, 9, 7),    # Labor Day
    date(2026, 10, 12),  # Columbus Day
    date(2026, 11, 11),  # Veterans Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
})


def is_business_day(d: date, holidays: frozenset[date] = US_FEDERAL_HOLIDAYS_2026) -> bool:
    """営業日判定（月-金、祝日を除く）。"""
    if d.weekday() >= 5:  # Sat=5, Sun=6
        return False
    if d in holidays:
        return False
    return True


def add_business_days(
    start: date, days: int, holidays: frozenset[date] = US_FEDERAL_HOLIDAYS_2026
) -> date:
    """開始日から指定営業日数後の日付を返す。"""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if is_business_day(current, holidays):
            added += 1
    return current


def compute_foia_deadline(received_date: str) -> str:
    """FOIA 受付日から 20 営業日後の期限を計算する（ISO date）。"""
    try:
        received = datetime.fromisoformat(received_date.replace("Z", "")).date()
    except ValueError:
        received = date.today()
    deadline = add_business_days(received, 20)
    return deadline.isoformat()


def days_until_deadline(deadline_str: str, today: date | None = None) -> int:
    """期限までの営業日数を計算する。"""
    if today is None:
        today = date.today()
    try:
        deadline = datetime.fromisoformat(deadline_str).date()
    except ValueError:
        return 999

    if deadline <= today:
        return 0

    count = 0
    current = today
    while current < deadline:
        current += timedelta(days=1)
        if is_business_day(current):
            count += 1
    return count


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC16 FOIA Deadline Reminder Lambda ハンドラ。

    EventBridge Schedule でトリガー。
    全 PENDING FOIA リクエストを走査し、期限接近したものに SNS 通知。

    Input:
        {}  # EventBridge event

    Output:
        {"checked": int, "reminders_sent": int, "overdue": int}
    """
    table_name = os.environ["FOIA_TABLE"]
    sns_topic_arn = os.environ["SNS_TOPIC_ARN"]
    reminder_days = int(os.environ.get("REMINDER_DAYS_BEFORE", "3"))

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    sns = boto3.client("sns")

    # PENDING ステータスの FOIA 請求をスキャン
    response = table.scan(
        FilterExpression=Attr("status").eq("PENDING"),
    )
    items = response.get("Items", [])

    checked = len(items)
    reminders_sent = 0
    overdue = 0
    today = date.today()

    for item in items:
        deadline = item.get("deadline", "")
        request_id = item.get("request_id", "unknown")
        days_left = days_until_deadline(deadline, today)

        if days_left == 0:
            # 期限超過
            overdue += 1
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject=f"[UC16 OVERDUE] FOIA Request {request_id}",
                Message=json.dumps({
                    "alert_type": "FOIA_OVERDUE",
                    "request_id": request_id,
                    "deadline": deadline,
                    "status": "OVERDUE",
                }, default=str),
                MessageAttributes={
                    "severity": {"DataType": "String", "StringValue": "HIGH"},
                },
            )
            reminders_sent += 1
        elif days_left <= reminder_days:
            # リマインダー
            last_reminder = item.get("last_reminder_sent")
            # 重複リマインダーを避けるため 1 日 1 回に制限
            if last_reminder == today.isoformat():
                continue
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject=f"[UC16 Reminder] FOIA Request {request_id} due in {days_left} business days",
                Message=json.dumps({
                    "alert_type": "FOIA_DEADLINE_APPROACHING",
                    "request_id": request_id,
                    "deadline": deadline,
                    "days_left": days_left,
                    "status": "PENDING",
                }, default=str),
                MessageAttributes={
                    "severity": {"DataType": "String", "StringValue": "MEDIUM"},
                },
            )
            # リマインダー送信日を更新
            table.update_item(
                Key={"request_id": request_id},
                UpdateExpression="SET last_reminder_sent = :today",
                ExpressionAttributeValues={":today": today.isoformat()},
            )
            reminders_sent += 1

    logger.info(
        "UC16 FOIA Deadline Reminder: checked=%d, reminders_sent=%d, overdue=%d",
        checked,
        reminders_sent,
        overdue,
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="foia_deadline_reminder")
    metrics.set_dimension("UseCase", "government-archives")
    metrics.put_metric("FoiaRequestsChecked", float(checked), "Count")
    metrics.put_metric("RemindersSent", float(reminders_sent), "Count")
    metrics.put_metric("OverdueRequests", float(overdue), "Count")
    metrics.flush()

    return {
        "checked": checked,
        "reminders_sent": reminders_sent,
        "overdue": overdue,
    }
