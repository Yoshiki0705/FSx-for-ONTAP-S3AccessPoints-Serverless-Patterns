# UC29 ペルソナレビューボード（Round 4）

> 対象: UC29 の新規作業（シナリオ C = FPolicy イベント駆動、リテラル Windows AD ドラッグ&ドロップ検証、
> KB 再作成、ブログドラフト）。Round 1-3 で未カバーの観点を、独立レビュー（イベント駆動アーキ / セキュリティ・運用衛生）で実施。
> 役割ベース記述・エビデンスティア明記。公開 push 文章に実在/プロジェクト内ペルソナ名を含めない。

エビデンスティア: **[公開]** 公開ソース / **[プロジェクト]** 内部合意 / **[アーキタイプ]** 一般役割

---

## Summary

- 全体評価（初回提出時）: **REQUEST CHANGES**。ハッピーパスは動作するが、イベント駆動の取りこぼし、
  エラーハンドリング、運用衛生（共有ロール権限漏れ・秘密の取り扱い）に実質的な問題。
- 対応後評価: **APPROVE WITH COMMENTS**（Must Fix を反映。下記参照）

---

## 1. イベント駆動アーキテクチャ レンズ — [アーキタイプ]+[公開]

### Concerns（指摘）
- **lost-update window**: 進行中ジョブ時にイベントを破棄。Ingestion はジョブ開始時の全走査のため、
  実行中に追加されたファイルは取り込まれない。docstring は「次イベント or 定期同期で補完」と記載していたが、
  **シナリオ C に Scheduler はない**（B の機能）→ 主張する安全網が存在しなかった。
- **エラーハンドリング**: `StartIngestionJob` 失敗を dict で return しており、Lambda 非同期リトライ/DLQ が
  発火しない（エラーが握り潰される）。ConflictException を終端エラー扱いしていた。
- **DLQ 不在**: EventBridge → Lambda ターゲットに DLQ/リトライポリシーがなかった。
- **スキーマ不一致**: demo-guide の C-2/C-3 JSON が `operation`/`path`/`FPolicyFileEvent` を使用。実装と
  公式スキーマ（`operation_type`/`file_path`/`FPolicy File Operation`）と乖離。ドキュメントどおりだと全イベントが
  誤スキップされる。
- **テスト不足**: lost-update / ConflictException / 再送出 / 公式スキーマ契約のテストがない。

### Recommendations → 対応状況
- ✅ **lost-update**: docstring と demo-guide/blog を修正。「シナリオ C は単独で取りこぼしゼロを保証しない。
  **シナリオ B（定期リコンサイル）との併用を必須**」と明記。
- ✅ **エラーハンドリング**: ConflictException → 進行中スキップ（リトライ不要）、その他の例外は**再送出**して
  Lambda 非同期リトライ + DLQ を発火させるよう修正。
- ✅ **DLQ**: `KbTriggerDLQ`（SQS、14日保持、SSE）+ EventBridge ターゲットに `DeadLetterConfig` +
  `RetryPolicy`（3回 / 1時間）を追加。
- ✅ **スキーマ修正**: demo-guide の JSON を公式スキーマに統一。EventBridge パターンの prefix も `ai_knowledge`（FPolicy パス）に統一。
- ✅ **テスト追加**: ConflictException スキップ / 予期せぬ例外再送出 / ThrottlingException 再送出 / 公式スキーマ契約（計 11 テスト、全パス）。
- ⏳ **Should（フォローアップ）**: バースト時の SQS バッファ + Lambda 予約並列度、`put_metric_data` の非同期化/EMF 化。

---

## 2. セキュリティ / 運用衛生 レンズ — [アーキタイプ]+[プロジェクト]

### Concerns（指摘）
- **共有ロール権限漏れ（LIVE）**: 検証中に `AmazonS3ReadOnlyAccess` を**共有インスタンスプロファイルロール**
  `AmazonSSMDirectoryServiceInstanceProfileRole` にアタッチ → そのロールを使う全インスタンスにアカウント全体の
  S3 読み取りを付与。未解除のまま。
- **SSM コマンド履歴に平文秘密**: AD admin / fsxadmin パスワードを RunPowerShellScript パラメータに平文で渡した
  → SSM 履歴/CloudTrail に残存。漏洩扱いすべき。
- **fsxadmin リセットのドリフト**: 共有 FS の fsxadmin を既知値にリセットし Secrets Manager と不整合。
- **検証ドキュメントに実 ID**: `verification-results.md` にアカウント ID/リソース ID 等。
- **コスト残存**: Managed AD / AOSS / Windows EC2 / 新規 SVM・ボリューム / 検証用バス / sample バケット。

### Recommendations → 対応状況
- ✅ **共有ロール権限漏れ**: `AmazonS3ReadOnlyAccess` を共有ロールから**即時デタッチ**（残りは SSM コア + Directory Service のみ）。
- ✅ **秘密漏洩対応**: fsxadmin を**新しいランダム値にローテーション**し、Secrets Manager を**整合**（SSM 履歴に残った値は無効化）。
- ✅ **検証ドキュメント**: `verification-results.md` は `**/docs/verification-results.md` で **gitignore 済み**（公開 push されない）。実 ID はローカルのみ。
- ⏳ **AD admin パスワード**: 使い捨て専用 AD のため、**teardown（AD/EC2 削除）が最終緩和策**。クリーンアップ runbook に記載。
- ⏳ **Should（フォローアップ）**: 秘密を SSM パラメータに渡さず実行時に Secrets Manager から取得 /
  Windows identity を最小権限の AD サービスアカウントに（現在は AD 管理者アカウントを使用）/ NetworkOrigin の再検討 /
  検証リソースの teardown 実行。

---

## Round 4 Action Items

### Must Fix（反映済み）
- [x] lost-update window の安全網（シナリオ B 併用必須）を docstring/demo-guide/blog に明記
- [x] エラーハンドリング修正（ConflictException スキップ / 他例外は再送出 → リトライ/DLQ 発火）
- [x] EventBridge ターゲットに DLQ + RetryPolicy を追加
- [x] demo-guide のイベントスキーマを公式スキーマに統一
- [x] テスト追加（11 テスト全パス）
- [x] 共有ロールから過剰権限ポリシーをデタッチ（LIVE 修正）
- [x] 漏洩した fsxadmin をローテーション + Secrets Manager 整合

### Should Fix（フォローアップ Issue 推奨）
- [ ] バースト制御（SQS バッファ / Lambda 予約並列度 / EMF メトリクス）
- [ ] 秘密を SSM パラメータに渡さない（実行時取得）/ Windows identity を最小権限 AD サービスアカウントに
- [ ] 検証リソース（AD / Windows EC2 / AOSS / 検証用バス / sample バケット）の teardown 実行
- [ ] AD admin パスワードの teardown による失効

---

## Final Recommendation

**APPROVE WITH COMMENTS** — Round 4 の Must Fix を全て反映。Should Fix はフォローアップ。
本番化時はシナリオ B 併用（取りこぼし防止）と検証リソースの teardown を必須とする。
