# SnapMirror Cross-Region DR + S3 Access Points パターン

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概要

S3 Access Points 経由で収集したデータを SnapMirror Asynchronous でクロスリージョン DR サイトに複製し、フェイルオーバー時に自動で新規 S3 AP を宛先ボリュームにアタッチする DR パターン。

通常時はソースボリュームの S3 AP 経由でデータ収集。DR イベント発生時、Lambda が ~3 分でフェイルオーバーを完了: SnapMirror break → junction path 設定 → S3 AP 作成。

## アーキテクチャ

```mermaid
graph TB
    subgraph "通常運用 (Region A)"
        WRITER[Writer Lambda]
        S3AP_SRC[S3 Access Point<br/>ソース]
        SRC_VOL[Source Volume<br/>vol_sm_dr_source]
    end
    subgraph "レプリケーション"
        SM[SnapMirror Async<br/>5分間隔]
    end
    subgraph "DR フェイルオーバー (Region B)"
        FAILOVER[Failover Lambda]
        S3AP_DST[S3 Access Point<br/>宛先<br/>(フェイルオーバー時に作成)]
        DST_VOL[Dest Volume (DP)<br/>vol_sm_dr_dest]
        SNS[SNS 通知]
        CLIENT[アプリケーション<br/>(新 S3 AP に切替)]
    end

    WRITER -->|PutObject| S3AP_SRC
    S3AP_SRC --> SRC_VOL
    SRC_VOL -->|増分<br/>レプリケーション| SM
    SM --> DST_VOL
    FAILOVER -->|1. SM break<br/>2. junction設定<br/>3. AP作成| DST_VOL
    FAILOVER --> S3AP_DST
    FAILOVER --> SNS
    SNS --> CLIENT
    CLIENT -->|S3 API| S3AP_DST
```

## 主要コンポーネント

| コンポーネント | 説明 |
|--------------|------|
| Source Volume + S3 AP | データ収集ポイント（Region A）。通常運用時に使用 |
| SnapMirror Async | ボリュームレベル増分レプリケーション（RPO = スケジュール間隔） |
| Destination Volume (DP) | データ保護ボリューム（break まで読み取り専用）。FSx API で作成必須（SM-VAL-009） |
| Failover Lambda | 自動化: break → junction → S3 AP 作成。RTO ~3 分 |
| SNS Topic | フェイルオーバー後にアプリケーションへ新 S3 AP エンドポイントを通知 |

## RTO / RPO

| メトリクス | 値 | 備考 |
|-----------|:---:|------|
| **RTO** | ~3 分 | SnapMirror break（即時）+ junction 伝搬（~2 分）+ S3 AP 作成（~30 秒） |
| **RPO** | ≤ SnapMirror スケジュール間隔 | デフォルト 5 分。最終転送以降のデータは消失する可能性あり |

## 前提条件

> 📐 **設計ガイド**: S3 AP のディレクトリ設計、性能特性、PoC チェックリストは [設計考慮事項](../../docs/design-considerations.md) を参照。

- FSx for ONTAP × 2 クラスタ（異なるリージョン）
- VPC Peering + Cluster/SVM Peering 確立済み
- DP 宛先ボリュームを `aws fsx create-volume` で作成済み（SM-VAL-009: ONTAP REST API のみでは FSx API に表示されず S3 AP アタッチ不可）
- SnapMirror 関係が初期化済み（`snapmirrored` 状態）
- 両リージョンで fsxadmin 認証情報が Secrets Manager に格納済み
- Lambda が宛先 ONTAP 管理 IP（ポート 443）にアクセス可能な VPC 構成

## デプロイ

```bash
# 1. スタックデプロイ（Source Vol, Dest DP Vol, Failover Lambda, SNS 作成）
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-sm-dr \
  --parameter-overrides file://params.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 2. Source S3 AP 作成 + SnapMirror 関係セットアップ
#    （スタック出力 PostDeployInstructions 参照）

# 3. フェイルオーバーテスト（ドライラン）
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{"dry_run": true}' \
  /tmp/dr-dryrun.json
```

## フェイルオーバー実行

```bash
# DR フェイルオーバー実行
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{}' \
  /tmp/dr-result.json

# 結果確認
cat /tmp/dr-result.json
# → {"s3_access_point": {"arn": "...", "alias": "..."}, ...}
```

## 検証

```bash
# フェイルオーバー後、宛先 S3 AP からデータ読み取り
aws s3api list-objects-v2 \
  --bucket <dest-s3-ap-alias>

aws s3api get-object \
  --bucket <dest-s3-ap-alias> \
  --key test/sample.txt \
  /tmp/recovered.txt
```

## 技術的制約

| 制約 | 詳細 |
|------|------|
| SnapMirror Asynchronous のみ | Synchronous は S3 NAS bucket ボリュームで非サポート |
| SVM-DR 非対応 | S3 NAS bucket を含む SVM は SVM-DR をブロック。Volume-level SnapMirror のみ |
| DP Volume は FSx API で作成必須 | SM-VAL-009: ONTAP REST API のみで作成したボリュームは FSx API に見えず、S3 AP アタッチ不可 |
| S3 AP は転送されない | SM-002: S3 AP は AWS レイヤのリソース。宛先に新規 AP が必要 |
| クライアント切替必須 | 新 AP は ARN/alias が異なる。アプリケーション側でエンドポイント更新が必要 |
| SnapMirror スケジュール | FSx for ONTAP の最小: 5 分間隔 |

## クリーンアップ（順序厳守 — SM-VAL-011）

```bash
# ⚠️ 以下の順序を必ず守ること

# 1. SnapMirror 関係削除（DESTINATION クラスタから）
#    ONTAP REST: DELETE /api/snapmirror/relationships/<uuid>?destination_only=true
#    SOURCE から: snapmirror release（ONTAP CLI）

# 2. SVM Peers 削除（両クラスタ）— 両側で num_records: 0 を確認

# 3. Cluster Peers 削除（両クラスタ）

# 4. VPC Peering 削除（ステップ 2 完了確認後のみ安全）

# 5. S3 Access Points デタッチ・削除
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <src-arn>
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <dest-arn>

# 6. CloudFormation スタック削除
aws cloudformation delete-stack --stack-name fsxn-sm-dr
```

## 参考資料

- [NetApp Docs: S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp KB: SVM DR of S3 buckets](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)
- [AWS Docs: FSx for ONTAP SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)
- [AWS Docs: FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)
