#!/usr/bin/env python3
"""Build the Part 2 / Part 3 architecture diagrams from declarative specs.

Compliance (official icons, native sizes, service-name labels, single-colour Open
Arrow edges, ※-numbered notes) is enforced by scripts/diagram_builder.py, so these
specs only describe content and grid placement.

Both the Japanese and the English variant are emitted from the same spec (see the
EN dictionary below), so scripts/generate-en-diagrams.py — which substitutes strings
in the hand-authored Part 1 XML — is not involved here.

Usage (from repo root):
    python3 scripts/build-part2-part3-diagrams.py --icon-root /tmp/awsicons
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

# state / phase tints. These are plain boxes, not AWS icons, so the icon colour
# rules do not apply — the tint only aids scanning.
RED = "#FDEDEE"
ORANGE = "#FEF3E6"
YELLOW = "#FFFBE6"
GREEN = "#EDF6EC"
BLUE = "#EDF3FB"
GREY = "#F5F5F5"


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
            Node("secrets", "AWS Secrets Manager", 3, 3, SERVICE, SECRETS),
            Node("fsxn", "Amazon FSx for<br>NetApp ONTAP", 2, 4, SERVICE, FSXN),
        ],
        groups=[Group("aws-cloud", "AWS Cloud", (1, 3), (1, 4))],
        edges=[
            Edge("browser", "amplify", "HTTPS"),
            Edge("amplify", "cognito", "認証 / グループ判定"),
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
        grid=Grid(col_pitch=290),
        nodes=[
            Node("detected", "検知 (Detected)", 0, 0, BOX, fill=RED, stroke="#DD344C"),
            Node("contained", "封じ込め (Contained)", 1, 0, BOX, fill=ORANGE, stroke="#ED7100"),
            Node("investigating", "調査中 (Investigating)", 2, 0, BOX, fill=YELLOW, stroke="#B7950B"),
            Node("resolved", "解決済み (Resolved)", 3, 0, BOX, fill=GREEN, stroke="#3F8624"),
        ],
        edges=[
            Edge("detected", "contained", "封じ込め実行"),
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
        grid=Grid(col_pitch=250),
        nodes=[
            Node("browser", "利用者（Web ブラウザ）", 0, 0, RESOURCE, USERS),
            Node("appsync", "AWS AppSync", 1, 0, SERVICE, APPSYNC),
            Node("lambda", "AWS Lambda", 2, 0, SERVICE, LAMBDA),
            Node("athena", "Amazon Athena", 3, 0, SERVICE, ATHENA),
            Node("glue", "AWS Glue<br>(Data Catalog)", 3, 1, SERVICE, GLUE),
            Node("s3logs", "Amazon S3<br>(CloudTrail ログ)", 4, 0, SERVICE, S3),
            # same row as the bucket, so the connector stays a straight horizontal
            # run and never crosses the bucket's label
            Node("cloudtrail", "AWS CloudTrail", 5, 0, SERVICE, CLOUDTRAIL),
        ],
        groups=[Group("aws-cloud", "AWS Cloud", (1, 5), (0, 1))],
        edges=[
            Edge("browser", "appsync", "監査クエリ"),
            Edge("appsync", "lambda"),
            Edge("lambda", "athena", "SQL 実行"),
            Edge("athena", "glue", "テーブル定義を参照"),
            Edge("athena", "s3logs", "ログをスキャン"),
            Edge("cloudtrail", "s3logs", "S3 データイベントを記録"),
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
            Edge("agentcore", "mcp", "Lambda 呼び出し"),
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
                "「探索 → 分析 → 判定」の複数フェーズを持つタスクに限られ、"
                "単純な検索は単一エージェントの方が速い",
            ),
        ],
    )


def part3_agentchat() -> Diagram:
    return Diagram(
        id="part3-agentchat-modes",
        name="Part3 AgentChat Modes",
        title="AgentChat — 3 モードと MCP ツール経由のファイルアクセス",
        grid=Grid(col_pitch=250),
        nodes=[
            Node("browser", "利用者（Web ブラウザ）", 0, 1, RESOURCE, USERS),
            Node("appsync", "AWS AppSync", 1, 1, SERVICE, APPSYNC),
            Node("agent", "AWS Lambda<br>(AgentChat)", 2, 1, SERVICE, LAMBDA),
            # mode names follow the handler: TOOLS_BY_MODE = {multi, kb, agent}.
            # kb is limited to the kb_search tool, agent to the file tools.
            Node("m_kb", "mode=kb<br>セマンティック検索のみ", 3, 0, BOX, fill=GREY),
            Node("m_agent", "mode=agent<br>ファイルツールのみ", 3, 1, BOX, fill=GREY),
            Node("m_multi", "mode=multi<br>全ツールで協調", 3, 2, BOX, fill=GREY),
            Node("kb", "Amazon Bedrock<br>(Knowledge Bases)", 4, 0, SERVICE, BEDROCK),
            Node("bedrock", "Amazon Bedrock", 4, 1, SERVICE, BEDROCK),
            Node("agentcore", "Amazon Bedrock<br>AgentCore", 5, 1, SERVICE, AGENTCORE),
            # MCP tool Lambda and the S3 AP share column 6 so their connector does
            # not run straight through the AgentCore icon in column 5
            Node("mcp", "AWS Lambda<br>(MCP ツール)", 6, 1, SERVICE, LAMBDA),
            Node("s3ap", "Amazon S3 Access Point", 6, 0, RESOURCE, S3AP),
        ],
        groups=[Group("aws-cloud", "AWS Cloud", (1, 6), (0, 2))],
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
                "list_files / read_file / search_files。ツール名は "
                "targetName___toolName 形式で渡る",
            ),
            (
                "Gateway と Lambda は同一リージョンに置く",
                "クロスリージョンの Lambda 呼び出しはできないため、"
                "Gateway・Lambda・S3 AP を同じリージョンに配置する",
            ),
        ],
    )


def part3_semantic_search() -> Diagram:
    return Diagram(
        id="part3-semantic-search",
        name="Part3 Semantic Search",
        title="SemanticSearch — Bedrock Knowledge Bases によるベクトル検索",
        grid=Grid(col_pitch=250),
        nodes=[
            Node("browser", "利用者（Web ブラウザ）", 0, 0, RESOURCE, USERS),
            Node("appsync", "AWS AppSync", 1, 0, SERVICE, APPSYNC),
            Node("lambda", "AWS Lambda", 2, 0, SERVICE, LAMBDA),
            Node("kb", "Amazon Bedrock<br>(Knowledge Bases)", 3, 0, SERVICE, BEDROCK),
            Node("oss", "Amazon OpenSearch<br>Service", 4, 0, SERVICE, OPENSEARCH),
            # directly under Knowledge Bases, so its edge label does not land on the
            # OpenSearch edge label
            Node(
                "embed",
                "Amazon Bedrock<br>(Titan Text Embeddings V2)",
                3,
                1,
                SERVICE,
                BEDROCK,
            ),
            Node("s3ap", "Amazon S3 Access Point", 2, 2, RESOURCE, S3AP),
            Node("fsxn", "Amazon FSx for<br>NetApp ONTAP", 1, 2, SERVICE, FSXN),
        ],
        groups=[Group("aws-cloud", "AWS Cloud", (1, 4), (0, 2))],
        edges=[
            Edge("browser", "appsync", "検索クエリ"),
            Edge("appsync", "lambda"),
            Edge("lambda", "kb", "RetrieveAndGenerate"),
            Edge("kb", "oss", "ベクトル検索"),
            # clearance from the two-line Knowledge Bases label is applied
            # automatically (see vertical_label_shortfall)
            Edge("kb", "embed", "埋め込み生成"),
            # land on the vertical run, right of the line, clear of the Lambda label
            Edge("kb", "s3ap", "データソース同期", at=0.5, dx=85),
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
        # 290 keeps a >=100px gap between boxes, which the longest English step
        # label ("4. Consolidate") needs; the Japanese labels are narrower
        grid=Grid(col_pitch=290, box_w=180),
        nodes=[
            Node("user", "利用者の指示<br>「engineering/ を分析して」", 0, 0, BOX, fill=GREY, h=80),
            Node("supervisor", "Supervisor<br>safety-controller", 1, 0, BOX, fill=BLUE, stroke="#2E73B8"),
            Node("explorer", "Collaborator<br>file-explorer", 2, 0, BOX, fill=GREEN, stroke="#3F8624"),
            Node("analyst", "Collaborator<br>knowledge-analyst", 3, 0, BOX, fill=GREEN, stroke="#3F8624"),
            Node("auditor", "Reviewer<br>compliance-auditor", 4, 0, BOX, fill=ORANGE, stroke="#ED7100"),
            Node("answer", "利用者への最終回答<br>要約 + フィルタリング結果", 5, 0, BOX, fill=GREY, h=80),
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
    # ---- titles ---------------------------------------------------------------
    "ストレージ運用機能をポータルに組み込む — 管理操作の経路": (
        "Storage Operations in the Portal — Admin Operation Path"
    ),
    "ARP/AI インシデントライフサイクル — 4 状態での管理": (
        "ARP/AI Incident Lifecycle — Tracked as Four States"
    ),
    "Audit Log — 「誰がいつ何にアクセスしたか」を UI で確認する経路": (
        "Audit Log — Answering Who Accessed What and When from the UI"
    ),
    "ブラウザから ONTAP REST API を操作する経路（VPC 内 Lambda）": (
        "Reaching the ONTAP REST API from the Browser (Lambda in the VPC)"
    ),
    "PoC から本番接続までの 3 フェーズ": (
        "Three Phases from PoC to Production Connectivity"
    ),
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
    "Phase 2: VPC 接続追加<br>（約 30 分）": (
        "Phase 2: Add VPC connectivity<br>(~30 min)"
    ),
    "Phase 3: 本番ハードニング<br>（約 60 分）": (
        "Phase 3: Production hardening<br>(~60 min)"
    ),
    "DemoMode=true<br>S3 バケットで動作確認<br>認証: Amazon Cognito": (
        "DemoMode=true<br>Verify against an S3 bucket<br>Auth: Amazon Cognito"
    ),
    "ONTAP 管理 LIF へ接続<br>AWS Secrets Manager 登録<br>VPC エンドポイント追加": (
        "Connect to the ONTAP management LIF<br>Store credentials in AWS Secrets "
        "Manager<br>Add VPC endpoints"
    ),
    "IAM 最小権限化<br>MFA 必須化 / AWS WAF 追加<br>監査ログ有効化": (
        "Least-privilege IAM<br>Require MFA / add AWS WAF<br>Enable audit logs"
    ),
    "AWS Lambda<br>(エージェント実行)": "AWS Lambda<br>(agent execution)",
    "AWS Lambda<br>(MCP ツール)": "AWS Lambda<br>(MCP tools)",
    "mode=kb<br>セマンティック検索のみ": "mode=kb<br>Semantic search only",
    "mode=agent<br>ファイルツールのみ": "mode=agent<br>File tools only",
    "mode=multi<br>全ツールで協調": "mode=multi<br>All tools, coordinated",
    "利用者の指示<br>「engineering/ を分析して」": (
        "User request<br>&quot;Analyze engineering/&quot;"
    ),
    "利用者への最終回答<br>要約 + フィルタリング結果": (
        "Final answer to the user<br>Summary + filtered results"
    ),
    # ---- edge labels ----------------------------------------------------------
    "認証 / グループ判定": "Auth / groups",
    "認証情報の取得": "Get credentials",
    "封じ込め実行": "Contain",
    "調査開始": "Investigate",
    "解決": "Resolve",
    "監査クエリ": "Audit query",
    "SQL 実行": "Run SQL",
    "テーブル定義を参照": "Read table definition",
    "ログをスキャン": "Scan logs",
    "S3 データイベントを記録": "Record S3 data events",
    "Cognito 認証": "Cognito auth",
    "fsxadmin 認証情報": "fsxadmin credentials",
    "推論": "Inference",
    "Lambda 呼び出し": "Invoke Lambda",
    "チャット送信": "Send chat",
    "ツール呼び出し": "Tool call",
    "検索クエリ": "Search query",
    "ベクトル検索": "Vector search",
    "埋め込み生成": "Embeddings",
    "データソース同期": "Sync data source",
    "① 探索": "1. Explore",
    "② 分析": "2. Analyze",
    "③ 検証": "3. Review",
    "④ 統合": "4. Consolidate",
    # ---- notes ----------------------------------------------------------------
    "権限分離は Cognito Groups で行う": "Cognito Groups separate the privileges",
    "storage-admin グループのみが変更操作を実行でき、一般ユーザーは閲覧のみ": (
        "Only the storage-admin group can run change operations; everyone else is "
        "read-only"
    ),
    "不可逆操作は実行前に確認が必要": "Irreversible operations need a confirmation",
    "SnapLock Compliance の有効化と保持期間の短縮は取り消せない": (
        "Enabling SnapLock Compliance and shortening a retention period cannot be "
        "undone"
    ),
    "各状態で記録される情報": "What each state records",
    "検知=detectedAt / 封じ込め=containedAt・blockedUsers・blockedIps・snapshotName"
    " / 調査中=notes / 解決済み=resolvedAt": (
        "Detected=detectedAt / Contained=containedAt, blockedUsers, blockedIps, "
        "snapshotName / Investigating=notes / Resolved=resolvedAt"
    ),
    "現在の制約": "Current limitation",
    "状態は localStorage 保存でブラウザ間共有されない。本番では DynamoDB 永続化を推奨": (
        "State lives in localStorage and is not shared across browsers; persist it "
        "in DynamoDB for production"
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
    "Phase 1 は 0 USD、Phase 2 で VPC Lambda 約 5 USD/月、"
    "Phase 3 で CloudTrail データイベント約 10〜50 USD/月": (
        "Phase 1 is 0 USD; Phase 2 adds roughly 5 USD/month for the VPC Lambda; "
        "Phase 3 adds roughly 10-50 USD/month for CloudTrail data events"
    ),
    "Phase をまたいでも変わらないもの": "What stays the same across phases",
    "フロントエンドの UI、Cognito の設定、アプリケーションコードは変更不要": (
        "The frontend UI, the Cognito configuration, and the application code need "
        "no changes"
    ),
    "破壊的操作は人間が承認してから実行": "A human approves destructive operations",
    "エージェントは提案までを担当し、実行は HITL の承認モーダルを経る": (
        "The agent stops at a proposal; execution goes through the HITL approval "
        "modal"
    ),
    "マルチエージェントが効く範囲": "Where multi-agent pays off",
    "「探索 → 分析 → 判定」の複数フェーズを持つタスクに限られ、"
    "単純な検索は単一エージェントの方が速い": (
        "Only for tasks with several phases (explore, analyze, decide); a single "
        "agent is faster for a plain search"
    ),
    "Gateway 経由の MCP ツールは 3 種": "Three MCP tools through the Gateway",
    "list_files / read_file / search_files。ツール名は "
    "targetName___toolName 形式で渡る": (
        "list_files / read_file / search_files. Tool names arrive as "
        "targetName___toolName"
    ),
    "Gateway と Lambda は同一リージョンに置く": (
        "Keep the Gateway and the Lambda in one Region"
    ),
    "クロスリージョンの Lambda 呼び出しはできないため、"
    "Gateway・Lambda・S3 AP を同じリージョンに配置する": (
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
        "Collaborators never talk to each other directly; the Supervisor passes the "
        "instructions and the results"
    ),
    "利用者から見た体験": "What the user experiences",
    "1 回のチャット送信で複数フェーズが完了し、途中の往復は表に出ない": (
        "One chat message completes several phases, and the intermediate exchanges "
        "stay hidden"
    ),
}


DIAGRAMS = [
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
                print(
                    f"  {path.name}: {len(variant.nodes)} nodes, "
                    f"{len(variant.edges)} edges, XML OK"
                )
            except Exception as exc:  # noqa: BLE001 - surface any spec error clearly
                print(f"  {variant.id}: FAILED -> {exc}", file=sys.stderr)
                failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
