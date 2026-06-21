# パターン選択ガイド — 顧客状況に応じたユースケース推奨

🌐 **Language / 言語**: [日本語](pattern-selection-guide.md) | [English](pattern-selection-guide.en.md)

## 概要

28 ユースケース + 6 FlexCache/FlexClone パターンから、顧客の状況に最適なパターンを選択するためのガイドです。Partner/SI が初回の顧客会話で使用することを想定しています。

## 顧客状況別の推奨パターン

| 顧客の状況 | 推奨パターン |
|---|---|
| FSx for ONTAP を既にファイル共有で利用中 | 業界別 UC + DemoMode=false |
| FSx for ONTAP 未導入、ワークフロー評価したい | 任意の UC + DemoMode=true |
| 文書処理中心（PDF、契約書、レポート） | UC20 / UC23 / UC24 / UC26 / UC27 / UC28 |
| 画像・点検ワークロード中心 | UC19 / UC21 / UC22 / UC25 |
| ログ / 時系列 / 分析ワークロード | UC18 / UC25 (SCADA) |
| 安全重要領域で Human Review が必要 | UC22 / UC25 + human_review モジュール |
| PII / 個人情報保護が必要 | UC27 / UC26 + data_classification モジュール |
| ESG / サステナビリティ報告 | UC23 + framework mapping |
| 既存 NFS/SMB ワークロードの横展開 | FC1-FC6（FlexCache/FlexClone パターン） |
| コンテンツを CDN/エッジ配信したい（CloudFront / サードパーティ CDN） | solutions/edge/content-delivery（[CDN比較](cdn-comparison.md) 参照） |
| 設備メンテナンス × マルチモーダル AI（画像 + 文書 RAG） | UC22 + Rekognition + Bedrock multimodal（[7-Eleven 事例参照](investigations/dais2026-agent-bricks-industry-cases.md#1-7-eleven-メンテナンス技術者向け-genai-アシスタント)） |
| 製薬・ライフサイエンス × マルチエージェント権限保持 RAG | UC7 + Step Functions multi-agent routing（[AstraZeneca 事例参照](investigations/dais2026-agent-bricks-industry-cases.md#2-astrazeneca-マルチエージェントシステム10x-スケール)） |
| 新規オブジェクトネイティブワークロード（NAS 不要） | 標準 S3 / DynamoDB サーバーレスネイティブ構成を推奨 |

## ワークロード別の技術選択

| ワークロード特性 | 推奨 AI サービス | 代表 UC |
|---|---|---|
| 画像の物体検出・分類 | Rekognition | UC19, UC21, UC22, UC25, UC26 |
| PDF/文書からの構造化データ抽出 | Textract + Comprehend | UC20, UC24, UC26, UC27, UC28 |
| 自然言語推論・分類・要約 | Bedrock (Nova/Claude) | 全 UC |
| 時系列異常検出 | Athena + Bedrock | UC18, UC25 |
| ESG フレームワークマッピング | Bedrock (structured prompt) | UC23 |

## DemoMode → 本番移行の判断基準

| 評価ポイント | DemoMode で確認 | 本番移行前に追加確認 |
|---|---|---|
| ワークフロー動作 | ✅ Step Functions SUCCEEDED | — |
| AI 抽出精度 | ✅ サンプルデータで確認 | ドメインバリデーションセットで評価 |
| パフォーマンス | ⚠️ S3 バケット経由（参考値） | FSx for ONTAP S3 AP 経由で実測 |
| 権限モデル | ⚠️ S3 IAM のみ | IAM + S3 AP policy + ONTAP ID |
| ネットワーク | ⚠️ パブリック経路 | Internet/VPC-origin 設計判断 |
| ガバナンス | ⚠️ デモラベル | データ分類 + リネージ + 保持 |
| コスト | ✅ ~$0.10/実行 | + FSx for ONTAP (~$194/月基本) |

## 安全重要・規制産業での追加考慮事項

以下の業界では、パターン選択後に追加のガバナンス検討が必要です:

| 業界 | 追加考慮事項 |
|---|---|
| 運輸・鉄道 (UC22) | エスカレーション閾値設定、Human Review SLA、保全計画チームとの連携 |
| 電力・ユーティリティ (UC25) | SCADA データ分類、マルチモーダル結果の統合評価プロセス |
| HR・人材 (UC27) | 労働法・差別禁止法適合、PII 取扱い規程、採用決定は人間が実施 |
| 金融・保険 (UC2/UC14) | FISC 準拠、監査証跡、データ保持ポリシー |
| 医療 (UC5/UC7) | 個人情報保護法、医療情報取扱い規程 |
| 公共 (UC16) | NARA 準拠、情報公開法対応、データ所在地要件 |

> **重要**: これらのパターンは reference implementation（参照実装）であり、顧客の規制・監査・運用・データ分類要件を自動的に満たすものではありません。本番利用前に顧客自身のポリシーと規制要件への適合を検証してください。

## NetworkOrigin 設計判断

| 要件 | 推奨 NetworkOrigin |
|---|---|
| 全コンシューマーが同一 VPC 内 | VPC-origin |
| 外部 / オンプレミスクライアントがアクセス | Internet-origin |
| 厳格なプライベートアクセス制限 | VPC-origin |
| 複数 VPC からアクセス | TGW/peering 評価、または Internet-origin |
| Lambda (VPC 外) からアクセス | Internet-origin |
| Lambda (VPC 内) からアクセス | VPC-origin + S3 Gateway EP |

> **注意**: NetworkOrigin は作成後に変更できません。設計時に慎重に選択してください。
