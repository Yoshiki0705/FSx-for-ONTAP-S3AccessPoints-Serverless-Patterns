# AI レディネスチェックリスト

[日本語](ai-readiness-checklist-ja.md) | [English](ai-readiness-checklist.md)

レプリケーションされた FSx for ONTAP データを AI、BI、または自然言語分析に使用する前に、以下を確認してください:

> **重要**: このパターンは、レプリケーションデータが自動的に AI-ready であることを前提としていません。データが準備できているかを判断するための鮮度、ガバナンス、オブザーバビリティシグナルを提供します。

## レディネスレベル

| レベル | 基準 | 利用可否 |
|--------|------|---------|
| **Ready** | 鮮度、ガバナンス、品質、利用境界がすべて満たされている | BI ダッシュボード、AI プロンプト、自動サマリーに安全に利用可能 |
| **Needs review** | 1つ以上のチェックが未完了だが、ヒューマンレビュー付きの利用は許容可能 | 明示的な注意事項付きの探索利用に許容 |
| **Not ready** | 鮮度不明、分類未設定、オーナー未定義、またはレビューなしの高影響利用 | ビジネスユーザーや AI サービスに公開しない |

## 鮮度

- [ ] `source_of_record_timestamp` が利用可能
- [ ] `replicated_at` が利用可能
- [ ] `dashboard_refreshed_at` が利用可能
- [ ] データ経過時間が定義済み SLO 内（`slo-design.md` 参照）

## ガバナンス

- [ ] データ分類が割り当て済み（public / internal / confidential / restricted）
- [ ] データオーナーが定義済み
- [ ] 許可された利用者が定義済み
- [ ] 機密フィールドが識別され、マスクまたは除外済み
- [ ] データアクセスの監査証跡が有効

## 品質

- [ ] 必須フィールドが存在する
- [ ] スキーマバージョンが既知で互換性あり
- [ ] 空ファイルが分析から除外されている
- [ ] 重複レコードが処理またはフラグ付けされている
- [ ] 高影響の AI 生成アクションにはヒューマンレビューが必要

## 利用境界

- [ ] データが「レプリケーションコピーであり、正本ではない」と明示的にラベル付けされている
- [ ] RPO の制限が文書化され、AI 利用者に見える
- [ ] 結果は即時の自動トランザクション決定には適さない
- [ ] 規制上の決定には追加のコンプライアンスレビューが必要
- [ ] AI 生成のインサイトにはプロヴナンス（どのデータ、どのタイムスタンプ）が含まれる

## AI サービス統合レディネス

| AWS サービス | FSx S3 AP サポート | 備考 |
|-------------|-------------------|------|
| Amazon Quick / QuickSight | ✅ S3 データソース経由 | 自然言語 Q&A、ダッシュボード |
| Amazon Bedrock Knowledge Bases | ✅ S3 データソース経由 | エンタープライズドキュメントの RAG |
| Amazon Athena | ✅ 直接クエリ | ファイルデータの SQL 分析 |
| AWS Glue | ✅ S3 AP 経由の ETL | 変換、検証、パーティション |
| Amazon SageMaker | ✅ S3 AP 経由 | 学習データ、バッチ推論 |
| Amazon EMR Serverless | ✅ S3 AP 経由の Spark | 大規模分析 |

> 参考: [Using S3 Access Points with AWS services](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)
