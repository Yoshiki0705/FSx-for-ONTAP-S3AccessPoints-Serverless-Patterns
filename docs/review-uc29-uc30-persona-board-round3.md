# UC29 / UC30 ペルソナレビューボード（Round 3）

> Round 2 以降の差分。データライフサイクル（削除伝播）と Quick×FSxN S3 AP の公式経路にフォーカス。
> 役割ベース記述・エビデンスティア明記。公開 push 文章に実在/プロジェクト内ペルソナ名を含めない。

エビデンスティア: **[公開]** / **[プロジェクト]** / **[アーキタイプ]**

---

## Summary

- 全体評価: セルフサービスの「追加・更新・削除」ライフサイクルを実機で完全実証。Quick×FSxN の統合境界に公式 remediation 経路を確認。
- 推奨判定: **APPROVE WITH COMMENTS**（運用面の確定事項を反映。コスト停止＝クリーンアップを推奨）

---

## 1. データライフサイクル / ガバナンス レビュー — [公開]

Bedrock KB の増分同期と削除伝播（`dataDeletionPolicy`）に基づく。

### Good（Round 3 実機実証）
- データソース `dataDeletionPolicy = DELETE` を確認
- **削除ライフサイクルを実機で完全実証**:
  1. ファイル追加 → 同期（`numberOfNewDocumentsIndexed=1`）→ クエリで取得可
  2. **S3 AP 経由で削除** → 同期（`numberOfDocumentsDeleted=1`、scanned 21→20）→ クエリで「情報が見つかりません」（ベクトル除去を確認）
- セルフサービスの「現場が消したら AI からも消える」が成立 → UC29 の核心価値を裏付け

### Concerns
- Bedrock KB の同期は**明示的トリガーが必要**（自動ではない）。本UCは EventBridge + AutoSync で担保しているが、メタデータファイル（`.metadata.json`）の変更も同期対象である点に注意 [公開]
- 削除の反映は「次回同期」まで遅延する（即時ではない）。機密文書の緊急失効が必要な場合は手動同期 or 直接 Ingestion API を併用

### Recommendations（反映状況）
- ✅ 削除ライフサイクルの実証結果を `genai-kb-selfservice-curation/docs/verification-results.md` に記録
- ✅ アーキ/デモガイドに「削除＝Windows でファイルを消す→次回同期で AI からも消える」を明記
- 推奨: 緊急失効が要件なら `DeleteKnowledgeBaseDocuments`（直接 Ingestion）での即時削除手順も用意

---

## 2. ストレージ / アイデンティティ（FSxN S3 AP + AD）レビュー — [公開]

AWS Storage Blog「Configuring S3 Access Points for FSx for NetApp ONTAP with Active Directory（AI-powered analytics）」に基づく。

### 確認事項
- FSxN S3 AP のアクセス制御は **IAM 権限 + ファイルシステムレベル権限の2層**（公式に明記）
- S3 AP は**オブジェクト操作のみ**（バケット削除等は不可）。Quick 等のクローラが使う S3 API が AP 対応 API かの確認が必要 [公開]

### Quick×FSxN S3 AP（Round 2 の境界に対する remediation 強化）
- Round 2 で Quick の S3 ナレッジベースが FSxN S3 AP エイリアスを受理するが認可で失敗することを確認
- **公式経路**: FSxN S3 AP を **AD 連携（Windows identity）** で構成し、アクセスするロール/ユーザーを
  ファイルシステム側で解決可能にする（2層認証を両方満たす）。AP の FileSystemIdentity と IAM プリンシパルの整合が要点
- 本検証の AP（`v4testkbsync`）は FileSystemIdentity=UNIX root のため、Quick のデータアクセスロールを
  AP リソースポリシー principal に追加しようとすると `MalformedPolicy` となった（principal 制約）
- **結論（再確認）**: FSxN→RAG は **Bedrock KB（UC29）が素直**。Quick Index は通常 S3 ステージング、
  または AD 連携 AP + 適切なロール設計が前提

---

## 3. Quick / BI 統合 レビュー — [公開]

### Concerns
- Quick Sight の S3/Athena アクセスは QuickSight ロールの権限 + （LF 環境では）Lake Formation 付与が前提（repost「Fix access issues between S3 and Quick Sight」）
- データソースクォータ（列数上限等）に留意 [公開]

### Recommendations
- Quick Sight データセットは Athena 経由（本UCの Glue/Athena 基盤）で接続。QuickSight ロールへ Athena/Glue/LF/結果バケット権限を付与（`quick-console-setup.md` に手順）
- 接続トラブル時は IAM ロール/バケットポリシー/マニフェストを順に確認

---

## 4. FinOps レビュー（緊急度上昇） — [アーキタイプ]

### Concerns
- **課金が継続中**: Amazon Quick（月額）、CMK 2 鍵（~$1/月/鍵）、Lambda/API/Athena/Bedrock 従量、S3 Vectors/KB
- 検証目的は達成済み

### Recommendations
- **クリーンアップ runbook の実行を推奨**（2 スタック削除＋手動成果物＋**Quick 解約**で課金停止）
- CMK は削除保留期間（7–30日）があるため、停止計画に含める

---

## Round 3 Action Items

### 反映済み
- [x] 削除ライフサイクルの実機実証（add→query→delete→sync→gone、`dataDeletionPolicy=DELETE`）
- [x] Quick×FSxN S3 AP の remediation を公式 AD 連携経路で強化（`quick-console-setup.md`）
- [x] 検証記録・アーキ/デモガイドへ削除運用を明記

### 継続（Should / 要判断）
- [ ] クリーンアップ runbook の実行（課金停止）— **最優先で推奨**
- [ ] 緊急失効用の直接 Ingestion（DeleteKnowledgeBaseDocuments）手順
- [ ] Quick Index は S3 ステージング or AD 連携 AP のいずれかを採用して実接続を完成

---

## Final Recommendation

**APPROVE WITH COMMENTS** — 実装・実機検証は十分に成熟。残るのは運用判断（クリーンアップによる課金停止）と、
Quick Index 実接続の方式選定（ステージング/AD 連携）。本番化時は削除 SLA・緊急失効・コスト停止手順を明記すること。
