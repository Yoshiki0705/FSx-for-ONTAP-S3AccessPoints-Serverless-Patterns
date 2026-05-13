# FPolicy External Server デプロイアーキテクチャ検討

**Phase 10 追加 — ECS Fargate vs EC2 比較評価**

## 背景

ONTAP FPolicy External Server は、FSxN SVM からの TCP 接続を受け付ける長時間稼働サーバーである。
ONTAP が接続を**開始する側**であり、FPolicy Server は TCP ポートでリッスンするだけ。
NFS/SMB マウントは一切不要。

### FPolicy 通信フロー（NetApp ドキュメントより）

> "Every node that participates on each SVM **initiates a connection** to an external
> FPolicy server using TCP/IP. Connections to the FPolicy servers are set up using
> **node data LIFs**."
>
> — [Node-to-external ONTAP FPolicy server communication process](https://docs.netapp.com/us-en/ontap/nas-audit/node-fpolicy-server-communication-process-concept.html)

```
FSxN SVM (data LIF, Private Subnet)
  │
  │ TCP connect (port 9898, async mode)
  ▼
FPolicy External Server (リッスンするだけ)
  │
  │ SQS SendMessage
  ▼
SQS Ingestion Queue → EventBridge → Step Functions
```

## 要件

| 要件 | 説明 | 重要度 |
|------|------|--------|
| TCP リッスン | ポート 9898 で ONTAP からの接続を受け付ける | 必須 |
| 同一 VPC | FSxN SVM data LIF と同一 VPC 内に配置 | 必須 |
| IP 安定性 | ONTAP external-engine の `-primary-servers` に指定する IP が安定 | 必須 |
| 高可用性 | サーバー障害時に自動復旧 | 推奨 |
| スケーラビリティ | 複数 SVM / 大量イベント対応 | 推奨 |
| 運用負荷 | パッチ適用、OS 管理の最小化 | 推奨 |
| コスト | 月額ランニングコスト | 考慮 |
| NFS マウント | **不要**（FPolicy は TCP 通知のみ） | N/A |

## アーキテクチャ比較

### Option A: ECS Fargate + NLB（推奨）

```
FSxN SVM (data LIF)
  │
  │ TCP connect to NLB static IP (port 9898)
  ▼
NLB (Network Load Balancer)
  │ TCP passthrough, health check
  │ Static IP per AZ
  ▼
ECS Fargate Service (desired_count=1, min=1, max=3)
  │ awsvpc network mode
  │ Private Subnet (same as FSxN)
  ▼
fpolicy-server container (port 9898)
  │
  │ boto3 → SQS SendMessage
  ▼
SQS Ingestion Queue
```

**メリット:**
- サーバーレス運用（OS パッチ不要）
- NLB の静的 IP で ONTAP external-engine 設定が安定
- ヘルスチェックによる自動復旧
- Auto Scaling 対応（イベント量に応じてタスク数調整）
- Fargate Spot で最大 70% コスト削減可能

**デメリット:**
- NLB コスト（~$16/月 + データ処理料金）
- Fargate タスク再起動時に一時的な接続断（NLB が自動リカバリ）
- ONTAP は接続断を検知後、keep-alive タイムアウト（デフォルト 2 分）で再接続

**コスト見積もり（東京リージョン）:**
| リソース | 月額 |
|----------|------|
| NLB 固定料金 | ~$16.20 |
| NLB データ処理 (1GB/月想定) | ~$0.01 |
| Fargate (0.25 vCPU, 0.5GB, 24h/day) | ~$9.50 |
| **合計** | **~$25.71/月** |

### Option B: ECS on EC2 + Static Private IP

```
FSxN SVM (data LIF)
  │
  │ TCP connect to EC2 ENI static IP (port 9898)
  ▼
EC2 Instance (ECS Container Instance)
  │ Static Private IP (ENI)
  │ Security Group: TCP 9898 from SVM
  ▼
ECS Task (fpolicy-server container)
  │
  │ boto3 → SQS SendMessage
  ▼
SQS Ingestion Queue
```

**メリット:**
- IP が完全に安定（ENI に固定 Private IP を割り当て）
- NLB 不要（コスト削減）
- ONTAP の再接続が不要

**デメリット:**
- EC2 インスタンスの OS パッチ管理が必要
- インスタンス障害時の手動/自動復旧が必要（ASG で対応可能）
- Fargate のサーバーレス利点を失う
- EC2 インスタンスのサイジング管理

**コスト見積もり（東京リージョン）:**
| リソース | 月額 |
|----------|------|
| t4g.nano (2 vCPU, 0.5GB) | ~$3.02 |
| EBS (8GB gp3) | ~$0.64 |
| **合計** | **~$3.66/月** |

### Option C: EC2 単体（ECS なし）

```
FSxN SVM (data LIF)
  │
  │ TCP connect to EC2 static IP (port 9898)
  ▼
EC2 Instance (systemd service)
  │ fpolicy_server.py as systemd unit
  │ Static Private IP
  ▼
SQS Ingestion Queue
```

**メリット:**
- 最もシンプル（コンテナオーケストレーション不要）
- 最低コスト
- Shengyu 氏の検証実装と同一構成

**デメリット:**
- コンテナ化の利点なし（ポータビリティ、再現性）
- デプロイが手動（rsync + systemctl restart）
- 自動復旧なし（systemd の restart のみ）
- スケーリング不可

**コスト見積もり:** Option B と同等（~$3.66/月）

## 評価マトリクス

| 基準 | 重み | Option A (Fargate+NLB) | Option B (EC2+ECS) | Option C (EC2単体) |
|------|------|------------------------|--------------------|--------------------|
| 運用負荷 | 30% | 9/10 | 5/10 | 3/10 |
| IP 安定性 | 25% | 8/10 (NLB) | 10/10 | 10/10 |
| 高可用性 | 20% | 9/10 | 7/10 (ASG) | 4/10 |
| コスト | 15% | 5/10 ($26/月) | 9/10 ($4/月) | 10/10 ($4/月) |
| スケーラビリティ | 10% | 9/10 | 6/10 | 2/10 |
| **加重スコア** | | **8.25** | **7.05** | **5.30** |

## 決定: Option A（ECS Fargate + NLB）→ 修正: Option A'（ECS Fargate 直接接続）

**AWS 検証結果に基づく修正（2026-05-13）:**

NLB 経由では ONTAP FPolicy プロトコルのハンドシェイクが完了しない問題が判明。
NLB が TCP 接続を中継する際に、FPolicy プロトコルのバイナリフレーミング
（`"` + 4バイト長 + `"` + payload）が正しく転送されない。

**修正アーキテクチャ: Fargate タスク直接接続**

```
FSxN SVM (data LIF: 10.0.9.32, 10.0.2.18)
  │
  │ TCP connect to Fargate Task IP (port 9898)
  ▼
ECS Fargate Task (10.0.4.234)
  │ awsvpc network mode
  │ Security Group: TCP 9898 from VPC CIDR
  ▼
fpolicy-server container
  │
  │ boto3 → SQS SendMessage
  ▼
SQS Ingestion Queue
```

**NLB の役割変更:**
- ~~ONTAP → NLB → Fargate~~ ❌（FPolicy プロトコル非互換）
- NLB はヘルスチェック + サービスディスカバリ用途のみ
- ONTAP external-engine には Fargate タスクの直接 Private IP を指定

**IP 安定性の対策:**
- ECS Service Discovery（AWS Cloud Map）で DNS 名を登録
- タスク再起動時は ONTAP external-engine の primary_servers を更新
- 自動化: EventBridge ECS Task State Change → Lambda → ONTAP REST API で IP 更新

**検証結果:**
- ONTAP → Fargate 直接接続: `state: "connected"` ✅
- NEGO_REQ/RESP ハンドシェイク: Version 1.2 で成功 ✅
- 2 ノードからの接続確立: 両方 connected ✅

## ONTAP FPolicy 設定時の注意事項

### IP アドレス指定

```bash
# Option A: NLB の静的 IP を指定
vserver fpolicy policy external-engine create \
  -vserver SVM_NAME \
  -engine-name fpolicy_aws_engine \
  -primary-servers <NLB_PRIVATE_IP> \
  -port 9898 \
  -extern-engine-type asynchronous

# Option B/C: EC2 の固定 Private IP を指定
vserver fpolicy policy external-engine create \
  -vserver SVM_NAME \
  -engine-name fpolicy_aws_engine \
  -primary-servers <EC2_PRIVATE_IP> \
  -port 9898 \
  -extern-engine-type asynchronous
```

### 接続断時の動作

- ONTAP は keep-alive タイムアウト（デフォルト 2 分）で接続断を検知
- 検知後、自動的に再接続を試行
- NLB 使用時は、Fargate タスク再起動後に NLB が新タスクにルーティング
- `-is-mandatory false` 設定により、接続断中もファイル操作はブロックされない

### Security Group 設定

```
FPolicy Server SG:
  Inbound: TCP 9898 from FSxN SVM Security Group
  Outbound: TCP 443 to SQS VPC Endpoint (or NAT Gateway)

FSxN SVM SG:
  Outbound: TCP 9898 to FPolicy Server SG
```

## 関連ドキュメント

- [FPolicy セットアップガイド](../guides/fpolicy-setup-guide.md)
- [イベント駆動アーキテクチャ設計](./architecture-design.md)
- [NetApp: Node-to-external FPolicy server communication](https://docs.netapp.com/us-en/ontap/nas-audit/node-fpolicy-server-communication-process-concept.html)
- [NetApp: How FPolicy works with external servers](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-external-fpolicy-servers-concept.html)
- [Shengyu Fang: ontap-fpolicy-aws-integration](https://github.com/YhunerFSY/ontap-fpolicy-aws-integration)
