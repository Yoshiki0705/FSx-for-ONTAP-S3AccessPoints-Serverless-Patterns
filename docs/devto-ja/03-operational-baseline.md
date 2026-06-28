---
title: "運用ベースラインの確立 — 17UC展開・DevSecOps・VPC Endpoint 自動検出"
published: false
description: "FSx for ONTAP S3 AP パターン集を17ユースケース全体に展開し、DevSecOpsバリデーション、自動デプロイ、パブリックセクター対応を完成させた Phase 7〜9。"
tags: aws, netapp, devsecops, cloudformation
series: "FSx for ONTAP S3 AP サーバーレスパターン集"
---

## TL;DR

Phase 7〜9 は「作ったものを安全に運用できる状態にする」フェーズです。

| Phase | テーマ |
|-------|--------|
| 7 | パブリックセクター UC 追加 (UC15-17)、OutputDestination 統一、17UC クロスバリデーション |
| 8 | DevSecOps バリデータスイート (5 ツール)、CI 自動化、マルチパート対応、デモガイド全言語対応 |
| 9 | 17UC 全体ロールアウト、VPC Endpoint 自動検出、Lambda パフォーマンスチューニング |

📦 **リポジトリ**: [GitHub](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## Phase 7: パブリックセクターと統一 API

### 3 つのパブリックセクターパターン

| UC | 分野 | 特徴 |
|----|------|------|
| UC15 | 防衛・情報機関 | データ分類ラベル、監査証跡強化 |
| UC16 | 自治体 | 個人情報検出、コンプライアンス対応 |
| UC17 | 公共インフラ | IoT センサーデータ解析 |

> **ガバナンス** (Public Sector SA lens): UC15–17 は技術アーキテクチャのリファレンスです。防衛・公共分野での実運用には、ISMAP、特定秘密保護法、ガバメントクラウド要件など組織固有のセキュリティ認定への適合評価が別途必要です。

### OutputDestination 統一

全 UC に `OutputDestination` パラメータを追加：

```yaml
Parameters:
  OutputDestination:
    Type: String
    Default: STANDARD_S3
    AllowedValues:
      - STANDARD_S3      # 新規 S3 バケットに出力
      - FSXN_S3AP        # FSx for ONTAP に書き戻し
```

NFS/SMB ユーザーが AI 処理結果を直接参照できる `FSXN_S3AP` モードは、エンタープライズ運用で特に重要。

---

## Phase 8: DevSecOps バリデーション

### 5 つの CI バリデータ

| ツール | 検出対象 |
|--------|---------|
| `lint_all_templates.sh` | cfn-lint エラー |
| `check_handler_names.py` | Lambda ハンドラ名の不整合 |
| `check_conditional_refs.py` | Condition 付きリソースの不正参照 |
| `check_s3ap_iam_patterns.py` | S3 AP IAM ARN フォーマット不正 |
| `check_python_quality.py` | Python コード品質 |

全て GitHub Actions で push/PR ごとに自動実行。

### マルチパート対応 (5GB 超)

`OutputWriter.put_stream` API を追加。VFX レンダー、生ゲノムデータ (FASTQ)、大容量 GeoTIFF の出力に対応。

---

## Phase 9: 本番ロールアウト

### VPC Endpoint 自動検出

最も頻発するデプロイ失敗原因: 「VPC Endpoint が存在しない」。Phase 9 のデプロイスクリプトは事前に VPC Endpoint の有無を確認し、不足分を自動検出して Conditions で制御。

```bash
# デプロイ時に自動判定
./deploy.sh --stack-name my-uc1
# → VPC Endpoint 未設定なら EnableVpcEndpoints=true で作成
# → 既存なら EnableVpcEndpoints=false でスキップ
```

### Lambda パフォーマンスチューニング

17 UC 全体で Lambda のメモリ/タイムアウト設定を最適化。ARM64 + 適切なメモリ割当で p95 レイテンシを改善。

### CDK 採用を見送った理由

> Phase 9 で CDK 移行を検討し、**見送り**を決定しました。理由:
> - 17 UC × 個別テンプレートの構造が SAM/CFn に最適化済み
> - CDK への移行コストに対してメリットが不十分
> - 新規プロジェクト（RAG、BLEA）では CDK を採用

> **技術選択** (Application Developer lens): SAM/CFn か CDK かはプロジェクトの段階と構造で判断します。既に多数のテンプレートが安定稼働しているなら移行コスト > メリットになりやすい。新規プロジェクトでは CDK の型安全性と再利用性が活きます。

---

## この段階での到達点

Phase 9 完了時点で「17 UC を安全にデプロイ・運用できる」状態が確立：

- ✅ 全 UC に統一された OutputDestination API
- ✅ CI/CD で自動バリデーション (lint + security + quality)
- ✅ VPC Endpoint 自動検出でデプロイ失敗率大幅削減
- ✅ パブリックセクター対応（データ分類、監査）
- ✅ 8 言語デモガイド + スクリーンショット

次は、ファイル操作イベントをリアルタイムに捉える FPolicy Event-Driven パイプラインの話です。

---

📦 **詳細**: [GitHub リポジトリ](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

> **前回の記事**: [#2 — 本番アーキテクチャ](./02-production-architecture.md)
> **DemoMode**: 本記事で紹介する全パターンは `DemoMode=true` で FSx for ONTAP なしに動作確認できます。
