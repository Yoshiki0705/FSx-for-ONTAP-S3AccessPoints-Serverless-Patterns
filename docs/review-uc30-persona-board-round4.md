# UC30 ペルソナレビューボード（Round 4）

> 対象: UC30 `genai-quick-agentic-workspace`（実装・検証・ドキュメント・ブログドラフト）。
> Round 1-3（UC29/UC30 共通）で未深掘りの観点を、独立レビュー（エージェント AI / API セキュリティ）で実施。
> 役割ベース記述・エビデンスティア明記。公開 push 文章に実在/プロジェクト内ペルソナ名を含めない。

エビデンスティア: **[公開]** / **[プロジェクト]** / **[アーキタイプ]**

---

## Summary

- 初回提出時評価: **REQUEST CHANGES**。整理された設計だが、エージェント安全性の主張が「助言」止まりで強制されていない:
  認可欠如（認証のみ）、承認の非強制、Athena 任意 SQL、Guardrails 既定オフ、ブログの過大表現。
- 対応後評価: **APPROVE WITH COMMENTS**（Must Fix を反映。フォローアップは Should）

---

## 1. エージェント AI / API セキュリティ レンズ — [アーキタイプ]+[公開]

### Concerns（指摘）と対応状況

| # | 指摘 | 重大度 | 対応 |
|---|------|--------|------|
| 1 | **認証≠認可**: Action API は SigV4 認証のみ。監査フィールド `requested_by`/`role` を**本文から信頼**しており spoofing 可能 | Must | ✅ 監査フィールドを**認証済み呼び出し元**（`requestContext.identity`）から設定。`requested_by`/`created_by` を本文非依存に。きめ細かい per-action 認可は利用側責務と明記 |
| 2 | **`request_approval` が非強制**: 高リスク操作を技術的にゲートしていない（承認ストア/executor なし） | Must | ✅ コード docstring + レスポンス `enforced: false` で**非強制スタブ**であることを明示。ブログ/ドキュメントの「HITL」表現を正確化。本番は承認ストア + executor 検証を追加と明記 |
| 3 | **Athena 任意 SQL**: `event.sql` を無条件で実行（クエリインジェクション） | Must | ✅ `ALLOW_RAW_SQL`（既定 false）で任意 SQL を**拒否**、許可リスト `NAMED_QUERIES` のみ。実機で raw SQL 拒否を確認 |
| 4 | **Bedrock Guardrails 既定オフ** | Must | ✅ ブログ「セキュリティ設計」で**本番は Guardrails 有効化推奨**を明示（既定オフ・単層プロンプト境界であることを記載） |
| 5 | **ブログが Quick×FSxN 統合を過大表現**（実機では失敗） | Must | ✅ ブログを検証ログに整合（標準手順では接続未達、Bedrock KB / S3 ステージング推奨、AD 連携は hypothesis） |
| 6 | エラーで `str(e)` を返却（内部情報漏えい） | Should | ✅ 3 ハンドラー全てを generic error（`internal error`）に。テスト追加 |
| 7 | `data_prep` の `prefix` 上書きでスコープ逸脱 | Should | ✅ `WORKSPACE_PREFIX` 配下にクランプ。テスト追加 |
| 8 | 結果バケットのハードニング不足 | Should | ✅ PublicAccessBlock + TLS-only ポリシー + 30日ライフサイクル、SSE を AES256 に統一 |
| 9 | API スロットリングなし（denial-of-wallet） | Should | ✅ `MethodSettings`（rate 10 / burst 20）を追加 |
| 10 | テスト不足（raw SQL / 認可 / generic error / prefix） | Should | ✅ テストを 9 → 17 に拡充 |

### 残（フォローアップ Issue 推奨）
- per-action のきめ細かい認可（呼び出し元 ARN → 許可アクションのマッピング、API リソースポリシー）
- 強制的 HITL（DynamoDB 承認ストア + executor）
- LF-TBAC のテンプレート組み込み（現状は手動付与）
- `S3ApHelper` / `shared/observability` 採用、context サイズ上限、非タイムスタンプ ID

---

## 実機検証（Round 4）

- UC30 スタックを更新デプロイ（`ALLOW_RAW_SQL=false`、結果バケットハードニング、API スロットリング）
- Athena: **raw SQL 拒否**を実機確認（`raw sql is disabled`）、named query は正常（5 行）
- リテラル Windows: UC29 の AD/Windows EC2 を**流用**し、`quick_workspace` ボリューム + SMB 共有 +
  Windows identity S3 AP（`uc30-quick-workspace-smb`）を作成（UC30 のロール×サービス構成を Windows から維持可能に）

---

## Round 4 Action Items

### Must Fix（反映済み）
- [x] 監査フィールドを認証済み呼び出し元から設定（spoofing 防止）
- [x] `request_approval` を非強制スタブと明示（コード + ドキュメント）
- [x] Athena 任意 SQL を既定無効化（許可リストのみ）
- [x] Guardrails 本番有効化の推奨を明記
- [x] ブログの Quick×FSxN / HITL / 最小権限 / データ移動表現を検証ログに整合

### Should Fix（反映済み）
- [x] generic error / prefix クランプ / 結果バケットハードニング / API スロットリング / テスト拡充

### フォローアップ（要判断）
- [ ] per-action 認可、強制 HITL、LF-TBAC テンプレート化、S3ApHelper 採用

---

## Final Recommendation

**APPROVE WITH COMMENTS** — Round 4 の Must/Should を反映。エージェント実行系の安全性は
「認証 + 監査の真正性 + 任意 SQL 既定無効 + 承認スタブの正直な表現」で底上げ。
本番化時は per-action 認可・強制 HITL・LF-TBAC を必須とする。
