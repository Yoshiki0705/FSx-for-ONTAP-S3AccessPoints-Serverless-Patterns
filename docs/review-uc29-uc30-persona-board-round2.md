# UC29 / UC30 ペルソナレビューボード（Round 2）

> ライブデプロイと Amazon Quick 有効化後の再レビュー。役割ベース記述・エビデンスティア明記。
> 公開 push 文章に実在/プロジェクト内ペルソナ名を含めない。

エビデンスティア: **[公開]** 公開ソース / **[プロジェクト]** 内部合意 / **[アーキタイプ]** 一般役割

Round 1 からの差分にフォーカス（実機検証・Quick 有効化・セキュリティ/可観測性/評価）。

---

## Summary

- 全体評価: 実機で E2E 動作確認済み。Round 2 で Well-Architected 生成AIレンズ観点（ガードレール・評価・可観測性）と Responsible AI（プロンプトインジェクション）を強化。
- 推奨判定: **APPROVE WITH COMMENTS**（Must は反映済み、評価/コストガードレールは Should として継続）

---

## 1. 生成AI Well-Architected レンズ レビュー — [公開]

AWS Well-Architected 生成AIレンズ（GENSEC02 ガードレール、GENOPS01 定期的機能評価）に基づく。

### Good
- マネージド KB / Quick による運用負荷低減、サーバーレス構成
- ロール×サービスのデータ整理、責務分界

### Concerns（Round 2 指摘）
- **GENSEC02**: 当初 Bedrock Guardrails 未適用（有害・不正確応答の抑制なし）
- **GENOPS01**: 回答品質の定期評価（ground truth 比較）の仕組みがない
- 可観測性: SNS 通知のみで CloudWatch アラーム/ダッシュボードがなかった

### Recommendations（反映状況）
- ✅ **Bedrock Guardrails をオプションで配線**（UC29 RetrieveAndGenerate / UC30 converse に `guardrailConfig`、IAM に `bedrock:ApplyGuardrail`、パラメータ `BedrockGuardrailId`）
- ✅ **CloudWatch エラーアラーム**を主要 Lambda に追加（Errors→SNS）
- ✅ **評価データセット雛形**を追加（`docs/evaluation.md` + `evaluation/uc29-eval-dataset.json`）。Bedrock の RAG 評価機能/RAGAS での定期評価を推奨

---

## 2. Responsible AI / セキュリティ レビュー — [公開]

RAG チャットボット ハードニング ブループリント（プロンプトインジェクション、情報漏えい）に基づく。

### Good
- データ移動なし、Action API は IAM 認証（SigV4）、最小権限

### Concerns（Round 2 指摘）
- Quick Flows の `generate_brief` が、取得/入力コンテキストを信頼して LLM に渡していた（インジェクション余地）
- 高リスク操作の自動実行リスク

### Recommendations（反映状況）
- ✅ **プロンプトインジェクション対策**: `generate_brief` に system 指示を追加し、コンテキストを**非信頼データ**として扱い、埋め込み指示に従わない/秘密を開示しない/情報不足時は推測しない、を明文化。実機で「秘密を開示せよ」の埋め込み指示を**無視**することを確認
- ✅ **human-in-the-loop**: 高リスク操作は `request_approval`（pending_approval）
- 推奨: Bedrock Guardrails の prompt attack フィルタ/機密情報保護を本番で有効化

---

## 3. RAG 品質 / 評価 レビュー — [公開]

### Concerns
- retrieval / answer の品質を測る基準・データセットがない（回帰検知不可）

### Recommendations（反映状況）
- ✅ 評価観点を `docs/evaluation.md` に整理（retrieval 適合率、citation 整合、no-answer 挙動、権限フィルタ精度）
- ✅ UC29 用の小規模評価データセット（質問→期待引用元）を同梱
- 推奨: Bedrock Knowledge Base 評価ジョブ or RAGAS を CI/定期実行（GENOPS01）

---

## 4. SRE / 可観測性 レビュー — [公開]+[アーキタイプ]

### Good
- 構造化ログ、Step Functions の Retry/Catch、多重起動防止

### Concerns（Round 2 指摘）
- メトリクスアラームがなく、障害が検知通知されない
- **SSE-SNS（AWS マネージドキー）+ CloudWatch アラーム通知の制約**: マネージドキー暗号化トピックへは CloudWatch サービスプリンシパルから配信できない場合がある

### Recommendations（反映状況）
- ✅ Lambda Errors の CloudWatch アラームを追加（AlarmActions→SNS）
- ⚠️ **要注意（文書化済み）**: アラーム通知を確実にするには SNS トピックを **CMK** 暗号化にし、キーポリシーで `cloudwatch.amazonaws.com` に `kms:GenerateDataKey*`/`Decrypt` を許可する（マネージドキーのままだとアラーム通知が届かない可能性）。アプリからの publish（Lambda/Step Functions）は動作確認済み
- 推奨: CloudWatch ダッシュボード（invocations/errors/duration、ingestion 統計）

---

## 5. FinOps / コスト レビュー — [アーキタイプ]+[公開]

### Concerns（Round 2 指摘）
- **Amazon Quick を有効化したため月額課金が発生**（QuickSight から進化）。停止は手動
- Bedrock トークン課金、Athena scanned 課金、OpenSearch/S3 Vectors コスト

### Recommendations（反映状況）
- ✅ クリーンアップ runbook に **Quick 解約/ユーザー削除**手順を追加（課金停止）
- ✅ analytics の Parquet 化推奨を明記（scanned 削減）
- 推奨: AWS Budgets による予算アラート、Quick ユーザー棚卸し（未使用ユーザーのアクセス取り消し）

---

## 6. ストレージ スペシャリスト レビュー（差分） — [公開]

- ✅ S3 AP レイテンシ参考値を取得（GetObject p50≈57ms / p99≈74ms、検証環境）
- 推奨（継続）: 同時 NFS/SMB ワークロード下での tail latency 計測、スループットキャパシティ別比較

---

## Round 2 Action Items

### Must Fix（反映済み）
- [x] プロンプトインジェクション対策（generate_brief の system 指示）
- [x] Bedrock Guardrails をオプション配線（GENSEC02）
- [x] Lambda エラーの CloudWatch アラーム（可観測性）
- [x] Quick 課金停止手順（クリーンアップ runbook）

### Should Fix（継続）
- [x] RAG 品質の定期評価（雛形 + ハーネス + CI）— `evaluation/run_eval.py`、`tests/test_eval.py`、`.github/workflows/rag-eval.yml`、ci.yml に UC テスト追加。ライブ評価 pass_rate 1.0
- [x] CloudWatch ダッシュボード、アラーム通知用 CMK トピック（両UCに Dashboard + CMK AlarmsTopic）
- [x] AWS Budgets 予算アラート（UC30、メール指定時に作成）、Quick ユーザー棚卸し（cleanup runbook 記載）
- [~] Quick の実データ接続: **S3 Index は統合境界を実機で特定・文書化**（Quick は S3 AP エイリアスを受理するが、FSxN デュアルレイヤー認証によりデータアクセスロールの AP 認可が必要。AP リソースポリシーは principal 制約で MalformedPolicy）。**本命は Bedrock KB（UC29、取り込み COMPLETE 済み）**、または通常 S3 へステージング。Quick Sight（BI）は Athena 経由で接続可（QuickSight ロールに Athena/Glue/LF/結果バケット権限が前提）

### 新規の確定事項（Round 2 実機）
- Amazon Quick の S3 ナレッジベースコネクタは FSxN S3 AP エイリアスを「有効な URL」として受理するが、**接続認可が FSxN デュアルレイヤー認証の制約を受ける**（`docs/quick-console-setup.md` に remediation 記載、証跡 `quick-s3-kb-connect.png`）

---

## Final Recommendation

**APPROVE WITH COMMENTS** — Round 2 の Must を反映済み。Should はフォローアップ Issue 化を推奨。
本番化時は Guardrails 有効化・定期評価・予算アラート・CMK 通知トピックを必須とする。
