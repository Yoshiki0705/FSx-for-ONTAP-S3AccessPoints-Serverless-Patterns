# パターン選択ガイド — 導入先の状況に応じたユースケース推奨

🌐 **Language / 言語**: 日本語 | [English](pattern-selection-guide.en.md)

## 概要

このリポジトリのすべてのパターンから、導入先の状況に最適なものを選ぶためのガイドです。Partner/SI が初回の導入検討会話で使用することを想定しています。

**先に 1 つ断っておきます。このガイドは「どれを deploy するか」に答えます。「その構成でよいか」には答えません。** 設計判断の根拠は [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) 側にあり、業種から入る場合は [業種別リソースマップ](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/industry-resource-map.md#業種から入ったときの読む順序) が「最初に読むモジュール」を示します。同じ内容を 2 か所に置かない分担です。

### 読む順序

| # | やること | 場所 |
|---|---|---|
| 1 | **どのパターンか決める** | このページ |
| 2 | 動かす | 各パターンの `README` と `docs/demo-guide.md` |
| 3 | 本番に出す前に読む | 各 README 末尾の「本番に出す前に読むもの」（Playbook のモジュールへ） |
| 4 | 運用する | [operations/](#運用最適化-ops16未使用容量とコストを下げる) の OPS1-6 |

---

## 1. 業務課題から選ぶ（業種別 UC1-UC28）

すべて S3 Access Point 経由の Lambda パイプラインで、`DemoMode=true` なら FSx for ONTAP なしで動きます。

### 文書を読ませたい（OCR・抽出・分類）

| 課題 | パターン |
|---|---|
| 契約書・請求書の自動処理 | [UC2 financial-idp](../solutions/industry/financial-idp/) |
| ファイルサーバーの監査・データガバナンス | [UC1 legal-compliance](../solutions/industry/legal-compliance/) |
| 論文 PDF の分類・引用ネットワーク | [UC13 education-research](../solutions/industry/education-research/) |
| 配送伝票 OCR・倉庫在庫画像 | [UC12 logistics-ocr](../solutions/industry/logistics-ocr/) |
| 公文書アーカイブ・FOIA 対応 | [UC16 government-archives](../solutions/industry/government-archives/) |
| 予約文書処理・施設点検 | [UC20 travel-document-processing](../solutions/industry/travel-document-processing/) |
| ESG メトリクス抽出・フレームワークマッピング | [UC23 sustainability-esg-reporting](../solutions/industry/sustainability-esg-reporting/) |
| 助成金申請の分類・成果マッチング | [UC24 nonprofit-grant-management](../solutions/industry/nonprofit-grant-management/) |
| 物件画像分析・契約書抽出 | [UC26 real-estate-portfolio](../solutions/industry/real-estate-portfolio/) |
| 履歴書スクリーニング（PII 厳格モード） | [UC27 hr-document-screening](../solutions/industry/hr-document-screening/) |
| SDS 危険分類抽出・GHS バリデーション | [UC28 chemical-sds-management](../solutions/industry/chemical-sds-management/) |

### 画像・映像を処理したい

| 課題 | パターン |
|---|---|
| DICOM 画像の分類・匿名化 | [UC5 healthcare-dicom](../solutions/industry/healthcare-dicom/) |
| VFX レンダリング品質チェック | [UC4 media-vfx](../solutions/industry/media-vfx/) |
| 映像・LiDAR 前処理・アノテーション | [UC9 autonomous-driving](../solutions/industry/autonomous-driving/) |
| BIM モデル管理・図面 OCR | [UC10 construction-bim](../solutions/industry/construction-bim/) |
| 商品画像の自動タグ付け | [UC11 retail-catalog](../solutions/industry/retail-catalog/) |
| 衛星画像解析 | [UC15 defense-satellite](../solutions/industry/defense-satellite/) |
| クリエイティブアセットのカタログ化・ブランド適合 | [UC19 adtech-creative-management](../solutions/industry/adtech-creative-management/) |
| 農地航空画像・トレーサビリティ | [UC21 agri-food-traceability](../solutions/industry/agri-food-traceability/) |
| 設備点検画像・保守レポート | [UC22 transportation-maintenance](../solutions/industry/transportation-maintenance/) |
| 事故写真の損害評価・見積書 OCR | [UC14 insurance-claims](../solutions/industry/insurance-claims/) |
| ドローン画像点検・SCADA 異常検知 | [UC25 utilities-asset-inspection](../solutions/industry/utilities-asset-inspection/) |

### 大容量の科学・工学データを扱いたい

| 課題 | パターン |
|---|---|
| 設計ファイルのバリデーション・メタデータ抽出 | [UC6 semiconductor-eda](../solutions/industry/semiconductor-eda/) |
| 品質チェック・バリアントコール集計 | [UC7 genomics-pipeline](../solutions/industry/genomics-pipeline/) |
| 地震探査データ処理・坑井ログ異常検知 | [UC8 energy-seismic](../solutions/industry/energy-seismic/) |
| IoT センサーログ・品質検査画像 | [UC3 manufacturing-analytics](../solutions/industry/manufacturing-analytics/) |
| 地理空間データ解析・都市計画 | [UC17 smart-city-geospatial](../solutions/industry/smart-city-geospatial/) |
| CDR/ネットワークログ異常検知 | [UC18 telecom-network-analytics](../solutions/industry/telecom-network-analytics/) |

---

## 2. データの置き方から選ぶ（FlexCache / FlexClone / SnapMirror）

**既存の NFS/SMB ワークロードを動かさずに、別の場所から読ませたいときに使います。** UC 群との違いは、パイプラインではなくボリュームの配置を扱う点です。

| 課題 | パターン |
|---|---|
| 同一リージョンで S3 AP と NFS/SMB を併用 | [same-region-s3ap](../solutions/flexcache/same-region-s3ap/) |
| 別リージョンから低遅延で読ませる | [cross-region-s3ap](../solutions/flexcache/cross-region-s3ap/) |
| DR 用にレプリカを置く（SnapMirror） | [snapmirror-cross-region-dr](../solutions/flexcache/snapmirror-cross-region-dr/) |
| 複数拠点から同じデータを読む（AnyCast / DR） | [anycast-dr](../solutions/flexcache/anycast-dr/) |
| CAE 解析を並列で回す | [automotive-cae](../solutions/flexcache/automotive-cae/) |
| レンダー / EDA ワークフローを動的にスケール | [dynamic-render-workflow](../solutions/flexcache/dynamic-render-workflow/) |
| ゲームアセット共有とビルドパイプライン | [gaming-build-pipeline](../solutions/flexcache/gaming-build-pipeline/) |
| 研究データを複数チームで分析 | [life-sciences-research](../solutions/flexcache/life-sciences-research/) |
| Dev/Test データを FlexClone で高速リフレッシュ | [devops-cicd](../solutions/flexcache/devops-cicd/) |
| 社内ファイルを RAG の入力にする | [rag-enterprise-files](../solutions/flexcache/rag-enterprise-files/) |

---

## 3. 利用者への出し方から選ぶ

| 課題 | パターン |
|---|---|
| NAS のファイルをブラウザから使わせたい（VPN 不要） | [ファイルポータル (Amplify Gen2)](../solutions/amplify-portal/) |
| コンテンツを CDN/エッジ配信したい | [content-delivery](../solutions/edge/content-delivery/)（[CDN 比較](cdn-comparison.md)） |
| ライブ配信を VOD として公開したい | [media-ivs-vod-publishing](../solutions/edge/media-ivs-vod-publishing/) |
| 社内ナレッジを利用者自身に育てさせたい | [kb-selfservice-curation](../solutions/genai/kb-selfservice-curation/) |
| エージェント型のワークスペースから使わせたい | [quick-agentic-workspace](../solutions/genai/quick-agentic-workspace/) |
| ERP に隣接するファイルワークフロー | [sap/erp-adjacent](../solutions/sap/erp-adjacent/) |

---

## 4. 起動のしかたから選ぶ（ポーリング / イベント駆動）

| 課題 | パターン |
|---|---|
| ファイル操作をリアルタイムに検知したい | [event-driven/fpolicy](../solutions/event-driven/fpolicy/)（[FPolicy セットアップ](guides/fpolicy-setup-guide.md)） |
| イベント駆動の最小構成を試したい | [event-driven/prototype](../solutions/event-driven/prototype/) |
| ポーリングとイベント駆動を選び分けたい | [TriggerMode 判断ガイド](trigger-mode-decision-guide.md) |
| HA 構成の監視を組み込みたい | [ha/lifekeeper-monitoring](../solutions/ha/lifekeeper-monitoring/) |

---

## 5. 運用最適化（OPS1-6）— 未使用容量とコストを下げる

**S3 Access Point を使わない側の柱です。** すでに動いているファイルシステムに対して行う操作で、パターンを deploy する話とは独立に使えます。

| 課題 | パターン |
|---|---|
| 容量・スループットが過剰か判断したい | [OPS1 capacity-rightsizing](../operations/capacity-rightsizing/) |
| 重複排除・圧縮の効きを測りたい | [OPS2 storage-efficiency](../operations/storage-efficiency/) |
| FabricPool の階層化を最適化したい | [OPS3 tiering-optimizer](../operations/tiering-optimizer/) |
| Snapshot の保持を整理したい | [OPS4 snapshot-lifecycle](../operations/snapshot-lifecycle/) |
| コストを FinOps の枠に載せたい | [OPS5 cost-optimization](../operations/cost-optimization/) |
| QoS ポリシーを監視したい | [OPS6 qos-monitoring](../operations/qos-monitoring/) |

---

## 6. 状況別の入り方

| 導入先の状況 | 入り方 |
|---|---|
| FSx for ONTAP を既にファイル共有で利用中 | 業種別 UC + `DemoMode=false` |
| FSx for ONTAP 未導入、ワークフローだけ評価したい | 任意の UC + `DemoMode=true` |
| 安全重要領域で Human Review が必要 | UC22 / UC25 + `shared/human_review.py` |
| PII / 個人情報保護が必要 | UC26 / UC27 + `shared/data_classification.py` |
| 設備メンテナンス × マルチモーダル AI | UC22 + Rekognition + Bedrock multimodal（[事例](investigations/dais2026-agent-bricks-industry-cases.md#1-7-eleven-メンテナンス技術者向け-genai-アシスタント)） |
| 製薬・ライフサイエンス × マルチエージェント RAG | UC7 + Step Functions multi-agent routing（[事例](investigations/dais2026-agent-bricks-industry-cases.md#2-astrazeneca-マルチエージェントシステム10x-スケール)） |
| 新規オブジェクトネイティブワークロード（NAS 不要） | **このリポジトリのパターンは不要です。** 標準 S3 / DynamoDB のサーバーレス構成のほうが素直です |

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

> **重要**: これらのパターンは reference implementation（参照実装）であり、導入先の規制・監査・運用・データ分類要件を自動的に満たすものではありません。本番利用前に導入先自身のポリシーと規制要件への適合を検証してください。

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
