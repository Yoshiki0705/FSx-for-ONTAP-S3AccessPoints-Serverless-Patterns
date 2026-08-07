# コスト計測 — サンドボックスの実測コスト

> 🌐 言語: **日本語** | [English](../en/cost-measurement.md)

> ポータルのサンドボックスを稼働させたあと、AWS Cost Explorer から実際のコストを計測する手法です。

## 計測方法

代表的な期間（1 週間を推奨）にわたって `npm start` を実行したあとに、次のコマンドを使います。

```bash
# Get costs for the sandbox stack (last 7 days)
aws ce get-cost-and-usage \
  --time-period Start=$(date -v-7d +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity DAILY \
  --metrics UnblendedCost \
  --filter '{
    "Tags": {
      "Key": "aws:cloudformation:stack-name",
      "Values": ["amplify-fsxns3apamplifyportal-dev1-sandbox-0123456789"]
    }
  }' \
  --group-by Type=DIMENSION,Key=SERVICE
```

## 想定コスト内訳（サンドボックス、軽負荷）

| サービス | 月額目安 | 備考 |
|---------|-----------------|-------|
| AWS AppSync | $0-4 | Free Tier: 250K クエリ/月 |
| Amazon Cognito | $0 | Free Tier: 50K MAU |
| AWS Lambda | $0-2 | Free Tier: 1M リクエスト/月 |
| Amazon DynamoDB | $0 | Free Tier: 25GB + 25 WCU/RCU |
| AWS Secrets Manager | $0.40 | $0.40/シークレット/月 |
| VPC（ENI 時間） | $0 | Lambda ENI に追加コストなし |
| CloudWatch Logs | $0-1 | 取り込み 5GB まで無料 |
| **合計（Free Tier 適用中）** | **~$1-5** | |
| **合計（Free Tier 終了後）** | **~$25-60** | 利用量に依存します |

## Free Tier 終了後の見積もり

12 か月経過後、Free Tier なしの場合は次のとおりです。

| 利用レベル | 月額コスト | 想定プロファイル |
|------------|-------------|---------|
| 軽負荷（10 ユーザー、100 リクエスト/日） | ~$25 | PoC / 評価 |
| 中負荷（50 ユーザー、1000 リクエスト/日） | ~$45 | チーム展開 |
| 高負荷（200 ユーザー、5000 リクエスト/日） | ~$80 | 部門全体 |

Free Tier 終了後の主なコスト要因は次のとおりです。
- AppSync: 100 万 Query/Mutation 操作あたり $4.00
- Cognito: 月間アクティブユーザーあたり $0.0055
- Lambda: 100 万リクエストあたり $0.20 + GB 秒あたり $0.0000166667
- DynamoDB: WCU あたり $1.25、RCU あたり $0.25（オンデマンド）

## 操作単位のコスト内訳

ユニットエコノミクスを必要とする FinOps チーム向けの内訳です。

| 操作 | 構成要素 | 計算 | 1 回あたりのコスト |
|-----------|-----------|------|--------------------|
| フォルダ 1 件の閲覧（ListObjectsV2） | Lambda（128MB、200ms）+ AppSync | 0.025 GB 秒 × $0.0000166667 + $0.000004 | ~$0.0000044 |
| PDF 1 件の AI 処理（Bedrock Nova Lite） | Lambda（256MB、3s）+ Bedrock（入力 1K + 出力 500 トークン） | 1 × $0.00006 + 0.5 × $0.00024 + 0.75 GB 秒 × $0.0000166667 | ~$0.0002 |
| PDF 1 件の AI 処理（Claude 3.5 Haiku） | Lambda（256MB、5s）+ Bedrock（入力 1K + 出力 500） | 1 × $0.0008 + 0.5 × $0.004 + 1.25 GB 秒 × $0.0000166667 | ~$0.0028 |
| スナップショット 1 件のロック（ONTAP REST） | Lambda（256MB、1s）+ AppSync | 0.25 GB 秒 × $0.0000166667 + $0.000004 | ~$0.0000082 |
| Rekognition（画像 1 枚） | Lambda + Rekognition の画像 API | $0.001/枚（月間 100 万枚まで） | ~$0.001 |
| Textract（テキストのみ、1 ページ） | Lambda + `DetectDocumentText` | $0.0015/ページ（100 万ページまで） | ~$0.0015 |
| Textract（表とフォーム、1 ページ） | Lambda + `AnalyzeDocument`（`TABLES`,`FORMS`） | $0.07/ページ（100 万ページまで） | ~$0.07 |
| Athena クエリ（スキャン 10MB） | Lambda + Athena | 最小課金 10MB × $5/TB | ~$0.00005 |

> **単価の出典**: us-east-1、オンデマンド。AWS Price List API から 2026-08-07 に取得。
> Lambda は $0.0000166667/GB 秒、AppSync は $0.000004/リクエスト。ap-northeast-1 は
> 若干異なるため、社外に数値を提示する前に再確認してください。
>
> **安いのは Nova Lite で、桁が違います**。Nova Lite は 100 万トークンあたり
> 入力 $0.06 / 出力 $0.24、Claude 3.5 Haiku は $0.80 / $4.00 で、入力で約 13 倍、
> 出力で約 17 倍の差があります。本表の以前のバージョンは両者が逆になっていました。
>
> **Textract の 2 行は約 47 倍違います**。ポータルは analyze モードで
> `analyze_document`（`TABLES` と `FORMS`）を、それ以外で `detect_document_text` を
> 呼びます（`functions/textract/index.py`）。どちらの行が該当するかは呼び出し側が
> 選んだモードで決まります。
>
> いずれも見積もりです。実際のコストはファイルサイズ、トークン数、処理時間で変わります。

**例**: 契約書 PDF 1,000 件を Bedrock Nova Lite で処理する場合（トークン数は上表のとおり）
- 1,000 × $0.0002 = **$0.20**（1 回のバッチ）
- 同規模のバッチを月 5 回実行 = AI 処理のみで **$1.00/月**

この単価では、請求額を左右するのは AI 処理ではありません。次節のインフラコストです。

## FSx for ONTAP のインフラコスト（別枠）

ポータルのコストは、Amazon FSx for NetApp ONTAP（以降 FSx for ONTAP）のインフラコストに加算されます。
- FSx for ONTAP（128 MBps、シングル AZ）: 約 $194/月
- S3 Access Point: 追加コストなし（FSx for ONTAP に含まれます）
- データ転送（リージョン内）: $0.01/GB

> 補足: FSx for ONTAP は共有インフラです。そのコストは、同一ファイルシステムを利用するすべてのワークロード（NFS/SMB クライアント + S3 AP + 本ポータル）に按分されます。
