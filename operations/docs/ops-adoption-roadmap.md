# 運用最適化パターン — 段階的導入ロードマップ

---

## 導入フェーズ

### Phase 1: 可視化 (Week 1-2)

**目標**: 現状を把握する。手動運用は変えない。

1. **OPS1 (capacity-rightsizing)** を `AutomationLevel=0` でデプロイ
2. CloudWatch Dashboard で容量・スループット使用率を確認
3. 日次レポート (S3 JSON/HTML) で推奨内容を確認
4. 閾値 (`ThresholdPercent`) を環境に合わせて調整

**成功基準**: 全ボリュームの使用率が日次で可視化されている

---

### Phase 2: アラート (Week 3-4)

**目標**: 問題を見逃さない仕組みを作る。

1. OPS1 を `AutomationLevel=1` に変更
2. **OPS4 (snapshot-lifecycle)** を `AutomationLevel=0` でデプロイ
3. SNS アラートの配信先設定 (メール / Slack / PagerDuty)
4. アラートノイズの調整 (閾値微調整)

**成功基準**: 80% 超過時に運用チームが通知を受け取る

---

### Phase 3: 推奨ベース運用 (Month 2)

**目標**: AI 推奨に基づいて手動で最適化を実行する。

1. **OPS3 (tiering-optimizer)** を `AutomationLevel=1` でデプロイ
2. Bedrock AI 推奨を有効化 (`EnableBedrockSummary=true`)
3. 推奨に基づいてティアリングポリシー・クーリング期間を手動調整
4. コスト削減効果を月次で計測

**成功基準**: ティアリング最適化でストレージコスト 10-30% 削減

---

### Phase 4: 承認ベース自動化 (Month 3-4)

**目標**: Human-in-the-loop で安全に自動化する。

1. OPS1 を `AutomationLevel=2` に変更
2. OPS4 を `AutomationLevel=2` に変更
3. SSM Change Calendar を設定 (月末/年度末の変更禁止期間)
4. 承認ワークフロー (SQS + TaskToken) の運用フロー確立

**成功基準**: 承認後の自動実行が月 N 回発生。手動作業ゼロ。

---

### Phase 5: FinOps 統合 (Month 5+)

**目標**: コスト配賦と予測で経営層に可視性を提供する。

1. **OPS5 (cost-optimization)** をデプロイ
2. ボリューム→チーム配賦テーブルを設定
3. 月次コストレポートを経営層に配信
4. AWS Budgets との連携

---

### Phase 6: 完全自動化 (Month 6+ / 成熟組織のみ)

**目標**: ガードレール範囲内で人手を介さず最適化。

1. 選択したパターンを `AutomationLevel=3` に変更
2. ガードレール設定 (最大リサイズ量、変更頻度上限)
3. エラーバジェット管理 (false positive 率 < 5%)
4. GameDay で異常シナリオを検証

---

## GUI 運用からの移行マップ

| 従来の GUI 操作 | OPS パターンの代替 | いつ移行するか |
|---------------|-----------------|--------------|
| コンソールで容量を目視確認 | OPS1 Dashboard + 日次レポート | Phase 1 |
| 手動でスループットティアを変更 | OPS1 Level 2 (承認後自動) | Phase 4 |
| System Manager でスナップショット削除 | OPS4 Level 2 (Human Review) | Phase 4 |
| 手動でティアリングポリシー変更 | OPS3 Level 2 (推奨→承認→実行) | Phase 4 |
| Excel でコスト集計 | OPS5 自動レポート + 配賦 | Phase 5 |
