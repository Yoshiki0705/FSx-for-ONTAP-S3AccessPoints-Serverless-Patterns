# UC30 ペルソナレビューボード（Round 5 — フォローアップ検証）

> Round 4 の Must/Should Fix 反映を再レビュー（改善ループ）。役割ベース記述・エビデンスティア明記。
> 公開 push 文章に実在/プロジェクト内ペルソナ名を含めない。

エビデンスティア: **[公開]** / **[プロジェクト]** / **[アーキタイプ]**

---

## Summary

- Round 4 Must Fix（5 件）の検証: **4 件 RESOLVED / 1 件 PARTIALLY（設計上の意図的残存・正直に文書化）**
- 残課題はいずれも非クリティカル（意図的に後続へ委譲し、ドキュメントで正確に明示）
- ブログドラフトは**コミット安全**（実 ID/秘密なし）
- 最終評価: **APPROVE WITH COMMENTS**

---

## エージェント AI / API セキュリティ レンズ（フォローアップ）— [アーキタイプ]+[公開]

| # | Round 4 Must Fix | 検証結果 |
|---|------------------|----------|
| 1 | 監査フィールドの spoofing | **RESOLVED**: `_caller_identity()` が SigV4 呼び出し元を使用、`created_by`/`requested_by` を本文非依存に。テストで本文値が無視されることを確認 |
| 2 | `request_approval` を制御として誤表現 | **RESOLVED（正直な文書化）**: `enforced: False` + docstring/ブログで非強制スタブと明示、DynamoDB + executor を本番フォローアップと記載 |
| 3 | Athena 任意 SQL | **RESOLVED**: `ALLOW_RAW_SQL`（既定 false）で拒否、許可リストのみ。実機で拒否確認、テストあり |
| 4 | Guardrails 既定オフ | **PARTIALLY（意図的・文書化済み）**: 配線は正しく、ブログが既定オフ + 本番有効化推奨を正直に記載。Guardrail リソース自体は未同梱（OOTB は無効） |
| 5 | ブログの過大表現（Quick×FSxN / HITL / 最小権限） | **RESOLVED**: 標準手順での接続失敗を検証ログどおり記載、Bedrock KB / S3 ステージング推奨、AD 直結は hypothesis、HITL は非強制スタブ、最小権限は caveat 付き |

### コミット安全性
- `blog-draft-ja.md`: **SAFE**（実アカウント ID/リソース ID/IP/ARN/個人パスなし、公開リポジトリ URL のみ）
- テストの `111122223333` ARN は文書化済みプレースホルダー（ブログ非含有）

### 残課題（非クリティカル・要判断）
- `ALLOW_RAW_SQL=true`（管理オプトイン）時の任意 SQL は LF-TBAC（テンプレート外）に依存
- Guardrails OOTB 無効（正直に文書化済み）
- `QuickDataSourceRole` の信頼プリンシパル既定がアカウント root（テンプレートで注意喚起済み）
- per-action 認可は利用側（インテグレーター）責務（API は AWS_IAM 認証のみ、文書化済み）

---

## 実機検証（Round 5）

- UC30 スタック更新デプロイ後、Athena Query Lambda を実機検証:
  - raw SQL（`{"sql": ...}`）→ **拒否**（`raw sql is disabled; use a named query`）
  - named query（`sales_pipeline_total`）→ **completed（5 行）**
- リテラル Windows: UC29 の AD/Windows EC2 を流用し `quick_workspace` ボリューム + SMB 共有 +
  Windows identity S3 AP（`uc30-quick-workspace-smb`）を作成

---

## Round 5 Action Items

### 本ラウンドで確認/反映済み
- [x] Round 4 Must Fix 4/5 を RESOLVED と検証、#4 は意図的残存を正直に文書化と確認
- [x] ブログのコミット安全性を確認
- [x] Athena raw SQL ゲートを実機検証

### フォローアップ（要判断・本番化時必須）
- [ ] per-action 認可（呼び出し元 ARN → 許可アクション、API リソースポリシー）
- [ ] 強制 HITL（DynamoDB 承認ストア + executor 検証）
- [ ] LF-TBAC のテンプレート組み込み
- [ ] 本番 Guardrail リソースの同梱/有効化

---

## Final Recommendation

**APPROVE WITH COMMENTS** — Round 4/5 の Must Fix を反映（4/5 完全 RESOLVED、1 件は意図的残存を正直に文書化）。
エージェント実行系の安全性主張は実装・文書ともにエビデンスに整合。本番化時は per-action 認可・強制 HITL・
LF-TBAC・Guardrail 有効化を必須とする。
