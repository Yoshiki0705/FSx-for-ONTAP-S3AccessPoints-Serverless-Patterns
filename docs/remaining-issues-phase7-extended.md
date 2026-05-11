# Phase 7 Extended Round — 残課題チェックリスト

**作成日**: 2026-05-12
**最終更新**: 2026-05-12 (網羅的スイープ完了)

---

## 完了済み項目（今回のラウンドで対応）

### A. IAM S3 Access Point ARN form 統一（全 17 UC）

| # | 課題 | 対象 | 状態 | Commit |
|---|------|------|------|--------|
| A1 | S3AccessPointName パラメータ追加 | UC1-5,6-8,10,14 (9 UC) | ✅ | `848b64e` |
| A2 | HasS3AccessPointName Condition 追加 | 同上 | ✅ | `848b64e` |
| A3 | IAM Resource に !If 条件分岐追加 | 同上 | ✅ | `848b64e` |
| A4 | template.yaml (SAM source) 同期 | 13 UC | ✅ | `3ded822` |
| A5 | deploy scripts に S3AccessPointName 追加 | 6 scripts | ✅ | `3ded822` |
| A6 | deploy_all_ucs.sh post-deploy hack 削除 | 1 script | ✅ | `3ded822` |

### B. Lambda handler バグ修正

| # | 課題 | 対象 | 状態 | Commit |
|---|------|------|------|--------|
| B1 | UC2 entity_extraction `import os` 欠落 | financial-idp | ✅ | `848b64e` |
| B2 | UC17 report_generation f-string 不要 | smart-city-geospatial | ✅ | `3ded822` |

### C. 横断検査スクリプト整備

| # | スクリプト | 目的 | 状態 | Commit |
|---|-----------|------|------|--------|
| C1 | `scripts/lint_all_templates.{sh,py}` | 並列 cfn-lint (17 UC) | ✅ | `848b64e` |
| C2 | `scripts/check_handler_names.py` | pyflakes undefined-name | ✅ | `848b64e` |
| C3 | `scripts/check_conditional_refs.py` | UC9-class bug detector | ✅ | `848b64e` |
| C4 | `scripts/check_python_quality.py` | 広範 pyflakes sweep | ✅ | `3ded822` |

### D. AWS 環境クリーンアップ

| # | 課題 | 状態 | 備考 |
|---|------|------|------|
| D1 | fsxn-semiconductor-eda-demo DELETE_FAILED 解消 | ✅ | Athena WG + versioned bucket 空化 |

### E. ドキュメント更新

| # | 課題 | 状態 | Commit |
|---|------|------|--------|
| E1 | phase7-troubleshooting.md Section 12/13 追加 | ✅ | `848b64e` |
| E2 | phase7-summary.md Extended Round section 追加 | ✅ | `848b64e` |

---

## 検証結果サマリー

| 検証項目 | 結果 |
|----------|------|
| cfn-lint (9 UC 修正分) | 9/9 clean |
| pyflakes undefined-name (87 handlers) | 0 issues |
| pyflakes broad sweep (197 files) | 0 critical |
| UC9-class conditional ref check (17 templates) | 0 issues |
| shared tests | 338 PASS |
| UC-specific tests | 620 PASS |
| **Total tests** | **958 PASS** |

---

## 残存課題（Phase 8 以降に持ち越し）

### Phase 8 Theme H: Pattern C → B Hybrid (UC6/7/8/13)

| UC | 現状 | 目標 |
|----|------|------|
| UC6 (construction-bim) | OutputDestination あり | ✅ 対応済み |
| UC7 (genomics-pipeline) | OutputDestination なし | Athena 出力と AI 成果物の分離設計が必要 |
| UC8 (energy-seismic) | OutputDestination なし | 同上 |
| UC13 (semiconductor-eda) | OutputDestination なし | 同上 |
| UC14 (education-research) | OutputDestination なし | 同上 |

設計ドキュメント: `docs/design-pattern-c-to-b-hybrid.md`

### Phase 8 Theme I: OutputWriter multipart (> 5 GB)

設計ドキュメント: `docs/design-output-writer-multipart.md`
現状: 設計草稿完了、実装未着手。

### Phase 8 Theme D: 残スタック cleanup

| Stack | 用途 | 判断 |
|-------|------|------|
| fsxn-uc4-demo | UC4 screenshot 用 | 撮影完了 → 削除可 |
| fsxn-uc9-demo | UC9 screenshot 用 | 撮影完了 → 削除可 |
| fsxn-uc15-demo | UC15 screenshot 用 | 撮影完了 → 削除可 |
| fsxn-uc16-demo | UC16 screenshot 用 | 撮影完了 → 削除可 |
| fsxn-uc17-demo | UC17 screenshot 用 | 撮影完了 → 削除可 |
| fsxn-insurance-claims-demo | UC11 Phase 3 | 記事用に保持 or 削除 |
| fsxn-retail-catalog-demo | UC12 Phase 3 | 同上 |
| fsxn-s3ap-guard-hooks | Guard Hooks demo | 記事用に保持 or 削除 |
| fsxn-eda-uc6 | UC6 Phase 2 | 古い → 削除推奨 |

**推奨**: UC4/9/15/16/17 の 5 demo stacks は `scripts/cleanup_generic_ucs.sh` で一括削除可能。
コスト: Lambda + Step Functions + DynamoDB はアイドル時ほぼ $0 だが、VPC Endpoints ($0.01/hr × 2 = $14.4/month per stack) がある場合はコスト発生。

### コード品質（cosmetic — 非ブロッカー）

| 項目 | 件数 | 優先度 |
|------|------|--------|
| unused imports | 77 | Low (機能に影響なし) |
| unused variables | 7 | Low |
| f-string without placeholders | 0 (修正済み) | — |

### template.yaml ↔ template-deploy.yaml 乖離

`template-deploy.yaml` には OutputDestination / OutputS3APAlias / OutputS3APPrefix 等の
Phase 5-7 で追加されたパラメータが含まれるが、`template.yaml` (SAM source) には
S3AccessPointName + HasS3AccessPointName のみ追加済み。

**影響**: `scripts/regenerate_deploy_templates.sh` を実行すると OutputDestination 関連の
パラメータが消える。現状は `template-deploy.yaml` を直接編集する運用のため問題ないが、
将来的に SAM source を正とする場合は `create_deploy_template.py` の拡張が必要。

**推奨**: Phase 8 で `template.yaml` を廃止し `template-deploy.yaml` を唯一の正とする
方針を検討。または `create_deploy_template.py` を OutputDestination 対応に拡張。

---

## 今後の作業優先度

1. **記事 publish** — 全 17 UC スクリーンショット揃い済み、A 側で記事最終化中
2. **Demo stacks cleanup** — UC4/9/15/16/17 の 5 stacks 削除（コスト削減）
3. **Phase 8 Theme H 設計レビュー** — Pattern C → B hybrid の実装方針確定
4. **Phase 8 Theme I 実装** — OutputWriter multipart (> 5 GB 対応)
5. **template.yaml 廃止 or 同期方針決定** — 二重管理の解消

---

**Phase 7 Extended Round status: ✅ COMPLETE**
全 17 UC の CloudFormation テンプレート、Lambda handler、deploy スクリプト、
ドキュメントの整合性を確認。958 テスト PASS、0 critical issues。
