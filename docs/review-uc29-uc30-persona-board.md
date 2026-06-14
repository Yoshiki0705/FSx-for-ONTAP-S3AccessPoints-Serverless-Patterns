# UC29 / UC30 ペルソナレビューボード

> 本レビューは内部作業ドキュメント。ペルソナは**役割ベース**で記述し、各指摘に**エビデンスティア**を付す。
> 公開リポジトリへ push する文章には実在・プロジェクト内ペルソナ名を含めない（role-based 記述のみ）。

エビデンスティア凡例:
- **[公開]** 公開ソースで検証可能（AWS 公式 doc/blog 等）
- **[プロジェクト]** 本プロジェクト内合意（公開検証不可）
- **[アーキタイプ]** Well-Architected 等の一般的役割

レビュー対象:
- UC29 `genai-kb-selfservice-curation`（マネージド Bedrock KB セルフサービス）
- UC30 `genai-quick-agentic-workspace`（Amazon Quick エージェント型ワークスペース）

---

## Summary

- 全体評価: 設計・実装・実機検証ともに良好。2UC の責務分離（自助投入 / エージェント型活用）が明確。
- 主なリスク: 権限制御の表現、S3 Vectors メタデータ制約、Action API 認証、Lake Formation/コスト運用。
- 推奨判定: **APPROVE WITH COMMENTS**（Must Fix を反映の上で公開可）

---

## 1. Storage Specialist（FSxN / S3 AP）レンズ — [公開]

公開セッション（Storage Specialist による S3 性能/アクセスパターン解説）に基づく。

### Good
- 既存 FSxN・S3 AP を再利用し、データ移動なし（正本維持）を徹底
- NetworkOrigin=Internet を選定理由つきで明示（ローカル投入・非VPC Lambda 到達性）

### Concerns
- FSxN スループットは NFS/SMB/S3AP 共有。SMB 書き込みと AI 取り込み読み取りの競合の定量評価がない
- 大量ファイル時の S3 AP List/Get の tail latency / スループット影響が未計測

### Recommendations
- ベンチマーク steering 準拠で P50/P95/P99 と同時ワークロード有無を記録
- 取り込みは差分・バッチ化（S3 Vectors は最大 500 vectors/req バッチ推奨）[公開]

---

## 2. GenAI / RAG アーキテクト（Bedrock KB / S3 Vectors）— [公開]+[アーキタイプ]

### Good
- マネージド KB（Pattern C）採用で運用負荷最小化。FC3（カスタム）との使い分けが明確
- 実機で ingestion COMPLETE（20/20）・引用つき回答を確認

### Concerns
- 初回 ingestion が **S3 Vectors のフィルタ可能メタデータ 2048 バイト制約**で失敗（既存 industry-packs）。再利用環境の落とし穴
- 「権限制御は対象外」の当初表現が、メタデータフィルタや Quick 文書 ACL の存在を踏まえると後退的

### Recommendations（実装反映済み）
- ✅ Query Lambda に **メタデータフィルタ（role/任意 filter）** を追加。`<file>.metadata.json` サンプルを同梱
- ✅ 2048 バイト/10KB/フィルタ選択性と recall の注意を README に明記 [公開]
- 単一 KB 多テナントは「S3 フォルダ構造 + メタデータフィルタ」が AWS 推奨パターン [公開]

---

## 3. Amazon Quick / BI スペシャリスト — [公開]

### Good
- Quick の Index/Sight/Flows/Research を S3 AP データに対応づけ、ロール×サービスで整理
- Athena 経由 BI を実機確認（stage 別集計・重大度別 MTTR）

### Concerns
- Quick 本体のデータソース接続がコンソール手動で、デモ手順の再現性に幅
- Quick の **account/role/user 3階層のカスタム権限**への言及が不足していた

### Recommendations（一部反映済み）
- ✅ **Amazon Quick S3 KB の文書レベル ACL** を UC30 に明記（利用者別可視範囲を Quick 側で実現）[公開]
- Quick カスタム権限（user>role>account 優先）とロールフォルダの対応表を追補 [公開]
- Quick 接続手順のスクリーンショット/ステップ化（再現性向上）

---

## 4. セキュリティ / IAM エンジニア — [アーキタイプ]

### Good
- Action API は **IAM 認証（SigV4）** をデフォルト化（認証なし公開を回避）
- Lambda は対象 S3 AP / WorkGroup / Glue DB / Bedrock に最小権限

### Concerns
- Bedrock InvokeModel の Resource を `nova-*` + `inference-profile/*` に広げた（必要だが要記録）
- Quick データソースロールの信頼プリンシパル既定が**アカウント root**（限定が前提）

### Recommendations
- inference-profile を使う旨と広めた理由を SECURITY ノートに残す（監査性）
- 本番では QuickDataSourcePrincipal を Quick 接続専用ロールに限定（README で強調済み、samconfig 既定も注意喚起）
- CloudTrail + S3 AP アクセス監査の有効化チェックを poc-checklist 化

---

## 5. データガバナンス / Lake Formation — [公開]+[アーキタイプ]

### Good
- 構造化データを Glue/Athena でカタログ化し、BI を疎結合に

### Concerns
- 当アカウントは **Lake Formation がカタログを統制**。Athena ロールへの LF 権限付与が未文書だった（実機で判明）

### Recommendations（反映済み）
- ✅ LF 権限付与（DESCRIBE on DB / SELECT・DESCRIBE on tables）を verification-results と demo-guide に明記
- 本番は LF タグベースアクセス制御（LF-TBAC）でロール別データ可視性を設計

---

## 6. 公共部門ガバナンス レンズ — [プロジェクト]+[アーキタイプ]

### Good
- ガバナンス注記・データ移動なし・暗号化・監査の観点を全ドキュメントに記載

### Concerns
- データ越境/保持/削除の検証可能性、AI 回答の人手レビュー要否の記述が薄い

### Recommendations
- governance-public-sector steering のチェックリスト（データ所在/暗号化/監査/保持/削除/インシデント）を UC29/30 の governance セクションに追補
- 高リスク回答は human-in-the-loop を明記（Quick Flows アクションの承認ステップ）

---

## 7. パートナー / SI イネーブルメント — [プロジェクト]

### Good
- partner-si チェックリストに UC29/30 を追加、顧客質問つき

### Concerns
- 「自己デプロイ可能」要件に対し、KB/Quick の手動構成・LF 権限など前提が多い

### Recommendations
- UC29/30 の **前提条件チェックリスト**（KB 種別=S3 Vectors か、LF 有無、推論プロファイル有無）を1枚化
- クリーンアップ手順（手動成果物含む）を runbook 化

---

## 8. FinOps / コスト最適化 — [アーキタイプ]

### Good
- サーバーレス従量・差分取り込み・必要時クエリで低コスト設計

### Concerns
- Amazon Quick 本体のユーザー/プラン課金が UC30 総コストに効くが概算のみ
- Athena scanned 課金は CSV 増大で逓増

### Recommendations
- analytics データは Parquet+パーティション化を推奨（scanned 削減）
- Quick 課金は別立てで明記済み。PoC 段階で unit cost を計測

---

## 9. SRE / 運用 — [アーキタイプ]

### Good
- Step Functions に Wait/ポーリング/通知。失敗を SNS 可視化

### Concerns
- ingestion FAILED 時のリトライ/隔離（DLQ）や部分失敗の扱いが未設計
- Scheduler 間隔と取り込み所要時間の整合チェックが運用任せ

### Recommendations
- Step Functions に Catch/リトライと失敗通知の分岐を追加（NotifyFailure は実装済、Catch 追補余地）
- 取り込み所要 > スケジュール間隔の検知（多重起動防止）

---

## 10. デベロッパーエクスペリエンス — [アーキタイプ]

### Good
- importlib 方式の軽量テスト、ruff/cfn-lint グリーン、events サンプル同梱

### Concerns
- Glue テーブル DDL が手動。再現スクリプトがない
- 多言語 README の機能差分同期（phase-article-consistency）への継続的注意

### Recommendations
- DDL を `scripts/` 化（または Athena Query Lambda に CreateTable 権限を分離付与した setup モード）
- README 機能表の同期チェックを CI 化

---

## Required Action Items

### Must Fix（公開前）
- [x] S3 Vectors メタデータ 2048 バイト制約と回避（inclusionPrefixes/メタデータ）を明記
- [x] Action API の IAM 認証をデフォルト化（実装済）
- [x] Lake Formation 権限付与手順を文書化
- [x] 権限制御の表現を「メタデータフィルタ / Quick 文書 ACL / カスタム RAG」の3層で整理（README + governance 反映済）

### Should Fix
- [x] 前提条件チェックリスト＋クリーンアップ runbook（手動成果物含む）
- [x] Step Functions に Catch/リトライ、取り込み多重起動防止
- [x] analytics の Parquet/パーティション推奨を明記、Glue DDL の scripts 化
- [x] Quick 接続手順の手順書化（スクショ取得指針つき・再現性）

### Nice to Have
- [x] LF-TBAC によるロール別データ可視性（設計ノート追加）
- [x] human-in-the-loop 承認（Quick Flows 高リスクアクション `request_approval`）
- [x] ベンチマーク（P50/95/99）スクリプト＋実データ（GetObject p50≈57ms / p99≈74ms、検証環境）

---

## Final Recommendation

**APPROVE WITH COMMENTS** — Must Fix（残1: governance セクションへの3層整理追補）反映で公開可。
Should Fix はフォローアップ Issue 化を推奨。
