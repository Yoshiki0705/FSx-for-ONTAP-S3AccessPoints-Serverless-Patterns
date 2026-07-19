# AgentCore MCP Gateway — ツール定義リファレンス

> **Workshop**: [Deploy AgentCore Gateway (Module 09)](https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/09-agentcore)
>
> **関連パターン**: [UC30 quick-agentic-workspace](../solutions/genai/quick-agentic-workspace/README.md)

本ドキュメントでは、Amazon Bedrock AgentCore MCP Gateway 経由で Amazon Quick Suite に公開する MCP ツール（Lambda 関数）の仕様を定義します。これにより Quick のエージェントが FSx for ONTAP 上の EDA ログをリアルタイムに読み取り、マルチステップ推論を実行できます。

---

## アーキテクチャ

```
Amazon Quick Suite
    ↓ (MCP Protocol)
AgentCore MCP Gateway
    ↓ (Lambda Invoke)
MCP Tools Lambda (S3 AP operations)
    ↓ (S3 API)
FSx for ONTAP S3 Access Point
    ↓
FSx for ONTAP Volume (NFS/SMB 同一データ)
```

### 認証フロー

```
Quick Suite User → Cognito User Pool (OAuth 2.0) → AgentCore Gateway → Lambda
```

---

## MCP ツール一覧

| ツール名 | 操作 | 説明 |
|---------|------|------|
| `list_files` | ListObjectsV2 | ディレクトリ内のファイル一覧を取得 |
| `read_file` | GetObject | 特定ファイルの内容を読み取り |
| `search_files` | ListObjectsV2 + フィルタ | パターンマッチでファイルを検索 |

---

## ツール定義（MCP JSON Schema）

### 1. list_files

ディレクトリ構造をブラウズし、指定パス配下のファイルとサブディレクトリを一覧表示します。

```json
{
  "name": "list_files",
  "description": "List files and directories at the specified path on FSx for ONTAP via S3 Access Point",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Directory path to list (e.g., 'eda-regression/simulation/' or ''  for root)",
        "default": ""
      },
      "max_results": {
        "type": "integer",
        "description": "Maximum number of results to return",
        "default": 100,
        "minimum": 1,
        "maximum": 1000
      },
      "file_extension": {
        "type": "string",
        "description": "Filter by file extension (e.g., '.log', '.csv')",
        "default": ""
      }
    },
    "required": []
  }
}
```

**Lambda 実装ロジック**:

```python
import boto3

def list_files(event):
    """S3 AP 経由で FSx for ONTAP ボリュームのファイルを一覧取得"""
    s3 = boto3.client("s3")
    ap_alias = os.environ["S3_AP_ALIAS"]
    prefix = event.get("path", "")
    max_results = event.get("max_results", 100)
    file_extension = event.get("file_extension", "")

    response = s3.list_objects_v2(
        Bucket=ap_alias,
        Prefix=prefix,
        MaxKeys=max_results,
    )

    files = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        if file_extension and not key.endswith(file_extension):
            continue
        files.append({
            "path": key,
            "size": obj["Size"],
            "last_modified": obj["LastModified"].isoformat(),
        })

    return {
        "files": files,
        "count": len(files),
        "truncated": response.get("IsTruncated", False),
    }
```

---

### 2. read_file

指定ファイルの内容を読み取ります。テキストファイル（ログ、CSV）を対象とし、エージェントがファイル内容を解析してユーザーの質問に回答します。

```json
{
  "name": "read_file",
  "description": "Read the content of a specific file from FSx for ONTAP via S3 Access Point",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Full path to the file (e.g., 'eda-regression/simulation/JOB_00001_sim.log')"
      },
      "max_bytes": {
        "type": "integer",
        "description": "Maximum bytes to read (truncate large files)",
        "default": 65536,
        "minimum": 1,
        "maximum": 1048576
      },
      "encoding": {
        "type": "string",
        "description": "Text encoding",
        "default": "utf-8",
        "enum": ["utf-8", "ascii", "latin-1"]
      }
    },
    "required": ["path"]
  }
}
```

**Lambda 実装ロジック**:

```python
def read_file(event):
    """S3 AP 経由でファイル内容を読み取り"""
    s3 = boto3.client("s3")
    ap_alias = os.environ["S3_AP_ALIAS"]
    path = event["path"]
    max_bytes = event.get("max_bytes", 65536)
    encoding = event.get("encoding", "utf-8")

    response = s3.get_object(
        Bucket=ap_alias,
        Key=path,
        Range=f"bytes=0-{max_bytes - 1}",
    )

    content = response["Body"].read().decode(encoding, errors="replace")
    content_length = response["ContentLength"]

    return {
        "path": path,
        "content": content,
        "size": content_length,
        "truncated": content_length > max_bytes,
        "content_type": response.get("ContentType", "text/plain"),
    }
```

---

### 3. search_files

パターンマッチングで関連ファイルを検索します。**ファイル名（パス）に対する**プレフィックスベースの検索に加え、正規表現によるフィルタリングを行います。ファイル内容の全文検索ではない点に注意してください（内容を確認するには `include_content_preview` を有効にするか、ヒットしたファイルを `read_file` で読み取ってください）。

```json
{
  "name": "search_files",
  "description": "Search for files matching a pattern on FSx for ONTAP via S3 Access Point",
  "inputSchema": {
    "type": "object",
    "properties": {
      "pattern": {
        "type": "string",
        "description": "Search pattern — applied to file paths (e.g., 'UVM_FATAL', 'cpu_core', 'JOB_001')"
      },
      "path": {
        "type": "string",
        "description": "Directory to search within",
        "default": ""
      },
      "file_extension": {
        "type": "string",
        "description": "Filter by extension (e.g., '.log')",
        "default": ""
      },
      "max_results": {
        "type": "integer",
        "description": "Maximum matching files to return",
        "default": 20,
        "minimum": 1,
        "maximum": 100
      },
      "include_content_preview": {
        "type": "boolean",
        "description": "Include first 1KB of each matching file",
        "default": false
      }
    },
    "required": ["pattern"]
  }
}
```

**Lambda 実装ロジック**:

```python
import re

def search_files(event):
    """パターンに一致するファイルを検索"""
    s3 = boto3.client("s3")
    ap_alias = os.environ["S3_AP_ALIAS"]
    pattern = event["pattern"]
    prefix = event.get("path", "")
    file_extension = event.get("file_extension", "")
    max_results = event.get("max_results", 20)
    include_preview = event.get("include_content_preview", False)

    # List all files under prefix
    paginator = s3.get_paginator("list_objects_v2")
    matches = []

    for page in paginator.paginate(Bucket=ap_alias, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if file_extension and not key.endswith(file_extension):
                continue
            if re.search(pattern, key, re.IGNORECASE):
                match = {
                    "path": key,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
                if include_preview:
                    try:
                        resp = s3.get_object(
                            Bucket=ap_alias, Key=key, Range="bytes=0-1023"
                        )
                        match["preview"] = resp["Body"].read().decode(
                            "utf-8", errors="replace"
                        )
                    except Exception:
                        match["preview"] = "(read error)"
                matches.append(match)
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    return {
        "pattern": pattern,
        "matches": matches,
        "count": len(matches),
    }
```

---

## Lambda 関数構成

### 環境変数

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `S3_AP_ALIAS` | FSx for ONTAP S3 AP Alias | `my-ap-xxxxx-ext-s3alias` |
| `AWS_REGION` | リージョン | `ap-northeast-1` |

### IAM ポリシー

```yaml
Policies:
  - Statement:
      - Sid: S3AccessPointRead
        Effect: Allow
        Action:
          - s3:GetObject
          - s3:ListBucket
          - s3:GetBucketLocation
        Resource:
          - !Sub "arn:aws:s3:::${S3AccessPointAlias}"
          - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"
          - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}"
          - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}/object/*"
```

### Lambda 設定

| 項目 | 値 |
|------|-----|
| Runtime | Python 3.12 |
| Architecture | arm64 |
| Memory | 256 MB |
| Timeout | 30 sec |
| VPC | 不要（Internet-origin S3 AP） |

---

## AgentCore MCP Gateway 構成

### Cognito User Pool

```yaml
CognitoUserPool:
  Type: AWS::Cognito::UserPool
  Properties:
    UserPoolName: !Sub "${AWS::StackName}-agentcore-pool"
    AutoVerifiedAttributes:
      - email
    Schema:
      - Name: email
        Required: true
        Mutable: true

CognitoUserPoolClient:
  Type: AWS::Cognito::UserPoolClient
  Properties:
    UserPoolId: !Ref CognitoUserPool
    ClientName: !Sub "${AWS::StackName}-agentcore-client"
    GenerateSecret: true
    AllowedOAuthFlows:
      - client_credentials
    AllowedOAuthScopes:
      - "agentcore/read"
    AllowedOAuthFlowsUserPoolClient: true
```

### AgentCore MCP Gateway 登録

AgentCore MCP Gateway の作成は AWS CLI で行います:

```bash
# 1. Gateway 作成（NONE 認証 — PoC 用）
aws bedrock-agentcore-control create-gateway \
  --gateway-name "eda-mcp-noauth" \
  --protocol-type MCP \
  --authorizer-type NONE \
  --region us-east-1

# 2. Lambda ターゲット登録（ツールスキーマ付き）
aws bedrock-agentcore-control create-target \
  --gateway-identifier <gateway-id> \
  --name "eda-log-tools" \
  --target-configuration '{
    "lambdaTarget": {
      "lambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:agentcore-mcp-eda-tools",
      "toolSchema": {
        "tools": [
          {"name": "list_files", "description": "List files on FSx for ONTAP via S3 AP", ...},
          {"name": "read_file", "description": "Read file content via S3 AP", ...},
          {"name": "search_files", "description": "Search files by pattern via S3 AP", ...}
        ]
      }
    }
  }' \
  --region us-east-1

# 3. 動作確認
curl -s https://<gateway-id>.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | jq '.result.tools | length'
# → 3
```

> **注意**: `aws bedrock-agent create-agent` は Bedrock Agent（会話型エージェント）用の API であり、MCP Gateway とは異なります。MCP Gateway は `bedrock-agentcore-control` 名前空間の API を使用してください。

---

## Knowledge Base vs AgentCore — 選択基準

| 基準 | Knowledge Base (Quick Index) | AgentCore (MCP) |
|------|------------------------------|-----------------|
| データ鮮度 | 同期間隔に依存（分〜時間） | 常に最新（リアルタイム読み取り） |
| クエリの柔軟性 | ベクトル検索（セマンティック） | ファイル操作（browse/read/search） |
| マルチステップ推論 | 限定的（1 回の検索） | 可能（複数ファイルを順次読み取り） |
| セットアップ | コンソールで数クリック | Cognito + Lambda + Gateway |
| コスト | KB ストレージ + 同期 | Lambda 実行のみ（従量） |
| 適するユースケース | FAQ、ドキュメント検索、定型 Q&A | ログ分析、相関調査、トリアージ |

### 推奨アプローチ

- **まず Knowledge Base** で Quick Index を設定し、基本的な Q&A を確認
- **追加で AgentCore** を導入し、リアルタイムのログ横断分析を有効化
- 両方を共存させることで、最適なアプローチが自動選択される

---

## 同一 Gateway に追加可能な MCP サーバー

本構成（EDA Log Analyzer）に加えて、AgentCore Gateway に以下の MCP サーバーを追加登録し、Quick から横断的に活用できます:

| カテゴリ | MCP サーバー | できること |
|---------|-------------|----------|
| **AWS API** | [AWS MCP Server](https://awslabs.github.io/mcp/) | 15,000+ AWS API 実行 + ドキュメント検索 (122 tools) |
| **SAP** | AWS for SAP MCP Server | SAP BTP / S/4HANA データアクセス |
| **Web Search** | AgentCore Web Search (Built-in connector) | リアルタイム Web 検索、引用付き |
| **GitHub** | GitHub MCP Server | PR 管理、Issue 検索、Code Search、Copilot AI |
| **Jira** | Atlassian Jira Cloud | Issue 作成・更新 (29 アクション) |
| **Slack** | Slack MCP Server | メッセージ送信、チャネル管理 |
| **Salesforce** | Salesforce MCP Server | CRM レコード操作 (42 アクション) |
| **ServiceNow** | ServiceNow NOW Platform | インシデント管理 (26 アクション) |
| **Snowflake** | Snowflake Cortex Agent | データウェアハウスクエリ |
| **Custom Lambda** | **本構成（EDA Log Analyzer）** | FSx for ONTAP S3 AP 上のファイル操作 |

> **活用例**: 「EDA ログで UVM_FATAL を含むジョブを検索して、失敗原因のサマリーを Jira チケットとして作成して」— 複数 MCP サーバーを組み合わせたマルチステップ操作。

---

## パフォーマンスとスループット考慮事項

> **Storage note**: S3 AP アクセスは NFS/SMB と同じ FSx for ONTAP スループットバジェットを共有します。

| 項目 | 影響 | 対策 |
|------|------|------|
| `search_files` の全件列挙 | 数万〜数百万ファイルのボリュームではタイムアウト（30s）のリスク | `path` を必ず指定して探索範囲を限定。`max_results` のデフォルト 20 を超えないことを推奨 |
| `read_file` の Range GET (max 1MB) | 複数ファイルの連続読み取りで瞬間的にスループットを消費 | バースト利用に留め、バッチ的な大量読み取りは EventBridge + Step Functions パターンへ |
| `include_content_preview` + 大量ヒット | 1KB × N 件の GetObject が発生（N=100 で 100 リクエスト） | `max_results` を 20 以下に設定し、必要なファイルのみ `read_file` で個別読み取り |
| NFS/SMB ワークロードとの帯域共有 | EDA シミュレーション実行中は S3 AP レイテンシが増加する可能性 | 重い MCP 分析は業務時間外に実行、または FlexCache で読み取り負荷を分離 |

**推奨**: FSx for ONTAP のスループット容量（128 MBps〜）に対して、MCP ツールの読み取りは微量（1 リクエストあたり KB〜MB 単位）です。通常利用では問題になりませんが、大量ファイルの連続処理を行う場合は CloudWatch の `ThroughputUtilization` メトリクスを確認してください。

---

## ガバナンスとセキュリティ

> **Security note**: 本構成は PoC 向けです。本番環境では以下の対策を実施してください。

### 認証・認可

| レイヤー | PoC 構成 | 本番推奨 |
|---------|---------|---------|
| Gateway | NONE（認証なし） | CUSTOM_JWT + Authorization Policy |
| Lambda | IAM Role（S3 読み取りのみ） | 追加: IP 制限、リソースポリシー |
| S3 AP | File System Identity（UNIX/Windows） | 最小権限の UID/GID 設定 |

### 監査ログ

MCP ツール呼び出しは以下で追跡可能です:

- **CloudTrail**: S3 AP 経由の GetObject / ListObjectsV2 は CloudTrail データイベントとして記録
- **Lambda CloudWatch Logs**: 各ツール呼び出しのパラメータ（path, pattern）が構造化ログに出力
- **AgentCore Gateway ログ**: Gateway のアクセスログで呼び出し元を追跡

### データリージョンに関する注意

本 PoC では Lambda を **us-east-1**（AgentCore Gateway と同一リージョン）にデプロイし、**ap-northeast-1** の FSx for ONTAP S3 AP にアクセスします。ファイル内容がリージョン間を転送されます。

- **PoC / 非機密データ**: 問題なし（S3 AP は Internet-origin で任意リージョンからアクセス可能）
- **機密データ / コンプライアンス要件あり**: AgentCore Gateway が ap-northeast-1 で利用可能になるまで待つか、VPC Peering + PrivateLink 構成を検討

### 入力バリデーション

Lambda ハンドラーでは以下の防御を実装してください:

```python
import os

def validate_path(path: str) -> str:
    """パストラバーサル防止"""
    normalized = os.path.normpath(path)
    if normalized.startswith("..") or normalized.startswith("/"):
        raise ValueError(f"Invalid path: {path}")
    return normalized
```

---

## 関連ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [Workshop EDA 統合ガイド](workshop-eda-integration.md) | Workshop モジュールと UC パターンの対応 |
| [UC30 README](../solutions/genai/quick-agentic-workspace/README.md) | Quick Suite 全機能統合パターン |
| [AgentCore Web Search 統合](investigations/agentcore-web-search-fsxn-integration.md) | Web Search Tool 統合の詳細 |
| [AD-Joined SVM Prerequisites](en/ad-joined-svm-s3ap-prerequisites.md) | AD 構成の前提条件 |
| [S3AP Compatibility Notes](s3ap-compatibility-notes.md) | S3 AP の制約と回避策 |
