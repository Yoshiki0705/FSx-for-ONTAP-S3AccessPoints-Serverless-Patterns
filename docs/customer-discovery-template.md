# Customer Discovery Template — ヒアリングシート

🌐 **Language / 言語**: [日本語](customer-discovery-template.md) | [English](customer-discovery-template.en.md)

## 概要

本テンプレートは、顧客との初回ヒアリングで FSx for ONTAP S3 Access Points サーバーレスパターンの適用可否を判断するための質問項目を整理したものです。

---

## 1. 現状のデータアクセス

| 質問 | 回答欄 | 設計への影響 |
|------|--------|------------|
| 既存データはどのプロトコルでアクセスされていますか？ | SMB / NFS / 両方 / S3 | FPolicy 対応可否、S3 AP identity タイプ |
| NFS バージョンは何ですか？ | NFSv3 / NFSv4.0 / NFSv4.1 / NFSv4.2 | NFSv4.2 は FPolicy 非対応 |
| 現在のストレージは何ですか？ | FSx for ONTAP / On-prem ONTAP / 他 NAS / S3 | 移行要否の判断 |
| データ量はどの程度ですか？ | ___TB, ___万ファイル | FSx サイジング、Map 並列度 |
| 平均ファイルサイズは？ | 小(<1MB) / 中(1-100MB) / 大(>100MB) | Lambda メモリ、処理戦略 |

---

## 2. データを S3 にコピーできない理由

| 質問 | 回答欄 | 設計への影響 |
|------|--------|------------|
| コスト（二重保管）が問題ですか？ | はい / いいえ | S3 AP の「データ移動なし」価値 |
| 規制上、データの複製が制限されていますか？ | はい / いいえ | Governance Checklist 適用 |
| 運用上、同期の仕組みが負担ですか？ | はい / いいえ | S3 AP の運用簡素化価値 |
| NFS/SMB ユーザーが AI 処理結果も見る必要がありますか？ | はい / いいえ | OutputDestination=FSXN_S3AP |
| データの鮮度（最新性）が重要ですか？ | はい / いいえ | ポーリング間隔 or EVENT_DRIVEN |

---

## 3. AI/ML 処理の要件

| 質問 | 回答欄 | 設計への影響 |
|------|--------|------------|
| どのような処理を自動化したいですか？ | OCR / 分類 / 要約 / 異常検知 / 画像分析 / その他 | UC パターン選択 |
| AI/ML 処理結果を誰が見ますか？ | 業務担当者 / 分析者 / 監査担当 / システム連携 | 出力先・フォーマット設計 |
| 処理結果をどこで見たいですか？ | 同じファイルサーバー / S3 / BI ツール / API | OutputDestination 選択 |
| AI 出力の自動確定は許容されますか？ | はい / 条件付き / いいえ（人間確認必須） | Human-in-the-loop 設計 |
| 処理対象のデータに個人情報は含まれますか？ | はい / いいえ / 不明 | PII 検出、Governance |

---

## 4. レイテンシ・頻度の要件

| 質問 | 回答欄 | 設計への影響 |
|------|--------|------------|
| ファイル変更から処理完了までの許容時間は？ | リアルタイム / 数分 / 1時間 / 日次 / 週次 | TriggerMode 選択 |
| 処理頻度は？ | 常時 / 営業時間のみ / 日次バッチ / 週次 | Business Hours Scheduling |
| ピーク時のファイル生成数は？ | ___件/時間 | Map 並列度、FSx スループット |

---

## 5. 監査・コンプライアンス要件

| 質問 | 回答欄 | 設計への影響 |
|------|--------|------------|
| 監査ログの保管期間は？ | 1年 / 3年 / 7年 / 永久 | S3 Object Lock、Lineage |
| イベントロスは許容されますか？ | はい / いいえ | Persistent Store 要否 |
| データのリージョン制約はありますか？ | 国内のみ / 特定リージョン / 制約なし | クロスリージョン呼び出し可否 |
| 改ざん防止が必要ですか？ | はい / いいえ | S3 Object Lock |
| 定期的な監査レポートが必要ですか？ | はい / いいえ | Lineage export + レポート |

---

## 6. 運用・組織

| 質問 | 回答欄 | 設計への影響 |
|------|--------|------------|
| AWS アカウント構成は？ | 単一 / マルチアカウント / Organizations | StackSets、Cross-Account |
| 運用チームの AWS 経験は？ | 初級 / 中級 / 上級 | Maturity Level 選択 |
| 既存の CI/CD パイプラインはありますか？ | はい / いいえ | デプロイ方式 |
| 障害時の対応体制は？ | 自動復旧のみ / 営業時間対応 / 24/7 | Alarm Profile、Runbook |
| 予算上限は？ | ___円/月 | コスト最適化設計 |

---

## 7. 次のステップ判断マトリクス

ヒアリング結果に基づき、以下のパスを推奨:

| 条件 | 推奨パス |
|------|---------|
| 「まず動くものを見たい」 | Level 1 Sandbox → 30 分パス |
| 「定期的に自動処理したい」 | Level 2 Scheduled → 60 分パス |
| 「本番環境で使いたい」 | Level 3-4 → 1 日ワークショップ |
| 「規制対象データを扱う」 | Governance Checklist + Compliance Profile |
| 「リアルタイム検知が必要」 | EVENT_DRIVEN + Deployment Profiles |

---

## 参考リンク

- [Choose Your Path](../README.md#choose-your-path)
- [Production Readiness](production-readiness.md)
- [Governance Checklist](governance-checklist.md)
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
