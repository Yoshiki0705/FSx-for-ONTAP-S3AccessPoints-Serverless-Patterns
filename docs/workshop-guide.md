# Partner Workshop Guide — 顧客向け PoC ワークショップ

🌐 **Language / 言語**: [日本語](workshop-guide.md) | [English](workshop-guide.en.md)

## 概要

パートナー/SI が顧客向けに実施する 1 日ワークショップのガイドです。

---

## ワークショップ構成（1 日 / 6 時間）

| 時間 | セッション | 内容 | 担当 |
|------|-----------|------|------|
| 09:00-09:30 | オープニング | 課題ヒアリング、ゴール設定 | パートナー |
| 09:30-10:30 | Session 1 | アーキテクチャ概要 + S3AP 認可モデル | パートナー |
| 10:30-10:45 | 休憩 | — | — |
| 10:45-12:00 | Session 2 | ハンズオン: UC テンプレートデプロイ | 参加者 |
| 12:00-13:00 | 昼食 | — | — |
| 13:00-14:30 | Session 3 | ハンズオン: FPolicy Event-Driven パイプライン | 参加者 |
| 14:30-14:45 | 休憩 | — | — |
| 14:45-15:45 | Session 4 | セキュリティ・ガバナンスレビュー | パートナー + 顧客 |
| 15:45-16:30 | Session 5 | 本番化計画 + 次ステップ | 全員 |
| 16:30-17:00 | クロージング | Q&A、アクションアイテム整理 | パートナー |

### 推奨参加者ロール

| ロール | 参加セッション | 役割 |
|--------|-------------|------|
| Storage / Infrastructure Owner | Session 1-3 | FSx 環境・ネットワーク確認 |
| Application Owner | Session 1-2, 5 | 業務要件・対象データ確認 |
| Security / Compliance Reviewer | Session 1, 4 | 認可モデル・ガバナンス確認 |
| Data / Analytics Owner | Session 2-3 | AI/ML 処理要件・出力先確認 |
| Operations Team | Session 3, 5 | 運用設計・障害対応確認 |
| Partner Delivery Lead | 全セッション | ファシリテーション・次ステップ整理 |
| Business Sponsor | Session 1, 5 | ビジネス価値・予算・優先度判断 |

---

## Session 1: アーキテクチャ概要（60 分）

### アジェンダ
1. FSx for ONTAP S3 Access Points とは（10 分）
2. デュアルレイヤー認可モデル（15 分）
3. Trigger Mode: POLLING / EVENT_DRIVEN / HYBRID（15 分）
4. ユースケース選択（10 分）
5. Q&A（10 分）

### 使用資料
- [S3AP Authorization Model](s3ap-authorization-model.md)
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
- README アーキテクチャ図

---

## Session 2: ハンズオン — UC テンプレートデプロイ（75 分）

### 前提条件
- AWS アカウント（参加者各自 or 共有）
- FSx for ONTAP ファイルシステム（事前準備済み）
- S3 Access Point（事前作成済み）
- テストファイル（NFS/SMB 経由で配置済み）

### 手順
1. CloudFormation テンプレートのデプロイ（15 分）
2. EventBridge Scheduler の確認（5 分）
3. 手動実行で動作確認（15 分）
4. CloudWatch ログ・メトリクスの確認（15 分）
5. 結果の確認と議論（25 分）

### 推奨 UC（初回ワークショップ）
- **UC1 (legal-compliance)**: 最もシンプル、Bedrock + Athena
- **UC11 (retail-catalog)**: Rekognition + Bedrock、視覚的に分かりやすい

---

## Session 3: ハンズオン — FPolicy Event-Driven（90 分）

### 手順
1. FPolicy Server デプロイ（Fargate or EC2）（20 分）
2. ONTAP FPolicy 設定（external-engine, policy, scope）（20 分）
3. NFS ファイル作成 → SQS → EventBridge 到達確認（20 分）
4. IP Updater Lambda の動作確認（Fargate の場合）（10 分）
5. 障害シミュレーション（タスク停止 → 再起動）（20 分）

### 注意事項
- NFSv4.2 は FPolicy 非対応。`vers=4.1` を明示的に指定
- Fargate タスク再起動中（30-60 秒）はイベントロスが発生
- Persistent Store は別途設定が必要（ワークショップでは説明のみ）

---

## Session 4: セキュリティ・ガバナンスレビュー（60 分）

### アジェンダ
1. [Governance Checklist](governance-checklist.md) の確認（20 分）
2. データ分類の議論（15 分）
3. Human-in-the-loop 要否の判断（10 分）
4. コンプライアンス要件の確認（15 分）

### 顧客側参加者（推奨）
- 情報セキュリティ担当
- コンプライアンス担当
- データ管理責任者

---

## Session 5: 本番化計画（45 分）

### アジェンダ
1. [Production Readiness](production-readiness.md) の Level 確認（10 分）
2. [Deployment Profile](deployment-profiles.md) の選択（10 分）
3. 成功基準の定義（10 分）
4. タイムライン・次ステップの合意（15 分）

### 成果物テンプレート

```markdown
## ワークショップ成果

### 選択した UC: ___
### Trigger Mode: POLLING / EVENT_DRIVEN / HYBRID
### Deployment Profile: PoC / Production / Compliance
### 成功基準:
- 検知レイテンシ: ___
- 処理スループット: ___
- コスト上限: ___
- 可用性目標: ___

### 次ステップ:
1. ___（担当: ___, 期限: ___）
2. ___（担当: ___, 期限: ___）
3. ___（担当: ___, 期限: ___）
```

---

## 事前準備チェックリスト（パートナー向け）

### 1 週間前
- [ ] 顧客の AWS アカウント確認
- [ ] FSx for ONTAP ファイルシステムの準備
- [ ] S3 Access Point の作成
- [ ] テストファイルの配置
- [ ] ネットワーク到達性の確認（VPC, Security Group）
- [ ] [Customer Discovery Template](customer-discovery-template.md) でヒアリング実施

### 前日
- [ ] CloudFormation テンプレートの事前デプロイテスト
- [ ] FPolicy Server の動作確認
- [ ] 参加者への事前資料送付
- [ ] 会議室 / リモート環境の確認

---

## 参考リンク

- [Choose Your Path](../README.md#choose-your-path)
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md)
- [Customer Discovery Template](customer-discovery-template.md)
- [Production Readiness](production-readiness.md)
- [Governance Checklist](governance-checklist.md)
