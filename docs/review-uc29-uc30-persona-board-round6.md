# UC29 / UC30 ペルソナレビューボード（Round 6 — フォローアップ実装）

> Round 4/5 で「フォローアップ（要判断）」として残した項目を実装し、実機検証した記録。
> 役割ベース記述・エビデンスティア明記。公開 push 文章に実在/プロジェクト内ペルソナ名を含めない。

エビデンスティア: **[公開]** / **[プロジェクト]** / **[アーキタイプ]**

---

## Summary

- Round 4/5 で残課題としていた **per-action 認可** と **強制 HITL** を実コードとして実装・実機検証。
- UC29 の **バースト制御**（予約済み同時実行）も反映。
- 評価: **APPROVE**（主要フォローアップを実装済み。LF-TBAC/Guardrail リソース同梱は環境依存の opt-in として整理）

---

## 1. UC30 — per-action 認可（実装）— [アーキタイプ]

Round 4 指摘「認証≠認可」に対し、認証済み呼び出し元（SigV4 `requestContext.identity`）に基づく
per-action 認可を実装。

- `ACTION_AUTH_MODE=open`（既定・デモ）/ `enforce`（本番）
- enforce 時: 読み取り（generate_brief）は許可、状態変更は `AUTHORIZED_PRINCIPALS`、
  管理（approve）は `ADMIN_PRINCIPALS` に照合。不一致は **403**
- テスト: open 全許可 / enforce 不許可 403 / enforce 許可 / 読み取り常時許可 / approve 管理者必須

## 2. UC30 — 強制 HITL（実装）— [公開]+[アーキタイプ]

Round 4 指摘「request_approval が非強制」に対し、DynamoDB 承認ストアによる**強制ゲート**を実装。

- フロー: `request_approval`（永続化, enforced=true）→ `approve`（管理者, 条件付き更新）→
  `execute_approved`（**approved のみ実行可**、それ以外 409）
- 競合防止: `ConditionExpression` で pending→approved→executed の状態遷移を保証
- 承認ストア未設定時は非強制スタブ（enforced=false）にフォールバック（後方互換）

### 実機検証（ライブ）

| ステップ | 結果 |
|---------|------|
| 1. request_approval | 202, enforced=true |
| 2. execute（承認前） | **409 rejected** |
| 3. approve（管理者） | 200 approved |
| 4. execute（承認後） | **200 executed** |
| 5. 再 execute | **409**（executed 済み、再実行不可） |

→ 高リスク操作が承認なしに実行されないことを実機で実証。

## 3. UC29 — バースト制御（実装）— [アーキタイプ]

Round 4/5 の Should（バースト時の同時起動抑制）に対し、KB Trigger Lambda に
`ReservedConcurrentExecutions`（パラメータ `KbTriggerReservedConcurrency`、既定 2）を付与。
デバウンス（進行中スキップ）+ ConflictException 処理 + 予約並列度で、大量投入時も KB ジョブは
同時 1 本に収束し、Bedrock/CloudWatch スロットリングを抑制する。

## 4. LF-TBAC / Guardrail（整理）

- **LF-TBAC**: ロール別データ境界の強制は Lake Formation 環境依存。テンプレート常時組み込みは
  非 LF 環境で破綻するため、検証ログ + ブログで「LF 環境では Athena ロールへ LF 付与が前提」と明記し、
  本番は LF-TBAC 設計を推奨（opt-in 運用）。
- **Bedrock Guardrail**: 既定オフ・本番有効化推奨を維持（`BedrockGuardrailId` で設定）。
  Guardrail リソースのアカウント横断的同梱は副作用が大きいため opt-in 運用とする。

---

## Round 6 Action Items

### 実装・反映済み
- [x] UC30 per-action 認可（ACTION_AUTH_MODE=enforce、403 拒否）
- [x] UC30 強制 HITL（DynamoDB 承認ストア + executor ゲート、実機実証）
- [x] UC29 バースト制御（予約済み同時実行）
- [x] テスト拡充（UC30: 17→25、HITL ライフサイクル + 認可）
- [x] ブログを実装済み機能に整合（HITL/認可を「実装済み」に更新）

### 環境依存（opt-in 運用として整理）
- [ ] LF-TBAC のテンプレート常時組み込み（LF 環境のみ）
- [ ] Guardrail リソースの同梱（本番方針依存）

---

## Final Recommendation

**APPROVE** — 主要フォローアップ（per-action 認可・強制 HITL・バースト制御）を実コードとして実装し、
強制 HITL は実機でゲート動作を実証。残る LF-TBAC/Guardrail 同梱は環境・本番方針依存の opt-in として整理済み。
