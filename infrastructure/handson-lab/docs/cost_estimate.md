# コスト見積もり

FSx for ONTAP ハンズオン Lab 環境の月額コスト概算です。

> 東京リージョン (ap-northeast-1) / USD / 2026年7月時点の料金

---

## リソース別コスト

| リソース | スペック | 月額 (USD) | 備考 |
|----------|---------|------------|------|
| **FSx for ONTAP** | 1 TiB SSD, 128 MB/s, Single-AZ | ~$194 | SSD: $0.168/GiB + Throughput: $0.583/MBps |
| **AWS Managed AD** | Standard Edition (2 DC) | ~$72 | $0.10/時間 |
| **NAT Gateway** | 1台 + データ転送 | ~$32 | $0.045/時間 + $0.045/GB |
| **Windows EC2** | t3.medium (2vCPU, 4GiB) | ~$34 | $0.0464/時間 (オンデマンド) |
| **VPC Endpoints** | Interface x3 (SSM) | ~$22 | $0.01/時間/ENI |
| **EBS (EC2)** | gp3 50GiB | ~$4 | $0.096/GiB |
| **Lambda** | Custom Resources | <$1 | デプロイ時のみ |
| **Secrets Manager** | シークレット x3 | ~$1.20 | $0.40/シークレット/月 |
| **S3** | テンプレート・Lambda保管 | <$1 | 数MB程度 |
| **CloudWatch Logs** | Lambda + EC2 | ~$2 | 取り込み + 保管 |
| | | | |
| **合計** | | **~$363/月** | |

---

## 時間単位コスト

検証を短時間で完了する場合の参考:

| 利用時間 | 概算コスト |
|----------|-----------|
| 1時間 | ~$0.50 |
| 4時間 (ハンズオン1回分) | ~$2.00 |
| 1日 (8時間) | ~$4.00 |
| 1週間 (常時稼働) | ~$85 |
| 1ヶ月 (常時稼働) | ~$363 |

> FSx for ONTAP は起動中に課金されます。検証しない時間帯は削除推奨。

---

## コスト最適化オプション

### 1. 既存リソース活用 (推奨)

既に VPC や FSx for ONTAP がある場合、`UseExistingVpc=true` / `UseExistingFsx=true` で大幅に削減:

| 削減対象 | 節約額/月 |
|----------|----------|
| FSx for ONTAP 共有利用 | -$194 |
| VPC + NAT GW + Endpoints 共有 | -$54 |
| **合計削減** | **-$248** |

残存コスト: ~$115/月 (AD + EC2 + EBS のみ)

### 2. VPC Endpoints 無効化

NAT Gateway 経由で SSM にアクセスする場合、VPC Endpoints は不要:

```
EnableVpcEndpoints=false  → -$22/月
```

### 3. EC2 スポットインスタンス

検証用途であればスポットインスタンスで ~70% 削減可能 (中断リスクあり):

```
t3.medium スポット: ~$0.014/時間 (オンデマンド比 70% OFF)
```

### 4. 検証後の即時削除

```bash
# ハンズオン完了後すぐに削除
./scripts/cleanup.sh --stack-name fsx-ontap-handson --force
```

---

## AWS 無料枠対象

以下のリソースは無料枠の範囲内で利用可能な場合があります (新規アカウント12ヶ月):

| リソース | 無料枠 |
|----------|--------|
| EC2 t3.micro | 750時間/月 (ただし t3.medium は対象外) |
| S3 | 5 GiB |
| Lambda | 100万リクエスト + 40万GB秒 |
| CloudWatch | 基本モニタリング |

> FSx for ONTAP, Managed AD, NAT Gateway は無料枠対象外です。

---

## コスト監視

デプロイ後、以下で費用を監視:

```bash
# 日次コスト確認 (Cost Explorer CLI)
aws ce get-cost-and-usage \
  --time-period Start=2026-07-16,End=2026-07-17 \
  --granularity DAILY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --region us-east-1
```

または AWS Console → Billing → Cost Explorer でスタック名タグ (`fsx-ontap-handson`) でフィルタ。
