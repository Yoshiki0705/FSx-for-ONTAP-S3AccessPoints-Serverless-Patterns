#!/usr/bin/env python3
"""Build every architecture diagram in this repository from declarative specs.

Compliance (official icons, native sizes, service-name labels, single-colour Open
Arrow edges, ※-numbered notes) is enforced by scripts/diagram_builder.py, so these
specs only describe content and grid placement.

Both the Japanese and the English variant are emitted from the same spec (see the
EN dictionary below). The Part 1 figures were hand-authored XML until they were
ported here; the two scripts that maintained them — apply-official-aws-icons.py,
which stamped icons into that XML, and generate-en-diagrams.py, which produced the
English variant by string substitution — are no longer part of the pipeline.

Usage (from repo root):
    python3 scripts/build-diagrams.py --icon-root /tmp/awsicons
    bash scripts/export-diagrams.sh

To check a diagram visually, downscale it first: exported PNGs are @2x and an agent
cannot read an image whose long edge exceeds 2000 px.
    python3 scripts/preview-diagram.py part3-agentchat-modes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diagram_builder import (  # noqa: E402
    BOX,
    RESOURCE,
    SERVICE,
    Diagram,
    Edge,
    Grid,
    Group,
    IconResolver,
    Node,
    translate_diagram,
    write,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "docs" / "diagrams"

# --- icon shorthands -----------------------------------------------------------
USERS = "Res_Users_48_Light.svg"
S3AP = "Res_Amazon-Simple-Storage-Service_General-Access-Points_48.svg"
AMPLIFY = "Arch_AWS-Amplify_64.svg"
COGNITO = "Arch_Amazon-Cognito_64.svg"
APPSYNC = "Arch_AWS-AppSync_64.svg"
LAMBDA = "Arch_AWS-Lambda_64.svg"
SECRETS = "Arch_AWS-Secrets-Manager_64.svg"
FSXN = "Arch_Amazon-FSx-for-NetApp-ONTAP_64.svg"
ATHENA = "Arch_Amazon-Athena_64.svg"
GLUE = "Arch_AWS-Glue_64.svg"
CLOUDTRAIL = "Arch_AWS-CloudTrail_64.svg"
S3 = "Arch_Amazon-Simple-Storage-Service_64.svg"
BEDROCK = "Arch_Amazon-Bedrock_64.svg"
AGENTCORE = "Arch_Amazon-Bedrock-AgentCore_64.svg"
OPENSEARCH = "Arch_Amazon-OpenSearch-Service_64.svg"
DATASYNC = "Arch_AWS-DataSync_64.svg"
SFN = "Arch_AWS-Step-Functions_64.svg"
SQS = "Arch_Amazon-Simple-Queue-Service_64.svg"
DYNAMODB = "Arch_Amazon-DynamoDB_64.svg"
NATGW = "Res_Amazon-VPC_NAT-Gateway_48.svg"
EC2 = "Arch_Amazon-EC2_64.svg"
ELB = "Arch_Elastic-Load-Balancing_64.svg"
RDS = "Arch_Amazon-RDS_64.svg"
QUICK = "Arch_Amazon-Quick_64.svg"
EVENTBRIDGE = "Arch_Amazon-EventBridge_64.svg"
CLIENT = "Res_Client_48_Light.svg"
# The 07312026 package renamed this asset: the generation the hand-authored Part 1
# figures embedded called it `Res_Traditional-server_48_Light`.
SERVER = "Res_Server_48_Light.svg"

# state / phase tints. These are plain boxes, not AWS icons, so the icon colour
# rules do not apply — the tint only aids scanning.
RED = "#FDEDEE"
ORANGE = "#FEF3E6"
YELLOW = "#FFFBE6"
GREEN = "#EDF6EC"
BLUE = "#EDF3FB"
GREY = "#F5F5F5"


# --- Part 1 --------------------------------------------------------------------
# Both notes appear on all four Part 1 figures, and both are about the access point
# rather than about one portal, so they stay identical across the four.
PART1_NOTES = [
    (
        "S3 Access Point の Internet origin はパブリック公開ではない",
        "Block Public Access が常時有効（無効化不可）。全リクエストで IAM の認証と認可が必要",
    ),
    (
        "マルチプロトコルでの同時アクセス",
        "同一データに NFS / SMB / S3 API でアクセス可能。データ移行は不要",
    ),
]
# The spine every Part 1 figure ends with: one access point, one file system, and the
# same data reachable over both file protocols.
NFS_LABEL = "NFS クライアント"
SMB_LABEL = "SMB クライアント"


def part1_overview() -> Diagram:
    """Both portals over one access point — the figure the Part 1 article opens with.

    Two portals on row 1, the shared spine down the middle, both file protocols on the
    last row. The AI services are one box rather than five icons: this figure exists to
    show that the two portals meet at the access point, and the fan-out belongs to
    amplify-vpc-split, which is one figure away.
    """
    return Diagram(
        id="architecture-overview",
        name="Part1 Overview",
        title="FSx for ONTAP S3 Access Points — ファイルポータル全体構成",
        grid=Grid(col_pitch=340, row_pitch=175, box_w=300),
        nodes=[
            Node("users", "利用者（Web ブラウザ）", 1, 0, RESOURCE, icon=USERS),
            Node("amplify", "AWS Amplify<br>(Gen2 / AI 処理ダッシュボード)", 0, 1, icon=AMPLIFY),
            Node("nextcloud", "Amazon EC2<br>(Nextcloud / ファイル共有 UI)", 2, 1, icon=EC2),
            Node(
                "ai_group",
                "AWS Lambda + AI サービス<br>(Amazon Bedrock / Amazon Textract / Amazon Athena ほか)",
                0.5,
                2,
                BOX,
                w=520,
                h=86,
            ),
            Node("s3ap", "Amazon S3 Access Point", 1, 3, RESOURCE, icon=S3AP),
            Node("fsxn", "Amazon FSx for<br>NetApp ONTAP", 1, 4, icon=FSXN),
            Node("nfs_client", NFS_LABEL, 0, 5, RESOURCE, icon=SERVER),
            Node("smb_client", SMB_LABEL, 2, 5, RESOURCE, icon=CLIENT),
        ],
        edges=[
            Edge("users", "amplify", "HTTPS"),
            Edge("users", "nextcloud", "HTTPS"),
            Edge("amplify", "ai_group"),
            Edge("ai_group", "s3ap", "S3 API"),
            Edge("nextcloud", "s3ap", "S3 API<br>(External Storage)", at=-0.6),
            Edge("s3ap", "fsxn"),
            Edge("fsxn", "nfs_client", "NFS"),
            Edge("fsxn", "smb_client", "SMB"),
        ],
        groups=[Group("aws_cloud", "AWS Cloud", (0, 2), (1, 5))],
        notes=PART1_NOTES,
    )


def part1_nextcloud() -> Diagram:
    """The Nextcloud portal, and the scheduled pipeline that runs beside it.

    The four AI services Step Functions calls are one box, for the same reason as in
    part1_overview: what this figure is for is the shape of the path, and five icons in
    a row is what pushed the hand-authored version to 1734px.
    """
    return Diagram(
        id="nextcloud-external-storage",
        name="Part1 Nextcloud",
        title="FSx for ONTAP S3 Access Points — Nextcloud によるファイル共有 UI 構成",
        grid=Grid(col_pitch=310, row_pitch=170, box_w=270),
        nodes=[
            # Directly above the load balancer it enters, so the first hop is a
            # straight drop. At column 1 it sat above the instance instead, with its
            # own arrow leaving sideways to a box two columns away.
            Node("browser", "Web ブラウザ<br>(ファイル管理 + 同期)", 0, 0, RESOURCE, icon=USERS),
            Node("rds", "Amazon RDS<br>(MariaDB)", 2, 1, icon=RDS),
            Node("alb", "Elastic Load Balancing", 0, 1, icon=ELB),
            Node("nextcloud", "Amazon EC2<br>(Nextcloud / Docker)", 1, 1, icon=EC2),
            Node("eventbridge", "Amazon EventBridge<br>Scheduler", 2, 2, icon=EVENTBRIDGE),
            Node(
                "ai_group",
                # Broken by hand: left to wrap, the third line began "Amazon" and the
                # fourth began "Athena".
                "AI サービス<br>(Amazon Bedrock / Amazon Rekognition<br>Amazon Athena / Amazon Comprehend)",
                0,
                3,
                BOX,
                w=440,
                h=96,
            ),
            Node("sfn", "AWS Step Functions<br>(UC1-28)", 2, 3, icon=SFN),
            Node("s3ap", "Amazon S3 Access Point<br>(Internet origin)", 1, 4, RESOURCE, icon=S3AP),
            Node("fsxn", "Amazon FSx for<br>NetApp ONTAP", 1, 5, icon=FSXN),
            Node("nfs_client", NFS_LABEL, 0, 6, RESOURCE, icon=SERVER),
            Node("smb_client", SMB_LABEL, 2, 6, RESOURCE, icon=CLIENT),
        ],
        edges=[
            # Placed by hand into the band between the cloud frame and the load
            # balancer. The automatic offset moved it up, away from the group's own
            # label, and it landed inside the browser's two-line label, where the node
            # paints over it and the label simply disappears.
            Edge("browser", "alb", "HTTPS", dy=28),
            Edge("alb", "nextcloud"),
            Edge("nextcloud", "rds"),
            Edge(
                "nextcloud",
                "eventbridge",
                "Webhook / Schedule",
                # Pushed toward the scheduler. At the path midpoint it sat on the
                # External Storage label, which rides the next column's vertical.
                at=0.45,
                exit=(0.75, 1),
                entry=(0, 0.5),
            ),
            Edge("eventbridge", "sfn"),
            Edge("sfn", "ai_group"),
            # Unlabelled on purpose. "S3 AP" restated what the target icon already
            # says, and on this two-bend route it came to rest away from every
            # segment, so it read as belonging to nothing.
            Edge("sfn", "s3ap", exit=(0.25, 1)),
            Edge("nextcloud", "s3ap", "External Storage<br>(S3 API)", at=-0.5),
            Edge("s3ap", "fsxn"),
            Edge("fsxn", "nfs_client", "NFS"),
            Edge("fsxn", "smb_client", "SMB"),
        ],
        groups=[Group("aws_cloud", "AWS Cloud", (0, 2), (1, 6))],
        notes=PART1_NOTES,
    )


def part1_amplify() -> Diagram:
    """The Amplify Gen2 portal: the AI path, and where the audit trail lands.

    Five AI services become one box. The AgentCore gateway keeps its own icon because
    the figure's second claim is that a desktop client reaches the same Lambda the
    portal does, and that claim needs both ends drawn.
    """
    return Diagram(
        id="amplify-vpc-split",
        name="Part1 Amplify",
        title="FSx for ONTAP S3 Access Points — Amplify Gen2 による AI 処理ポータル構成",
        grid=Grid(col_pitch=310, row_pitch=170, box_w=270),
        nodes=[
            Node("browser", "Web ブラウザ", 1, 0, RESOURCE, icon=USERS),
            Node("quick_desktop", "Amazon Quick", 2, 0, icon=QUICK),
            Node("cognito", "Amazon Cognito", 0, 1, icon=COGNITO),
            Node("amplify", "AWS Amplify", 1, 1, icon=AMPLIFY),
            Node("mcp_gw", "Amazon Bedrock AgentCore", 2, 1, icon=AGENTCORE),
            Node("appsync", "AWS AppSync<br>(GraphQL API)", 1, 2, icon=APPSYNC),
            Node(
                "ai_group",
                "AI サービス<br>(Amazon Bedrock / Amazon Rekognition<br>"
                "Amazon Athena / Amazon Textract<br>Amazon Comprehend)",
                0,
                3,
                BOX,
                w=440,
                h=118,
            ),
            Node("lambda", "AWS Lambda<br>(VPC 外 / ARM64)", 1, 3, icon=LAMBDA),
            Node("s3_objectlock", "Amazon S3<br>(Object Lock / WORM)", 2, 4, icon=S3),
            Node("s3ap", "Amazon S3 Access Point<br>(Internet origin)", 1, 5, RESOURCE, icon=S3AP),
            Node("fsxn", "Amazon FSx for<br>NetApp ONTAP", 1, 6, icon=FSXN),
            Node("nfs_client", NFS_LABEL, 0, 7, RESOURCE, icon=SERVER),
            Node("smb_client", "SMB クライアント<br>(Windows)", 2, 7, RESOURCE, icon=CLIENT),
        ],
        edges=[
            Edge("browser", "amplify"),
            Edge("quick_desktop", "mcp_gw"),
            Edge("amplify", "cognito"),
            Edge("amplify", "appsync"),
            Edge("appsync", "lambda"),
            Edge("mcp_gw", "lambda"),
            Edge("lambda", "ai_group"),
            Edge("lambda", "s3_objectlock", "CloudTrail 監査ログ", at=-0.6),
            Edge("lambda", "s3ap", "GetObject / PutObject", at=-0.5, dy=10),
            Edge("s3ap", "fsxn"),
            Edge("fsxn", "nfs_client", "NFS"),
            Edge("fsxn", "smb_client", "SMB"),
        ],
        groups=[Group("aws_cloud", "AWS Cloud", (0, 2), (1, 7))],
        notes=PART1_NOTES,
    )


def part1_coexistence() -> Diagram:
    """The two portals side by side, meeting at one access point.

    This one is deliberately the most abstracted of the four. It used to be the other
    two figures drawn again in full, side by side, which is how it reached 2214px --
    and at that width its labels arrive at 4.4px, so the detail it was carrying could
    not be read anyway. Each portal is one box naming its own services, and the reader
    who wants either side has a figure for it.
    """
    return Diagram(
        id="coexistence-3path",
        name="Part1 Coexistence",
        title="FSx for ONTAP S3 Access Points — Amplify Gen2 と Nextcloud の併用構成",
        grid=Grid(col_pitch=330, row_pitch=175, box_w=290),
        nodes=[
            Node("browser_ai", "Web ブラウザ<br>(AI ポータル)", 0, 0, RESOURCE, icon=USERS),
            Node("browser_files", "Web ブラウザ<br>(ファイル管理)", 2, 0, RESOURCE, icon=USERS),
            Node(
                "ai_side",
                # Three explicit lines. Left to wrap, the second one broke between
                # "AWS" and "Lambda", and a service name split across lines is the one
                # thing the label rules do not allow.
                "AWS Amplify (Gen2)<br>Amazon Cognito / AWS AppSync<br>AWS Lambda / AI サービス",
                0,
                1,
                BOX,
                w=320,
                h=116,
            ),
            Node(
                "files_side",
                "Amazon EC2 (Nextcloud)<br>Elastic Load Balancing<br>Amazon RDS (MariaDB)",
                2,
                1,
                BOX,
                w=320,
                h=116,
            ),
            Node("s3ap", "Amazon S3 Access Point<br>(Internet origin)", 1, 2, RESOURCE, icon=S3AP),
            Node("fsxn", "Amazon FSx for<br>NetApp ONTAP", 1, 3, icon=FSXN),
            Node("nfs_client", NFS_LABEL, 0, 4, RESOURCE, icon=SERVER),
            Node("smb_client", "SMB クライアント<br>(Windows)", 2, 4, RESOURCE, icon=CLIENT),
        ],
        edges=[
            Edge("browser_ai", "ai_side"),
            Edge("browser_files", "files_side"),
            # Down each portal's own column, then in from the side. Routed through the
            # midpoint above the access point instead, the two edges share one vertical
            # run: the later line strikes through the earlier label, and a reader
            # cannot tell which portal either label belongs to.
            Edge(
                "ai_side",
                "s3ap",
                "GetObject / PutObject",
                at=-0.55,
                exit=(0.5, 1),
                entry=(0, 0.5),
            ),
            Edge(
                "files_side",
                "s3ap",
                "External Storage<br>(S3 API)",
                at=-0.55,
                exit=(0.5, 1),
                entry=(1, 0.5),
            ),
            Edge("s3ap", "fsxn"),
            Edge("fsxn", "nfs_client", "NFS"),
            Edge("fsxn", "smb_client", "SMB"),
        ],
        groups=[Group("aws_cloud", "AWS Cloud", (0, 2), (1, 4))],
        notes=PART1_NOTES,
    )


# --- Part 2 --------------------------------------------------------------------
def part2_overview() -> Diagram:
    return Diagram(
        id="part2-admin-operations",
        name="Part2 Storage Operations Overview",
        title="ストレージ運用機能をポータルに組み込む — 管理操作の経路",
        nodes=[
            Node("browser", "利用者（Web ブラウザ）", 2, 0, RESOURCE, USERS),
            Node("cognito", "Amazon Cognito", 1, 1, SERVICE, COGNITO),
            Node("amplify", "AWS Amplify", 2, 1, SERVICE, AMPLIFY),
            Node("appsync", "AWS AppSync", 2, 2, SERVICE, APPSYNC),
            Node("lambda", "AWS Lambda<br>(VPC 内)", 2, 3, SERVICE, LAMBDA),
            # Two lines: at the label floor the single-line form is wider than the
            # column and ran past the AWS Cloud boundary on the right.
            Node("secrets", "AWS Secrets<br>Manager", 3, 3, SERVICE, SECRETS),
            Node("fsxn", "Amazon FSx for<br>NetApp ONTAP", 2, 4, SERVICE, FSXN),
        ],
        groups=[Group("aws-cloud", "AWS Cloud", (1, 3), (1, 4))],
        edges=[
            Edge("browser", "amplify", "HTTPS"),
            Edge("amplify", "cognito", "認証 /<br>グループ判定"),
            Edge("amplify", "appsync"),
            Edge("appsync", "lambda"),
            Edge("lambda", "secrets", "認証情報の取得"),
            Edge("lambda", "fsxn", "ONTAP REST API"),
        ],
        notes=[
            (
                "権限分離は Cognito Groups で行う",
                "storage-admin グループのみが変更操作を実行でき、一般ユーザーは閲覧のみ",
            ),
            (
                "不可逆操作は実行前に確認が必要",
                "SnapLock Compliance の有効化と保持期間の短縮は取り消せない",
            ),
        ],
    )


def part2_arp_lifecycle() -> Diagram:
    return Diagram(
        id="part2-arp-incident-lifecycle",
        name="Part2 ARP Incident Lifecycle",
        title="ARP/AI インシデントライフサイクル — 4 状態での管理",
        # One column, like the other state pipeline in this set. Four states in a row
        # needed a 310 pitch to hold "Investigate" -- one word, so unwrappable -- and
        # the canvas that bought was 1158 px, which asks for a 19 px label. Stacked,
        # the transition labels sit on vertical runs and the pitch stops mattering.
        grid=Grid(col_pitch=310, box_w=240),
        nodes=[
            Node("detected", "検知 (Detected)", 0, 0, BOX, fill=RED, stroke="#DD344C"),
            Node("contained", "封じ込め (Contained)", 0, 1, BOX, fill=ORANGE, stroke="#ED7100"),
            Node("investigating", "調査中 (Investigating)", 0, 2, BOX, fill=YELLOW, stroke="#B7950B"),
            Node("resolved", "解決済み (Resolved)", 0, 3, BOX, fill=GREEN, stroke="#3F8624"),
        ],
        edges=[
            Edge("detected", "contained", "封じ込め<br>実行"),
            Edge("contained", "investigating", "調査開始"),
            Edge("investigating", "resolved", "解決"),
        ],
        notes=[
            (
                "各状態で記録される情報",
                "検知=detectedAt / 封じ込め=containedAt・blockedUsers・blockedIps・snapshotName"
                " / 調査中=notes / 解決済み=resolvedAt",
            ),
            (
                "現在の制約",
                "状態は localStorage 保存でブラウザ間共有されない。本番では DynamoDB 永続化を推奨",
            ),
        ],
    )


def part2_audit_log() -> Diagram:
    return Diagram(
        id="part2-audit-log-pipeline",
        name="Part2 Audit Log Pipeline",
        title="Audit Log — 「誰がいつ何にアクセスしたか」を UI で確認する経路",
        # Two columns, not six. The query path used to run left to right across six
        # columns, and a canvas that wide is scaled to a third in a reader's column,
        # which is what put this diagram below the label floor. Depth costs nothing:
        # rows do not compete for the width the reader gives the image.
        grid=Grid(col_pitch=250),
        nodes=[
            Node("browser", "利用者（Web ブラウザ）", 0, 0, RESOURCE, USERS),
            Node("appsync", "AWS AppSync", 0, 1, SERVICE, APPSYNC),
            Node("lambda", "AWS Lambda", 0, 2, SERVICE, LAMBDA),
            Node("athena", "Amazon Athena", 0, 3, SERVICE, ATHENA),
            Node("glue", "AWS Glue<br>(Data Catalog)", 1, 3, SERVICE, GLUE),
            Node("s3logs", "Amazon S3<br>(CloudTrail ログ)", 0, 4, SERVICE, S3),
            # same row as the bucket, so the connector stays a straight horizontal
            # run and never crosses the bucket's label
            Node("cloudtrail", "AWS CloudTrail", 1, 4, SERVICE, CLOUDTRAIL),
        ],
        groups=[Group("aws-cloud", "AWS Cloud", (0, 1), (1, 4))],
        edges=[
            Edge("browser", "appsync", "監査クエリ"),
            Edge("appsync", "lambda"),
            Edge("lambda", "athena", "SQL 実行"),
            Edge("athena", "glue", "テーブル定義を参照"),
            Edge("athena", "s3logs", "ログをスキャン"),
            Edge("cloudtrail", "s3logs", "S3 データイベント<br>を記録"),
        ],
        notes=[
            (
                "前提条件",
                "S3 AP の ARN に対して CloudTrail のデータイベントを有効化し、"
                "Glue Crawler もしくは手動 CREATE TABLE で Athena テーブルを作成しておく",
            ),
            (
                "保持期間はバケット側で制御",
                "CloudTrail ログの保持は Trail のバケットのライフサイクルポリシーで設定する",
            ),
        ],
    )


def part2_vpc_split() -> Diagram:
    return Diagram(
        id="part2-ontap-rest-api-path",
        name="Part2 ONTAP REST API Path",
        title="ブラウザから ONTAP REST API を操作する経路（VPC 内 Lambda）",
        grid=Grid(col_pitch=250),
        nodes=[
            Node("browser", "利用者（Web ブラウザ）", 0, 0, RESOURCE, USERS),
            Node("appsync", "AWS AppSync", 1, 0, SERVICE, APPSYNC),
            Node("lambda", "AWS Lambda", 2, 0, SERVICE, LAMBDA),
            Node("secrets", "AWS Secrets Manager", 2, 1, SERVICE, SECRETS),
            Node("fsxn", "Amazon FSx for<br>NetApp ONTAP", 3, 0, SERVICE, FSXN),
        ],
        groups=[
            Group("aws-cloud", "AWS Cloud", (1, 3), (0, 1)),
            Group(
                "vpc",
                "VPC",
                (2, 3),
                (0, 0),
                gr_icon="group_vpc2",
                stroke="#8C4FFF",
                inset=26,
            ),
        ],
        edges=[
            Edge("browser", "appsync", "Cognito 認証"),
            Edge("appsync", "lambda"),
            Edge("lambda", "secrets", "fsxadmin 認証情報"),
            Edge("lambda", "fsxn", "ONTAP REST API"),
        ],
        notes=[
            (
                "Lambda を VPC 内に置く理由",
                "ONTAP の管理 LIF はプライベート（TCP 443）。一方 S3 AP は Internet origin"
                " なので、1 つの Lambda で両方を兼用できない",
            ),
            (
                "認証情報は必ず同時に更新する",
                "fsxadmin のパスワード変更時に FSx API と Secrets Manager の片方だけを"
                "更新すると認証失敗し、ONTAP 側のアカウントロックの契機になる",
            ),
        ],
    )


def part2_poc_to_prod() -> Diagram:
    return Diagram(
        id="part2-poc-to-production",
        name="Part2 PoC to Production",
        title="PoC から本番接続までの 3 フェーズ",
        grid=Grid(col_pitch=260),
        nodes=[
            Node("p1", "Phase 1: PoC<br>（約 15 分）", 0, 0, BOX, fill=BLUE, stroke="#2E73B8", w=210),
            Node("p2", "Phase 2: VPC 接続追加<br>（約 30 分）", 1, 0, BOX, fill=BLUE, stroke="#2E73B8", w=210),
            Node("p3", "Phase 3: 本番ハードニング<br>（約 60 分）", 2, 0, BOX, fill=BLUE, stroke="#2E73B8", w=210),
            Node(
                "d1",
                "DemoMode=true<br>S3 バケットで動作確認<br>認証: Amazon Cognito",
                0,
                1,
                BOX,
                fill=GREY,
                h=100,
            ),
            Node(
                "d2",
                "ONTAP 管理 LIF へ接続<br>AWS Secrets Manager 登録<br>VPC エンドポイント追加",
                1,
                1,
                BOX,
                fill=GREY,
                h=100,
            ),
            Node(
                "d3",
                "IAM 最小権限化<br>MFA 必須化 / AWS WAF 追加<br>監査ログ有効化",
                2,
                1,
                BOX,
                fill=GREY,
                h=100,
            ),
        ],
        edges=[
            Edge("p1", "p2"),
            Edge("p2", "p3"),
            Edge("p1", "d1"),
            Edge("p2", "d2"),
            Edge("p3", "d3"),
        ],
        notes=[
            (
                "追加コストの目安",
                "Phase 1 は 0 USD、Phase 2 で VPC Lambda 約 5 USD/月、"
                "Phase 3 で CloudTrail データイベント約 10〜50 USD/月",
            ),
            (
                "Phase をまたいでも変わらないもの",
                "フロントエンドの UI、Cognito の設定、アプリケーションコードは変更不要",
            ),
        ],
    )


def part3_overview() -> Diagram:
    return Diagram(
        id="part3-ai-agent-overview",
        name="Part3 AI Agent Overview",
        title="ファイルポータルに AI エージェントを組み込む — 全体構成",
        nodes=[
            Node("browser", "利用者（Web ブラウザ）", 1, 0, RESOURCE, USERS),
            Node("amplify", "AWS Amplify", 1, 1, SERVICE, AMPLIFY),
            Node("appsync", "AWS AppSync", 1, 2, SERVICE, APPSYNC),
            Node("bedrock", "Amazon Bedrock<br>(Converse API)", 0, 3, SERVICE, BEDROCK),
            Node("agent", "AWS Lambda<br>(エージェント実行)", 1, 3, SERVICE, LAMBDA),
            Node("agentcore", "Amazon Bedrock<br>AgentCore", 2, 3, SERVICE, AGENTCORE),
            Node("mcp", "AWS Lambda<br>(MCP ツール)", 3, 3, SERVICE, LAMBDA),
            Node("s3ap", "Amazon S3 Access Point", 3, 4, RESOURCE, S3AP),
            Node("fsxn", "Amazon FSx for<br>NetApp ONTAP", 3, 5, SERVICE, FSXN),
        ],
        groups=[Group("aws-cloud", "AWS Cloud", (0, 3), (1, 5))],
        edges=[
            Edge("browser", "amplify", "HTTPS"),
            Edge("amplify", "appsync"),
            Edge("appsync", "agent"),
            Edge("agent", "bedrock", "推論"),
            Edge("agent", "agentcore", "MCP"),
            Edge("agentcore", "mcp", "Lambda<br>呼び出し"),
            Edge("mcp", "s3ap", "S3 API"),
            Edge("s3ap", "fsxn"),
        ],
        notes=[
            (
                "破壊的操作は人間が承認してから実行",
                "エージェントは提案までを担当し、実行は HITL の承認モーダルを経る",
            ),
            (
                "マルチエージェントが効く範囲",
                "「探索 → 分析 → 判定」の複数フェーズを持つタスクに限られ、単純な検索は単一エージェントの方が速い",
            ),
        ],
    )


def part3_agentchat() -> Diagram:
    return Diagram(
        id="part3-agentchat-modes",
        name="Part3 AgentChat Modes",
        title="AgentChat — 3 モードと MCP ツール経由のファイルアクセス",
        # Three columns, not seven. This was the widest diagram in the set at 1739 px,
        # and the one the label floor punished hardest: fitting its labels by widening
        # the pitch reached 61 px on a 3815 px canvas, which is compliant arithmetic and
        # an unreadable image. The request path and the tool chain both run downwards
        # now; only the mode fan-out spends width, because three boxes beside one source
        # is what it is.
        grid=Grid(col_pitch=250),
        nodes=[
            Node("browser", "利用者（Web ブラウザ）", 2, 0, RESOURCE, USERS),
            Node("appsync", "AWS AppSync", 2, 1, SERVICE, APPSYNC),
            Node("agent", "AWS Lambda<br>(AgentChat)", 2, 2, SERVICE, LAMBDA),
            # mode names follow the handler: TOOLS_BY_MODE = {multi, kb, agent}.
            # kb is limited to the kb_search tool, agent to the file tools.
            Node("m_kb", "mode=kb<br>セマンティック検索のみ", 3, 1, BOX, fill=GREY),
            Node("m_agent", "mode=agent<br>ファイルツールのみ", 3, 2, BOX, fill=GREY),
            Node("m_multi", "mode=multi<br>全ツールで協調", 3, 3, BOX, fill=GREY),
            Node("kb", "Amazon Bedrock<br>(Knowledge Bases)", 4, 1, SERVICE, BEDROCK),
            Node("bedrock", "Amazon Bedrock", 4, 2, SERVICE, BEDROCK),
            # the tool chain continues downwards rather than to the right
            Node("agentcore", "Amazon Bedrock<br>AgentCore", 4, 3, SERVICE, AGENTCORE),
            Node("mcp", "AWS Lambda<br>(MCP ツール)", 4, 4, SERVICE, LAMBDA),
            Node("s3ap", "Amazon S3 Access Point", 3, 4, RESOURCE, S3AP),
        ],
        groups=[Group("aws-cloud", "AWS Cloud", (2, 4), (1, 4))],
        edges=[
            Edge("browser", "appsync", "チャット送信"),
            Edge("appsync", "agent"),
            # fan out from the right of the Lambda into the left of each mode box,
            # so the vertical runs stay in the gap instead of crossing mode=agent
            Edge("agent", "m_kb", exit=(1, 0.5), entry=(0, 0.5)),
            Edge("agent", "m_agent", exit=(1, 0.5), entry=(0, 0.5)),
            Edge("agent", "m_multi", exit=(1, 0.5), entry=(0, 0.5)),
            Edge("m_kb", "kb", "kb_search"),
            Edge("m_agent", "bedrock"),
            Edge("m_multi", "bedrock"),
            Edge("bedrock", "agentcore", "ツール呼び出し"),
            Edge("agentcore", "mcp"),
            Edge("mcp", "s3ap", "list / read / search"),
        ],
        notes=[
            (
                "Gateway 経由の MCP ツールは 3 種",
                "list_files / read_file / search_files。ツール名は targetName___toolName 形式で渡る",
            ),
            (
                "Gateway と Lambda は同一リージョンに置く",
                "クロスリージョンの Lambda 呼び出しはできないため、Gateway・Lambda・S3 AP を同じリージョンに配置する",
            ),
        ],
    )


def part3_semantic_search() -> Diagram:
    return Diagram(
        id="part3-semantic-search",
        name="Part3 Semantic Search",
        title="SemanticSearch — Bedrock Knowledge Bases によるベクトル検索",
        # Three columns, not five. "RetrieveAndGenerate" is an API name that can be
        # neither shortened nor wrapped, and widening the pitch to fit it at the label
        # floor spiralled: wider canvas, larger floor, wider label. Running the query
        # path downwards makes the room instead of buying it.
        grid=Grid(col_pitch=250),
        nodes=[
            Node("s3ap", "Amazon S3 Access Point", 0, 3, RESOURCE, S3AP),
            Node("fsxn", "Amazon FSx for<br>NetApp ONTAP", 0, 4, SERVICE, FSXN),
            Node("browser", "利用者（Web ブラウザ）", 1, 0, RESOURCE, USERS),
            Node("appsync", "AWS AppSync", 1, 1, SERVICE, APPSYNC),
            Node("lambda", "AWS Lambda", 1, 2, SERVICE, LAMBDA),
            Node("kb", "Amazon Bedrock<br>(Knowledge Bases)", 1, 3, SERVICE, BEDROCK),
            # directly under Knowledge Bases, so its edge label does not land on the
            # OpenSearch edge label
            Node(
                "embed",
                "Amazon Bedrock<br>(Titan Text Embeddings V2)",
                1,
                4,
                SERVICE,
                BEDROCK,
            ),
            Node("oss", "Amazon OpenSearch<br>Service", 2, 3, SERVICE, OPENSEARCH),
        ],
        groups=[Group("aws-cloud", "AWS Cloud", (0, 2), (1, 4))],
        edges=[
            Edge("browser", "appsync", "検索クエリ"),
            Edge("appsync", "lambda"),
            Edge("lambda", "kb", "RetrieveAndGenerate"),
            Edge("kb", "oss", "ベクトル検索"),
            # clearance from the two-line Knowledge Bases label is applied
            # automatically (see vertical_label_shortfall)
            Edge("kb", "embed", "埋め込み生成"),
            Edge("kb", "s3ap", "データソース同期"),
            Edge("s3ap", "fsxn"),
        ],
        notes=[
            (
                "検索結果に含まれるもの",
                "関連チャンク・ソースファイルパス・関連度スコア",
            ),
            (
                "同期は自動ではない",
                "ファイル追加後にデータソースの同期ジョブを実行するまで検索対象に入らない",
            ),
        ],
    )


def part3_agent_teams() -> Diagram:
    return Diagram(
        id="part3-agent-teams",
        name="Part3 Agent Teams",
        title="Agent Teams — Supervisor が調整するマルチエージェント協調",
        # One column. Six boxes in a row put every step label in the gap between two
        # of them, and the English labels ("1.<br>Explore", "4. Consolidate") did not fit
        # a gap this pitch could afford at the label floor. Stacked, the same labels
        # sit on vertical runs, which no pitch has to accommodate. box_w carries the
        # widest label line instead -- 250 covers "Summary + filtered results", because
        # `whiteSpace=wrap` is not applied on export and a box label only breaks where
        # a <br> says so.
        grid=Grid(col_pitch=290, box_w=250),
        nodes=[
            Node("user", "利用者の指示<br>「engineering/ を分析して」", 0, 0, BOX, fill=GREY, h=80),
            Node("supervisor", "Supervisor<br>safety-controller", 0, 1, BOX, fill=BLUE, stroke="#2E73B8"),
            Node("explorer", "Collaborator<br>file-explorer", 0, 2, BOX, fill=GREEN, stroke="#3F8624"),
            Node("analyst", "Collaborator<br>knowledge-analyst", 0, 3, BOX, fill=GREEN, stroke="#3F8624"),
            Node("auditor", "Reviewer<br>compliance-auditor", 0, 4, BOX, fill=ORANGE, stroke="#ED7100"),
            Node("answer", "利用者への最終回答<br>要約 + フィルタリング結果", 0, 5, BOX, fill=GREY, h=80),
        ],
        edges=[
            Edge("user", "supervisor"),
            Edge("supervisor", "explorer", "① 探索"),
            Edge("explorer", "analyst", "② 分析"),
            Edge("analyst", "auditor", "③ 検証"),
            Edge("auditor", "answer", "④ 統合"),
        ],
        notes=[
            (
                "各ステップは Supervisor が仲介する",
                "Collaborator 同士は直接やり取りせず、Supervisor が指示と結果を受け渡す",
            ),
            (
                "利用者から見た体験",
                "1 回のチャット送信で複数フェーズが完了し、途中の往復は表に出ない",
            ),
        ],
    )


# --- English text --------------------------------------------------------------
# Keyed by the exact Japanese string in the specs above. `translate_diagram()`
# fails the build when a string is missing or still contains CJK, so a label added
# to a spec cannot ship without its English counterpart.
EN: dict[str, str] = {
    # ---- Part 1 ---------------------------------------------------------------
    # Wording carried over from the published EN figures, so a reader who saw the
    # earlier export finds the same terms.
    "FSx for ONTAP S3 Access Points — ファイルポータル全体構成": (
        "FSx for ONTAP S3 Access Points — File Portal Architecture Overview"
    ),
    "FSx for ONTAP S3 Access Points — Nextcloud によるファイル共有 UI 構成": (
        "FSx for ONTAP S3 Access Points — File Sharing UI with Nextcloud"
    ),
    "FSx for ONTAP S3 Access Points — Amplify Gen2 による AI 処理ポータル構成": (
        "FSx for ONTAP S3 Access Points — AI Processing Portal with Amplify Gen2"
    ),
    "FSx for ONTAP S3 Access Points — Amplify Gen2 と Nextcloud の併用構成": (
        "FSx for ONTAP S3 Access Points — Amplify Gen2 and Nextcloud Side by Side"
    ),
    "AWS Amplify<br>(Gen2 / AI 処理ダッシュボード)": "AWS Amplify<br>(Gen2 / AI dashboard)",
    "Amazon EC2<br>(Nextcloud / ファイル共有 UI)": "Amazon EC2<br>(Nextcloud / file sharing UI)",
    "AWS Lambda + AI サービス<br>(Amazon Bedrock / Amazon Textract / Amazon Athena ほか)": (
        "AWS Lambda + AI services<br>(Amazon Bedrock / Amazon Textract / Amazon Athena and others)"
    ),
    "AI サービス<br>(Amazon Bedrock / Amazon Rekognition<br>Amazon Athena / Amazon Comprehend)": (
        "AI services<br>(Amazon Bedrock / Amazon Rekognition<br>Amazon Athena / Amazon Comprehend)"
    ),
    "AI サービス<br>(Amazon Bedrock / Amazon Rekognition<br>Amazon Athena / Amazon Textract<br>Amazon Comprehend)": (
        "AI services<br>(Amazon Bedrock / Amazon Rekognition<br>Amazon Athena / Amazon Textract<br>Amazon Comprehend)"
    ),
    "AWS Amplify (Gen2)<br>Amazon Cognito / AWS AppSync<br>AWS Lambda / AI サービス": (
        "AWS Amplify (Gen2)<br>Amazon Cognito / AWS AppSync<br>AWS Lambda / AI services"
    ),
    "AWS Lambda<br>(VPC 外 / ARM64)": "AWS Lambda<br>(outside VPC / ARM64)",
    "Web ブラウザ": "Web browser",
    "Web ブラウザ<br>(ファイル管理 + 同期)": "Web browser<br>(file management + sync)",
    "Web ブラウザ<br>(AI ポータル)": "Web browser<br>(AI portal)",
    "Web ブラウザ<br>(ファイル管理)": "Web browser<br>(file management)",
    "NFS クライアント": "NFS client",
    "SMB クライアント": "SMB client",
    "SMB クライアント<br>(Windows)": "SMB client<br>(Windows)",
    "CloudTrail 監査ログ": "CloudTrail audit logs",
    "S3 Access Point の Internet origin はパブリック公開ではない": ("Internet origin does not mean public access"),
    "Block Public Access が常時有効（無効化不可）。全リクエストで IAM の認証と認可が必要": (
        "Block Public Access is always enabled and cannot be disabled; every request "
        "requires IAM authentication and authorization"
    ),
    "マルチプロトコルでの同時アクセス": "Concurrent multi-protocol access",
    "同一データに NFS / SMB / S3 API でアクセス可能。データ移行は不要": (
        "The same data stays reachable over NFS / SMB / S3 API at once, with no data migration"
    ),
    # ---- titles ---------------------------------------------------------------
    "群 A（ストレージエンドポイントを持つ移行元） — DataSync の 2 経路": (
        "Group A (sources with a storage endpoint) — the two DataSync routes"
    ),
    "群 B（コラボレーション SaaS） — 管理者 API を使う中央実行の構成": (
        "Group B (collaboration SaaS) — central execution via the admin API"
    ),
    "オブジェクトストレージ<br>(S3 互換 / Blob / GCS)": ("Object storage<br>(S3-compatible / Blob / GCS)"),
    "同じ移行元<br>(S3 互換 / Blob / GCS)": "The same source<br>(S3-compatible / Blob / GCS)",
    "AWS DataSync<br>(エージェント)": "AWS DataSync<br>(with agent)",
    "AWS DataSync<br>(エージェントレス)": "AWS DataSync<br>(agentless)",
    "Amazon S3<br>(一時保管)": "Amazon S3<br>(staging)",
    "経路 1:<br>直行": "Route 1:<br>direct",
    "経路 2:<br>S3 経由": "Route 2:<br>via S3",
    "Basic モード": "Basic mode",
    "Enhanced モード": "Enhanced mode",
    "エージェント不要": "No agent",
    "FSx for ONTAP 宛は常にエージェントと Basic モードが必要": (
        "An FSx for ONTAP destination always needs an agent and Basic mode"
    ),
    "エージェントレスの Enhanced モードは宛先が Amazon S3 のときだけ有効になる": (
        "Agentless Enhanced mode applies only when the destination is Amazon S3"
    ),
    "S3 を経由すると両区間がエージェントレスになる": ("Staging through S3 makes both legs agentless"),
    "代わりに S3 の一時保管費と 2 回分の転送を払う。容量と期間で有利不利が逆転する": (
        "In exchange you pay for S3 staging and transfer twice. Which wins flips with volume and duration"
    ),
    "コラボレーション SaaS はこの図の対象外": ("Collaboration SaaS is out of scope for this figure"),
    "Box / Dropbox / OneDrive / Google Drive は DataSync のソースにならない（群 B）": (
        "Box / Dropbox / OneDrive / Google Drive are not DataSync sources (group B)"
    ),
    "SaaS テナント<br>(Microsoft 365 / Box 等)": "SaaS tenant<br>(Microsoft 365 / Box, etc.)",
    "AWS Lambda<br>(移行ワーカー / VPC 内)": "AWS Lambda<br>(migration worker, in VPC)",
    "SaaS API<br>呼び出し": "SaaS API<br>calls",
    "テナント<br>管理者認可": "Tenant admin<br>grant",
    "対象の一覧化と分割": "Enumerate and fan out targets",
    "NFS / SMB<br>で書き込み": "Write over<br>NFS / SMB",
    "移行後の活用経路": "Post-migration access",
    "認可はテナント単位なので利用者ごとの同意は不要": (
        "Authorization is tenant-wide, so per-user consent is not required"
    ),
    "Graph の application permissions / ドメイン全体の委任 / as-user 等を用いる": (
        "Uses Graph application permissions, domain-wide delegation, as-user and similar"
    ),
    "書き込みは NFS / SMB を主経路にする": "Make NFS / SMB the primary write path",
    "S3 access point は 50 GiB を超えられず、ACL を書きながら投入できない": (
        "An S3 access point cannot exceed 50 GiB and cannot write ACLs during ingest"
    ),
    "進捗を外部に持たないと再開できない": ("Without externalised progress there is no resume"),
    "SaaS API のレート制限で必ず中断する。再開位置がなければ全件やり直しになる": (
        "SaaS API rate limits will interrupt it. With no resume point the whole set restarts"
    ),
    "移行用の権限は終了後に取り消す": "Revoke the migration permissions when finished",
    "テナント全体の読み取り権限を持つアプリ登録は、それ自体が高価値の標的になる": (
        "An app registration holding tenant-wide read permission is itself a high-value target"
    ),
    "ストレージ運用機能をポータルに組み込む — 管理操作の経路": (
        "Storage Operations in the Portal — Admin Operation Path"
    ),
    "ARP/AI インシデントライフサイクル — 4 状態での管理": ("ARP/AI Incident Lifecycle — Tracked as Four States"),
    "Audit Log — 「誰がいつ何にアクセスしたか」を UI で確認する経路": (
        "Audit Log — Answering Who Accessed What and When from the UI"
    ),
    "ブラウザから ONTAP REST API を操作する経路（VPC 内 Lambda）": (
        "Reaching the ONTAP REST API from the Browser (Lambda in the VPC)"
    ),
    "PoC から本番接続までの 3 フェーズ": ("Three Phases from PoC to Production Connectivity"),
    "ファイルポータルに AI エージェントを組み込む — 全体構成": (
        "Adding AI Agents to the File Portal — Overall Architecture"
    ),
    "AgentChat — 3 モードと MCP ツール経由のファイルアクセス": (
        "AgentChat — Three Modes and File Access via MCP Tools"
    ),
    "SemanticSearch — Bedrock Knowledge Bases によるベクトル検索": (
        "SemanticSearch — Vector Search with Bedrock Knowledge Bases"
    ),
    "Agent Teams — Supervisor が調整するマルチエージェント協調": (
        "Agent Teams — Multi-Agent Coordination Led by a Supervisor"
    ),
    # ---- node labels ----------------------------------------------------------
    "利用者（Web ブラウザ）": "Users (web browser)",
    "AWS Lambda<br>(VPC 内)": "AWS Lambda<br>(in VPC)",
    "Amazon S3<br>(CloudTrail ログ)": "Amazon S3<br>(CloudTrail logs)",
    "検知 (Detected)": "Detected",
    "封じ込め (Contained)": "Contained",
    "調査中 (Investigating)": "Investigating",
    "解決済み (Resolved)": "Resolved",
    "Phase 1: PoC<br>（約 15 分）": "Phase 1: PoC<br>(~15 min)",
    "Phase 2: VPC 接続追加<br>（約 30 分）": ("Phase 2: Add VPC connectivity<br>(~30 min)"),
    "Phase 3: 本番ハードニング<br>（約 60 分）": ("Phase 3: Production hardening<br>(~60 min)"),
    "DemoMode=true<br>S3 バケットで動作確認<br>認証: Amazon Cognito": (
        "DemoMode=true<br>Verify against an S3 bucket<br>Auth: Amazon Cognito"
    ),
    "ONTAP 管理 LIF へ接続<br>AWS Secrets Manager 登録<br>VPC エンドポイント追加": (
        "Connect to the ONTAP management LIF<br>Store credentials in AWS Secrets Manager<br>Add VPC endpoints"
    ),
    "IAM 最小権限化<br>MFA 必須化 / AWS WAF 追加<br>監査ログ有効化": (
        "Least-privilege IAM<br>Require MFA / add AWS WAF<br>Enable audit logs"
    ),
    "AWS Lambda<br>(エージェント実行)": "AWS Lambda<br>(agent execution)",
    "AWS Lambda<br>(MCP ツール)": "AWS Lambda<br>(MCP tools)",
    "mode=kb<br>セマンティック検索のみ": "mode=kb<br>Semantic search only",
    "mode=agent<br>ファイルツールのみ": "mode=agent<br>File tools only",
    "mode=multi<br>全ツールで協調": "mode=multi<br>All tools, coordinated",
    "利用者の指示<br>「engineering/ を分析して」": ("User request<br>&quot;Analyze engineering/&quot;"),
    "利用者への最終回答<br>要約 + フィルタリング結果": ("Final answer to the user<br>Summary + filtered results"),
    # ---- edge labels ----------------------------------------------------------
    "認証 /<br>グループ判定": "Auth / groups",
    "認証情報の取得": "Get<br>credentials",
    "封じ込め<br>実行": "Contain",
    "調査開始": "Investigate",
    "解決": "Resolve",
    "監査クエリ": "Audit query",
    "SQL 実行": "Run SQL",
    "テーブル定義を参照": "Read table<br>definition",
    "ログをスキャン": "Scan logs",
    "S3 データイベント<br>を記録": "Record S3 data<br>events",
    "Cognito 認証": "Cognito auth",
    "fsxadmin 認証情報": "fsxadmin credentials",
    "推論": "Inference",
    "Lambda<br>呼び出し": "Invoke Lambda",
    "チャット送信": "Send chat",
    "ツール呼び出し": "Tool call",
    "検索クエリ": "Search query",
    "ベクトル検索": "Vector search",
    "埋め込み生成": "Embeddings",
    "データソース同期": "Sync data source",
    "① 探索": "1.<br>Explore",
    "② 分析": "2.<br>Analyze",
    "③ 検証": "3.<br>Review",
    "④ 統合": "4.<br>Consolidate",
    # ---- notes ----------------------------------------------------------------
    "権限分離は Cognito Groups で行う": "Cognito Groups separate the privileges",
    "storage-admin グループのみが変更操作を実行でき、一般ユーザーは閲覧のみ": (
        "Only the storage-admin group can run change operations; everyone else is read-only"
    ),
    "不可逆操作は実行前に確認が必要": "Irreversible operations need a confirmation",
    "SnapLock Compliance の有効化と保持期間の短縮は取り消せない": (
        "Enabling SnapLock Compliance and shortening a retention period cannot be undone"
    ),
    "各状態で記録される情報": "What each state records",
    "検知=detectedAt / 封じ込め=containedAt・blockedUsers・blockedIps・snapshotName"
    " / 調査中=notes / 解決済み=resolvedAt": (
        "Detected=detectedAt / Contained=containedAt, blockedUsers, blockedIps, "
        "snapshotName / Investigating=notes / Resolved=resolvedAt"
    ),
    "現在の制約": "Current limitation",
    "状態は localStorage 保存でブラウザ間共有されない。本番では DynamoDB 永続化を推奨": (
        "State lives in localStorage and is not shared across browsers; persist it in DynamoDB for production"
    ),
    "前提条件": "Prerequisites",
    "S3 AP の ARN に対して CloudTrail のデータイベントを有効化し、"
    "Glue Crawler もしくは手動 CREATE TABLE で Athena テーブルを作成しておく": (
        "Enable CloudTrail data events on the S3 AP ARN, then create the Athena "
        "table with a Glue Crawler or a manual CREATE TABLE"
    ),
    "保持期間はバケット側で制御": "Retention is controlled on the bucket",
    "CloudTrail ログの保持は Trail のバケットのライフサイクルポリシーで設定する": (
        "Set CloudTrail log retention with the lifecycle policy on the trail bucket"
    ),
    "Lambda を VPC 内に置く理由": "Why this Lambda sits in the VPC",
    "ONTAP の管理 LIF はプライベート（TCP 443）。一方 S3 AP は Internet origin"
    " なので、1 つの Lambda で両方を兼用できない": (
        "The ONTAP management LIF is private (TCP 443) while the S3 AP is Internet "
        "origin, so one Lambda cannot serve both"
    ),
    "認証情報は必ず同時に更新する": "Update both credential stores together",
    "fsxadmin のパスワード変更時に FSx API と Secrets Manager の片方だけを"
    "更新すると認証失敗し、ONTAP 側のアカウントロックの契機になる": (
        "Changing the fsxadmin password in the FSx API but not in Secrets Manager "
        "(or the reverse) causes auth failures that can lock the ONTAP account"
    ),
    "追加コストの目安": "Rough added cost",
    "Phase 1 は 0 USD、Phase 2 で VPC Lambda 約 5 USD/月、Phase 3 で CloudTrail データイベント約 10〜50 USD/月": (
        "Phase 1 is 0 USD; Phase 2 adds roughly 5 USD/month for the VPC Lambda; "
        "Phase 3 adds roughly 10-50 USD/month for CloudTrail data events"
    ),
    "Phase をまたいでも変わらないもの": "What stays the same across phases",
    "フロントエンドの UI、Cognito の設定、アプリケーションコードは変更不要": (
        "The frontend UI, the Cognito configuration, and the application code need no changes"
    ),
    "破壊的操作は人間が承認してから実行": "A human approves destructive operations",
    "エージェントは提案までを担当し、実行は HITL の承認モーダルを経る": (
        "The agent stops at a proposal; execution goes through the HITL approval modal"
    ),
    "マルチエージェントが効く範囲": "Where multi-agent pays off",
    "「探索 → 分析 → 判定」の複数フェーズを持つタスクに限られ、単純な検索は単一エージェントの方が速い": (
        "Only for tasks with several phases (explore, analyze, decide); a single agent is faster for a plain search"
    ),
    "Gateway 経由の MCP ツールは 3 種": "Three MCP tools through the Gateway",
    "list_files / read_file / search_files。ツール名は targetName___toolName 形式で渡る": (
        "list_files / read_file / search_files. Tool names arrive as targetName___toolName"
    ),
    "Gateway と Lambda は同一リージョンに置く": ("Keep the Gateway and the Lambda in one Region"),
    "クロスリージョンの Lambda 呼び出しはできないため、Gateway・Lambda・S3 AP を同じリージョンに配置する": (
        "Cross-Region Lambda invocation is not available, so place the Gateway, the "
        "Lambda, and the S3 AP in the same Region"
    ),
    "検索結果に含まれるもの": "What a search result contains",
    "関連チャンク・ソースファイルパス・関連度スコア": (
        "The matching chunks, the source file paths, and a relevance score"
    ),
    "同期は自動ではない": "Syncing is not automatic",
    "ファイル追加後にデータソースの同期ジョブを実行するまで検索対象に入らない": (
        "A newly added file is not searchable until the data source sync job runs"
    ),
    "各ステップは Supervisor が仲介する": "The Supervisor brokers every step",
    "Collaborator 同士は直接やり取りせず、Supervisor が指示と結果を受け渡す": (
        "Collaborators never talk to each other directly; the Supervisor passes the instructions and the results"
    ),
    "利用者から見た体験": "What the user experiences",
    "1 回のチャット送信で複数フェーズが完了し、途中の往復は表に出ない": (
        "One chat message completes several phases, and the intermediate exchanges stay hidden"
    ),
}


def saas_group_a_routes() -> Diagram:
    """Group A: the source has a storage endpoint, so DataSync can carry it.

    The figure exists to make one asymmetry visible: an FSx for ONTAP destination
    always needs an agent, while an Amazon S3 destination does not. Staging
    through S3 therefore removes the agent from the picture at the price of a
    second pass, and that trade is the whole decision.
    """
    return Diagram(
        id="saas-migration-group-a-routes",
        name="SaaS Migration Group A Routes",
        title="群 A（ストレージエンドポイントを持つ移行元） — DataSync の 2 経路",
        grid=Grid(col_pitch=300),
        # One route per row, each starting from its own source box. Edges are drawn
        # with orthogonal routing, so a single source fanning out to both rows put
        # two labels on the same horizontal segment and hid one of them.
        nodes=[
            # Plain boxes, not icons: the source is another vendor's storage, and
            # every AWS icon would name a service this is not.
            Node("source_a", "オブジェクトストレージ<br>(S3 互換 / Blob / GCS)", 0, 0, BOX, fill=GREY, w=210),
            Node("agent", "AWS DataSync<br>(エージェント)", 1, 0, SERVICE, DATASYNC),
            Node("fsxn_direct", "Amazon FSx for<br>NetApp ONTAP", 2, 0, SERVICE, FSXN),
            Node("source_b", "同じ移行元<br>(S3 互換 / Blob / GCS)", 0, 1, BOX, fill=GREY, w=210),
            Node("agentless", "AWS DataSync<br>(エージェントレス)", 1, 1, SERVICE, DATASYNC),
            Node("s3", "Amazon S3<br>(一時保管)", 2, 1, SERVICE, S3),
            Node("fsxn_staged", "Amazon FSx for<br>NetApp ONTAP", 3, 1, SERVICE, FSXN),
        ],
        groups=[Group("aws-cloud", "AWS Cloud", (1, 3), (0, 1))],
        edges=[
            Edge("source_a", "agent", "経路 1:<br>直行"),
            Edge("agent", "fsxn_direct", "Basic モード"),
            Edge("source_b", "agentless", "経路 2:<br>S3 経由"),
            Edge("agentless", "s3", "Enhanced モード"),
            Edge("s3", "fsxn_staged", "エージェント不要"),
        ],
        notes=[
            (
                "FSx for ONTAP 宛は常にエージェントと Basic モードが必要",
                "エージェントレスの Enhanced モードは宛先が Amazon S3 のときだけ有効になる",
            ),
            (
                "S3 を経由すると両区間がエージェントレスになる",
                "代わりに S3 の一時保管費と 2 回分の転送を払う。容量と期間で有利不利が逆転する",
            ),
            (
                "コラボレーション SaaS はこの図の対象外",
                "Box / Dropbox / OneDrive / Google Drive は DataSync のソースにならない（群 B）",
            ),
        ],
    )


def saas_group_b_worker() -> Diagram:
    """Group B: no storage endpoint, so a worker drives the tenant admin API.

    The point of the figure is that this is one central pipeline, not a per-user
    setup: the credential at the left is a tenant-wide administrator grant, so an
    infrastructure team runs the whole migration without collecting consent from
    each user.
    """
    return Diagram(
        id="saas-migration-group-b-worker",
        name="SaaS Migration Group B Worker",
        title="群 B（コラボレーション SaaS） — 管理者 API を使う中央実行の構成",
        # Four columns at a tighter pitch, with the post-migration hop running
        # downwards. The chain used to occupy five columns at 300, and the long
        # horizontal labels on it demanded the width twice over: once for the pitch,
        # again for the larger label the wider canvas then required.
        grid=Grid(col_pitch=248),
        # Every edge joins adjacent or diagonal cells. An edge that spans an
        # occupied cell is drawn straight through it, which put a label on top of
        # the Amazon SQS icon in the first version of this figure.
        # The worker sits at the centre and every edge is orthogonal to an adjacent
        # cell, which caps it at four connections. Amazon DynamoDB was the fifth,
        # and a diagonal edge to it was routed straight through the Amazon FSx for
        # NetApp ONTAP cell. Its role — externalised progress, without which a
        # rate-limited run cannot resume — is carried by note 3 instead.
        nodes=[
            Node("saas", "SaaS テナント<br>(Microsoft 365 / Box 等)", 0, 1, BOX, fill=GREY, w=210),
            Node("natgw", "Amazon VPC<br>NAT Gateway", 1, 1, RESOURCE, NATGW),
            Node("secrets", "AWS Secrets Manager", 2, 0, SERVICE, SECRETS),
            Node("worker", "AWS Lambda<br>(移行ワーカー / VPC 内)", 2, 1, SERVICE, LAMBDA),
            Node("sfn", "AWS Step Functions", 2, 2, SERVICE, SFN),
            Node("fsxn", "Amazon FSx for<br>NetApp ONTAP", 3, 1, SERVICE, FSXN),
            # below the file system rather than beside it: the label on this hop is
            # long, and a vertical run does not have to fit it between two icons
            Node("s3ap", "Amazon S3 access point", 3, 2, RESOURCE, S3AP),
        ],
        groups=[Group("aws-cloud", "AWS Cloud", (1, 3), (0, 2))],
        edges=[
            Edge("worker", "natgw", "SaaS API<br>呼び出し"),
            Edge("natgw", "saas", "テナント<br>管理者認可"),
            Edge("secrets", "worker", "認証情報の取得"),
            Edge("sfn", "worker", "対象の一覧化と分割"),
            Edge("worker", "fsxn", "NFS / SMB<br>で書き込み"),
            Edge("fsxn", "s3ap", "移行後の活用経路"),
        ],
        notes=[
            (
                "認可はテナント単位なので利用者ごとの同意は不要",
                "Graph の application permissions / ドメイン全体の委任 / as-user 等を用いる",
            ),
            (
                "書き込みは NFS / SMB を主経路にする",
                "S3 access point は 50 GiB を超えられず、ACL を書きながら投入できない",
            ),
            (
                "進捗を外部に持たないと再開できない",
                "SaaS API のレート制限で必ず中断する。再開位置がなければ全件やり直しになる",
            ),
            (
                "移行用の権限は終了後に取り消す",
                "テナント全体の読み取り権限を持つアプリ登録は、それ自体が高価値の標的になる",
            ),
        ],
    )


DIAGRAMS = [
    part1_overview,
    part1_nextcloud,
    part1_amplify,
    part1_coexistence,
    saas_group_a_routes,
    saas_group_b_worker,
    part2_overview,
    part2_arp_lifecycle,
    part2_audit_log,
    part2_vpc_split,
    part2_poc_to_prod,
    part3_overview,
    part3_agentchat,
    part3_semantic_search,
    part3_agent_teams,
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--icon-root", required=True)
    args = ap.parse_args()
    root = Path(args.icon_root)
    if not root.is_dir():
        print(f"ERROR: --icon-root not a directory: {root}", file=sys.stderr)
        return 1

    icons = IconResolver(root)
    failed = False
    for factory in DIAGRAMS:
        d = factory()
        try:
            variants = [d, translate_diagram(d, EN)]
        except ValueError as exc:
            print(f"  {d.id}: FAILED -> {exc}", file=sys.stderr)
            failed = True
            continue
        for variant in variants:
            try:
                path = write(variant, icons, OUT_DIR)
                print(f"  {path.name}: {len(variant.nodes)} nodes, {len(variant.edges)} edges, XML OK")
            except Exception as exc:  # noqa: BLE001 - surface any spec error clearly
                print(f"  {variant.id}: FAILED -> {exc}", file=sys.stderr)
                failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
