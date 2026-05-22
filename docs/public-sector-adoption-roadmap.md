# Public Sector 導入ロードマップ

🌐 **Language / 言語**: [日本語](public-sector-adoption-roadmap.md) | [English](public-sector-adoption-roadmap.en.md)

## 概要

自治体、教育機関、医療機関、中央省庁が本パターンを導入する際の 3 段階ロードマップです。

---

## 3 段階ロードマップ

```
Phase A              Phase B              Phase C
PoC・検証      →    限定本番        →    庁内/組織展開
(2-4 週間)          (1-3 ヶ月)           (3-6 ヶ月)
```

### Production Readiness Level との対応

| Public Sector Phase | Production Readiness Level | 説明 |
|--------------------|--------------------------|------|
| Phase A: PoC・検証 | Level 1 (Sandbox) → Level 2 (Scheduled) | 手動実行で動作確認 → 定期実行で安定性確認 |
| Phase B: 限定本番 | Level 3 (Monitored) | Dashboard + Alarm + Runbook で可観測性確立 |
| Phase C: 庁内展開 | Level 4 (Production) | StackSets + CI/CD + SLO + DR + 監査対応 |

詳細: [Production Readiness Maturity Model](production-readiness.md)

---

## Phase A: PoC・検証（2-4 週間）

### 目的
- パターンの動作確認と適用可否判断
- セキュリティ・ガバナンス要件との整合性確認
- コスト・性能の概算取得

### 成果物
- [ ] PoC 環境構築完了（単一 AWS アカウント）
- [ ] 1-2 UC テンプレートのデプロイ・動作確認
- [ ] S3 AP 経由のファイルアクセス検証
- [ ] AI/ML 処理結果の品質評価
- [ ] セキュリティレビュー結果（S3AP 認可モデル確認）
- [ ] コスト見積もり（月額概算）
- [ ] PoC 報告書

### セキュリティレビュー項目
| 項目 | 確認内容 | 判定 |
|------|---------|------|
| データ分類 | 処理対象データの機密レベル特定 | □ |
| 認可モデル | IAM + ONTAP file system identity の設計 | □ |
| 暗号化 | 保管時 (SSE-FSX) + 転送時 (TLS) | □ |
| ネットワーク | VPC 分離、VPC Endpoint 設計 | □ |
| ログ | CloudTrail、CloudWatch Logs の保管設計 | □ |
| クロスリージョン | Textract/Comprehend Medical の呼び出し可否 | □ |

### 判定基準（Go / No-Go Criteria）

**Phase A → Phase B への移行条件**:
- [ ] 対象データ分類が確認済み（個人情報・医療情報の有無）
- [ ] 監査ログ取得方針が合意済み
- [ ] Human-in-the-loop の責任者が定義済み
- [ ] AI 出力の誤りに対する業務影響が評価済み
- [ ] 運用チームがアラートと障害対応を確認済み
- [ ] クロスリージョン呼び出しの可否が判断済み
- [ ] コスト見積もりが予算内であることを確認済み
- [ ] 住民・患者・学生など最終受益者への影響が評価済み
- [ ] AI 誤出力が発生した場合の業務影響と対応手順が定義済み
- [ ] AI 利用目的・データ利用範囲・誤出力時の責任分界を関係者に説明できる状態か
- [ ] 判断に関わる関係者（業務部門、情報システム、セキュリティ、個人情報保護担当）が特定済み

**判定**:
- ✅ 全条件クリア → Phase B へ進行
- ⚠️ 一部未達 → 追加対策（Human-in-the-loop 強化等）で対応可能か評価
- ❌ 重大な不適合 → 代替アプローチを検討

---

## Phase B: 限定本番（1-3 ヶ月）

### 目的
- 限定的な本番データでの運用開始
- 運用手順の確立と運用チームへの引き継ぎ
- SLO の定義と監視体制の構築

### 成果物
- [ ] 本番環境構築（Production Deployment Profile）
- [ ] 運用 Runbook 作成
- [ ] アラーム・ダッシュボード設定
- [ ] SLO 定義（検知レイテンシ、エラー率、可用性）
- [ ] 障害対応手順の訓練実施
- [ ] 運用引き継ぎドキュメント
- [ ] 月次運用レポートテンプレート
- [ ] セキュリティ監査対応準備

### 運用設計項目
| 項目 | 設計内容 |
|------|---------|
| 監視 | CloudWatch Dashboard + Alarm Profile (BATCH/REALTIME) |
| 障害対応 | Runbook + SNS 通知 + エスカレーションフロー |
| 変更管理 | CloudFormation 更新手順 + テスト環境での事前検証 |
| バックアップ | FSx SnapMirror + S3 バージョニング（Output Bucket） |
| パッチ管理 | Lambda Runtime 更新 + EC2 AMI 更新（EC2 構成の場合） |
| コスト管理 | 月次コストレビュー + Budget Alert |

### ガバナンス対応
| 項目 | 対応内容 |
|------|---------|
| Human-in-the-loop | 高リスク AI 出力のレビュー体制構築 |
| 監査証跡 | CloudTrail + DynamoDB Lineage の保管期間設定 |
| データリネージ | 処理履歴の追跡可能性確保 |
| インシデント対応 | AI 誤出力時の対応手順定義 |

---

## Phase C: 庁内/組織展開（3-6 ヶ月）

### 目的
- 複数部署・複数ワークロードへの展開
- マルチアカウント構成への移行
- 組織全体のガバナンス体制確立

### 成果物
- [ ] マルチアカウント構成（StackSets デプロイ）
- [ ] 複数 UC の本番運用開始
- [ ] 組織横断ダッシュボード
- [ ] コンプライアンス対応完了（FISC/個人情報保護法等）
- [ ] 定期的な AI 出力品質レビュー体制
- [ ] 運用改善サイクルの確立
- [ ] 次年度予算計画への反映

### 展開パターン

```
[Phase A: 1 部署 × 1 UC]
    ↓
[Phase B: 1 部署 × 2-3 UC]
    ↓
[Phase C-1: 2-3 部署 × 各 1-2 UC]
    ↓
[Phase C-2: 組織全体 × 標準化]
```

### マルチアカウント構成

```
Management Account
├── Shared Services Account (監視・ログ集約)
├── Workload Account A (部署 A)
│   ├── UC1 (法務・コンプライアンス)
│   └── UC2 (金融・IDP)
├── Workload Account B (部署 B)
│   ├── UC5 (医療・DICOM)
│   └── UC16 (公文書アーカイブ)
└── Security Account (CloudTrail 集約・GuardDuty)
```

---

## 公共セクター固有の考慮事項

### 領域別ミニシナリオ

#### 自治体
| シナリオ | 対応 UC | 期待効果 | 主な関係者 |
|---------|---------|---------|-----------|
| 公文書アーカイブの自動分類・検索 | UC16 | 情報公開請求対応時間の短縮 | 総務課、情報政策課、文書管理担当 |
| 監査資料の自動整理・メタデータ付与 | UC1 | 監査準備工数の削減 | 監査委員事務局、情報システム課 |
| 防災・都市計画データの地理空間分析 | UC17 | 災害リスク評価の迅速化 | 防災課、都市計画課、GIS 担当 |

#### 教育機関
| シナリオ | 対応 UC | 期待効果 | 主な関係者 |
|---------|---------|---------|-----------|
| 校務文書の自動分類・保管期限管理 | UC1, UC16 | 教職員の事務負荷軽減 | 教育委員会、学校事務、情報担当 |
| 教材・学習データの整理・検索性向上 | UC13 | 教材再利用率の向上 | 教務主任、ICT 支援員 |
| 教育データ分析レポートの自動生成 | UC13 | データに基づく教育改善 | 教育委員会、データ分析担当 |

#### 医療機関
| シナリオ | 対応 UC | 期待効果 | 主な関係者 |
|---------|---------|---------|-----------|
| DICOM 画像の自動分類・メタデータ整理 | UC5 | 放射線科の検索効率向上 | 放射線科、医療情報部、PACS 管理者 |
| 退院サマリー・診療記録の要約支援 | UC2 | 医師の文書作成負荷軽減 | 診療情報管理士、医療情報部 |
| 研究データの分類・匿名化レビュー | UC7, UC5 | 研究データ利活用の促進 | 研究支援センター、倫理委員会、個人情報保護担当 |

> **注意**: 上記シナリオの AI 処理出力は意思決定支援であり、医療診断・行政処分・教育評価の最終判断は人間が行います。

### Cache-Aware Routing / Read-Path Resilience チェックポイント

FlexCache Anycast/DR パターン（FC1）を検討する場合の追加確認項目:

| 項目 | 確認内容 |
|------|---------|
| 正本データソース | どのボリュームが authoritative source か |
| キャッシュアクセスポリシー | 誰がキャッシュボリュームにアクセスできるか |
| フェイルオーバー判断者 | Decision owner は誰か |
| 承認フロー | ルート変更の承認プロセス |
| ルート変更監査証跡 | 変更記録の保持・参照方法 |
| 監査証跡レビュー担当 | 誰が監査証跡を確認するか |
| 運用責任者 | 日常運用・障害対応の責任者 |

### 調達・契約
| 項目 | 考慮事項 |
|------|---------|
| AWS 利用契約 | 政府機関向け契約条件の確認 |
| データ所在地 | 国内リージョン（ap-northeast-1）での処理確認 |
| クロスリージョン | Textract/Comprehend Medical の利用可否判断 |
| 第三者認証 | SOC 2, ISO 27001, ISMAP 等の確認 |

### 規制対応
| 規制 | 対象 UC | 主な要件 |
|------|---------|---------|
| 個人情報保護法 | 全 UC | 利用目的明示、安全管理措置 |
| 行政機関個人情報保護法 | UC16 | 行政文書の適正管理 |
| 医療情報ガイドライン | UC5 | 3 省 2 ガイドライン準拠 |
| FISC 安全対策基準 | UC2, UC14 | 金融機関向けセキュリティ |
| 教育データ利活用 | UC13 | 学習データの適正管理 |

### 人材育成
| フェーズ | 必要スキル | 育成方法 |
|---------|-----------|---------|
| Phase A | CloudFormation 基礎、S3 AP 概念理解 | AWS Training + PoC ハンズオン |
| Phase B | 運用監視、障害対応、セキュリティ | Runbook 訓練 + OJT |
| Phase C | マルチアカウント設計、CI/CD | AWS SA 支援 + パートナー協力 |

---

## 参考リンク

- [Governance Checklist](governance-checklist.md)
- [Production Readiness](production-readiness.md)
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)
- [Deployment Profiles](deployment-profiles.md)
- [Customer Discovery Template](customer-discovery-template.md)
