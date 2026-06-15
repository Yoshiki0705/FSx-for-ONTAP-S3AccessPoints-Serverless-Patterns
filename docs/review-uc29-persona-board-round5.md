# UC29 ペルソナレビューボード（Round 5 — フォローアップ検証）

> Round 4 の Must Fix 反映を再レビュー（改善ループ）。役割ベース記述・エビデンスティア明記。
> 公開 push 文章に実在/プロジェクト内ペルソナ名を含めない。

エビデンスティア: **[公開]** / **[プロジェクト]** / **[アーキタイプ]**

---

## Summary

- Round 4 指摘の検証結果: イベント駆動 5 件中 4 件 RESOLVED、1 件は重要な残課題（R1）を新規検出 → **本ラウンドで修正**。
- セキュリティ 5 件: 共有ロール権限・fsxadmin ドリフトは RESOLVED、秘密漏洩は部分対応 → **AD admin もローテーションし完全失効**。
- 対応後評価: **APPROVE WITH COMMENTS**（teardown とフォローアップ Should を残す）

---

## 1. イベント駆動アーキテクチャ レンズ（フォローアップ）— [公開]+[アーキタイプ]

### Round 4 指摘の検証
- lost-update window + 安全網の主張 → **RESOLVED**（docstring/demo-guide で B 併用必須を明記、誇張なし）
- ConflictException / エラー再送出 → **RESOLVED**（handler レベル）
- DLQ → **RESOLVED**（DLQ + QueuePolicy + ターゲット DeadLetterConfig + RetryPolicy）
- スキーマ不一致 → **RESOLVED**（公式スキーマに統一、契約テスト追加）
- テスト不足 → **RESOLVED**（11 テスト、conflict/throttle/reraise/契約をカバー）

### 新規検出（R1、重要）→ 本ラウンドで修正
- **DLQ セマンティクス不一致**: EventBridge→Lambda は非同期呼び出し。ターゲットの
  `RetryPolicy`/`DeadLetterConfig` は **配信失敗**のみを捕捉し、再送出された**実行失敗**は捕捉しない。
  実行失敗の捕捉には Lambda の `EventInvokeConfig.OnFailure`（または関数 DeadLetterConfig）が必要だが未設定だった。
  docstring と demo-guide が「OnFailure DLQ で捕捉」と**過大表現**していた。
- ✅ **修正**: `KbTriggerFunction` に `EventInvokeConfig`（MaximumRetryAttempts=2 + OnFailure→`KbTriggerDLQ`）を追加。
  実行ロールに `sqs:SendMessage`（DLQ 宛）を付与。docstring/demo-guide を「配信失敗=EventBridge DLQ /
  実行失敗=Lambda OnFailure DLQ / 追加で CloudWatch Errors アラーム + シナリオ B リコンサイル」と正確化。

### 残（Should / フォローアップ）
- バースト時の SQS バッファ + Lambda 予約並列度、`put_metric_data` の EMF 化
- 二次パスフィルタの substring vs prefix（EventBridge ルールが一次・authoritative のため低優先）

---

## 2. セキュリティ / 運用衛生 レンズ（フォローアップ）— [アーキタイプ]+[プロジェクト]

### Round 4 指摘の検証
- 共有ロール権限漏れ → **RESOLVED**（`AmazonS3ReadOnlyAccess` をデタッチ、残りは SSM コア + Directory Service のみ）
- fsxadmin ドリフト → **RESOLVED**（新ランダム値にローテーション + Secrets Manager 整合）
- 秘密漏洩（SSM 履歴） → 当初**部分対応**（fsxadmin の漏洩値は失効、AD admin は未対応だった）
  - ✅ **本ラウンドで AD admin パスワードもローテーション**（`ds reset-user-password`）→ SSM 履歴の AD admin 値も失効
  - 注: SSM コマンド履歴 / CloudTrail のエントリ自体は不変（保持期間で失効）。今後は秘密を SSM パラメータに渡さない
- 検証ドキュメントの実 ID → **RESOLVED**（`verification-results.md` は gitignore 済み、公開されない）
- コミット安全性 → blog-draft / review-round4 を確認: 実アカウント ID/リソース ID なし。
  `UC29DEMO\Admin` の環境固有識別子を**プレースホルダーに修正済み**

### 残（teardown による最終クローズ）
- 検証リソース（Managed AD / AOSS / Windows EC2 / 新規 SVM・ボリューム / 検証用バス / sample バケット）の teardown
- teardown 完了をもってセキュリティ残課題（秘密の最終失効・コスト停止）をクローズ

---

## Round 5 Action Items

### Must Fix（本ラウンドで反映済み）
- [x] R1: Lambda `EventInvokeConfig.OnFailure` で実行失敗を DLQ 捕捉、ロールに `sqs:SendMessage` 付与
- [x] docstring/demo-guide の DLQ カバレッジ表現を正確化（配信失敗 vs 実行失敗）
- [x] AD admin パスワードのローテーション（SSM 漏洩値の完全失効）
- [x] review ドキュメントの環境固有識別子をプレースホルダー化

### フォローアップ（Should / 要判断）
- [ ] 検証リソースの teardown（コスト停止 + 秘密の最終失効）
- [ ] バースト制御（SQS バッファ / 予約並列度 / EMF）
- [ ] 秘密を実行時取得に変更、Windows identity を最小権限 AD サービスアカウントに

---

## Final Recommendation

**APPROVE WITH COMMENTS** — Round 4/5 の Must Fix を全て反映。イベント駆動の失敗捕捉は
配信失敗（EventBridge DLQ）と実行失敗（Lambda OnFailure DLQ）の両層でカバー。
秘密は両方ローテーション済み。残るは検証リソースの teardown（コスト停止）と Should フォローアップ。
