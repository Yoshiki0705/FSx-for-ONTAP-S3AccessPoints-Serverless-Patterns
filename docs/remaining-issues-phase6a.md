# Phase 6A 残課題チェックリスト

**作成日**: 2026-05-09  
**対象**: Phase 6A (Lambda SnapStart + SAM CLI ローカルテスト)  
**検証環境**: ap-northeast-1 (fsxn-eda-uc6 スタック)

---

## カテゴリ別残課題一覧

### A. CloudFormation テンプレート

| # | 課題 | 優先度 | 状態 | Phase | 備考 |
|---|------|-------|------|-------|------|
| A1 | EnableSnapStart パラメータ追加 | P1 | ✅ 完了 | 6A | 全 15 template-deploy.yaml |
| A2 | SnapStartEnabled Condition 追加 | P1 | ✅ 完了 | 6A | 全 15 template-deploy.yaml |
| A3 | Lambda Runtime python3.13 更新 | P1 | ✅ 完了 | 6A | 全 template-deploy.yaml + template.yaml + shared/cfn/ |
| A4 | Lambda 関数に SnapStart プロパティ Conditional 追加 | P1 | ✅ 完了 | 6A | `!If + !Ref AWS::NoValue` パターン |
| A5 | Lambda Version/Alias リソース追加 | P2 | ⏸️ 延期 | 7+ | CloudFormation の制約により SAM Transform 移行が必要 |
| A6 | Step Functions Resource を Alias ARN に切替（Conditional） | P2 | ⏸️ 延期 | 7+ | A5 とセット |
| A7 | IAM Invoke 権限に Version/Alias ARN 追加 | P2 | ⏸️ 延期 | 7+ | A5 とセット |
| A8 | SnapStart 非対応リージョンのバリデーション | P3 | ⏸️ 保留 | 7+ | 現状 `EnableSnapStart=false` で回避可能 |

**A5-A7 の対応方針**:
- 現時点では運用スクリプト (`scripts/enable-snapstart.sh`) で代替
- SAM Transform への移行は大規模改修のため、Phase 7 以降で別途検討
- それまでの間、ドキュメント (`docs/snapstart-guide.md`) で運用手順を明記

### B. 運用スクリプト

| # | 課題 | 優先度 | 状態 | Phase | ファイル |
|---|------|-------|------|-------|---------|
| B1 | SnapStart 有効化ワンショットスクリプト | P1 | ✅ 完了 | 6A | `scripts/enable-snapstart.sh` |
| B2 | SnapStart 動作検証スクリプト | P1 | ✅ 完了 | 6A | `scripts/verify-snapstart.sh` |
| B3 | SAM CLI ローカルテストスクリプト | P1 | ✅ 完了 | 6A | `scripts/local-test.sh` |
| B4 | SAM CLI 実動作確認（実機） | P2 | ⏸️ 保留 | 7+ | Docker/Finch が必要なローカルテスト |
| B5 | スクリプトを CI に統合 | P3 | ⏸️ 保留 | 7+ | Phase 5 で GitHub Actions 導入済み |

### C. ドキュメント

| # | 課題 | 優先度 | 状態 | Phase | ファイル |
|---|------|-------|------|-------|---------|
| C1 | SnapStart ガイド作成 | P1 | ✅ 完了 | 6A | `docs/snapstart-guide.md` |
| C2 | SnapStart ガイドに「$LATEST では効果なし」を明記 | P1 | ✅ 完了 | 6A | `docs/snapstart-guide.md` 更新 |
| C3 | SnapStart ガイドに運用パターン追加 | P1 | ✅ 完了 | 6A | パターン A/B/C の 3 方式 |
| C4 | ローカルテストガイド作成 | P1 | ✅ 完了 | 6A | `docs/local-testing-guide.md` |
| C5 | Phase 6A 記事作成（スクリーンショット付） | P1 | ✅ 完了 | 6A | `docs/article-phase6a-en.md` |
| C6 | 検証結果ドキュメント作成 | P1 | ✅ 完了 | 6A | `docs/verification-results-phase6a.md` |
| C7 | 多言語対応（ja/en/ko/zh-CN/zh-TW/fr/de/es） | P3 | ⏸️ 保留 | 7+ | 任意（project/product.md 参照） |

### D. テスト

| # | 課題 | 優先度 | 状態 | Phase | 備考 |
|---|------|-------|------|-------|------|
| D1 | 全既存テスト PASS 確認 | P1 | ✅ 完了 | 6A | 301/301 PASS |
| D2 | test_scale_to_zero_calls_update_with_zero_instances 修正 | P1 | ✅ 完了 | 6A | MIN_INSTANCE_COUNT=0 を明示、デフォルト1のテストも追加 |
| D3 | cfn-lint 0 errors 確認 | P1 | ✅ 完了 | 6A | 全 15 template-deploy.yaml で 0 errors |
| D4 | Python 3.13 互換性テスト | P2 | ✅ 完了 | 6A | 既存テストが全て PASS（後方互換性あり） |
| D5 | SnapStart 有効化 E2E テスト | P2 | ✅ 完了 | 6A | AWS 実環境で検証済み |

### E. AWS 実環境検証

| # | 検証項目 | 状態 | 結果 |
|---|---------|------|------|
| E1 | CloudShell で cfn-lint 実行 | ✅ 完了 | 全 15 テンプレート 0 errors |
| E2 | Lambda Runtime python3.13 確認 | ✅ 完了 | UC6 全関数で確認 |
| E3 | SnapStart デフォルト無効確認 | ✅ 完了 | SnapStart: "None" 表示 |
| E4 | CloudFormation スタック更新（EnableSnapStart=true） | ✅ 完了 | UPDATE_COMPLETE |
| E5 | Lambda SnapStart: ApplyOn PublishedVersions 確認 | ✅ 完了 | コンソール表示で確認 |
| E6 | Lambda バージョン公開（OptimizationStatus: On） | ✅ 完了 | Version 1 で On |
| E7 | Step Functions 実行 | ✅ 完了 | Succeeded (21.977秒) |
| E8 | EventBridge Scheduler 定期実行 | ✅ 完了 | 1時間ごと、全 17 回 Succeeded |
| E9 | SAM CLI local invoke 実機検証 | ⏸️ 保留 | Docker/Finch 環境が必要 |

### F. スクリーンショット

| # | スクリーンショット | 状態 | ファイル |
|---|-------------------|------|---------|
| F1 | cfn-lint validation | ✅ 完了 | `phase6a-cfn-lint-validation.png` |
| F2 | Lambda 関数一覧 (Python 3.13) | ✅ 完了 | `phase6a-lambda-functions-list.png` |
| F3 | Lambda Runtime python3.13 | ✅ 完了 | `phase6a-lambda-runtime-python313.png` |
| F4 | Lambda SnapStart 無効 (None) | ✅ 完了 | `phase6a-lambda-snapstart-none.png` |
| F5 | Lambda SnapStart 有効 (PublishedVersions) | ✅ 完了 | `phase6a-lambda-snapstart-config.png` |
| F6 | CloudFormation パラメータ | ✅ 完了 | `phase6a-cfn-stack-parameters.png` |
| F7 | SnapStart 有効化検証 (CloudShell) | ✅ 完了 | `phase6a-snapstart-enabled-verification.png` |
| F8 | Step Functions 実行結果 | ✅ 完了 | `phase6a-stepfunctions-executions.png` |
| F9 | CloudWatch Logs RESTORE | ⏸️ 保留 | SnapStart 有効版を実際に呼んだログが必要 |
| F10 | SAM local invoke 実行結果 | ⏸️ 保留 | Docker/Finch 環境が必要 |

### G. 運用

| # | 課題 | 優先度 | 状態 | Phase | ファイル |
|---|------|-------|------|-------|---------|
| G1 | CHANGELOG 作成/更新 | P2 | ✅ 完了 | 6A | `CHANGELOG.md` |
| G2 | README 更新（Phase 6A セクション） | P2 | ✅ 完了 | 6A | `README.md` |
| G3 | スクリプト使用例を CI/CD ガイドに追加 | P3 | ⏸️ 保留 | 7+ | `docs/ci-cd-guide.md` |

---

## 延期項目の詳細

### Phase 7 以降で検討すべき項目

#### 1. Lambda Version/Alias の IaC 化（A5-A7）

**現状**: `scripts/enable-snapstart.sh` で運用スクリプトとして実装  
**理想**: CloudFormation テンプレートで自動化

**アプローチ候補**:
- **SAM Transform 移行**: `AWS::Serverless::Function` + `AutoPublishAlias` を使用
  - メリット: 完全自動化、公式推奨
  - デメリット: 全 15 テンプレートの大規模書き換え、既存デプロイへの影響
  
- **CloudFormation Custom Resource**: Lambda で Version を管理
  - メリット: 現行構造を維持
  - デメリット: 複雑度増加、追加の Lambda リソースが必要

**推奨**: Phase 7 で SAM Transform 移行を段階的に実施

#### 2. Step Functions Resource の Alias ARN 自動切替（A6）

A5 と合わせて SAM Transform 移行時に対応。SAM では以下が可能：

```yaml
Resource: !Ref DiscoveryFunction.Alias   # SAM が自動解決
```

#### 3. SnapStart 非対応リージョンのバリデーション（A8）

**現状**: `EnableSnapStart=false` デフォルトでエラー回避可能  
**改善案**: CloudFormation Rules で非対応リージョンを検出しエラー表示

```yaml
Rules:
  SnapStartRegionCheck:
    RuleCondition: !Equals [!Ref EnableSnapStart, "true"]
    Assertions:
      - Assert: !Contains [["us-east-1", "ap-northeast-1", ...], !Ref "AWS::Region"]
        AssertDescription: SnapStart is not supported in this region
```

#### 4. SAM CLI ローカルテストの実機検証（B4, E9, F10）

**未検証の理由**: CloudShell では Docker/Finch が利用不可  
**対応方法**: ローカル開発環境または EC2 から実行して検証

---

## Phase 6A 完了サマリー

### 完了した項目

- 全 15 CloudFormation テンプレートに SnapStart サポート追加
- Python 3.13 への Runtime 更新
- 運用スクリプト 3 本作成（enable/verify/local-test）
- ドキュメント 3 本作成（snapstart-guide/local-testing-guide/verification-results-phase6a）
- Phase 6A 記事作成（実検証結果反映済み）
- AWS 実環境での E2E 検証（8 項目）
- スクリーンショット 8 枚撮影
- 既存失敗テスト修正（`test_scale_to_zero_calls_update_with_zero_instances`）
- CHANGELOG + README 更新

### 延期項目

- Lambda Version/Alias の IaC 化 → Phase 7 で SAM Transform 移行と合わせて検討
- Step Functions Resource の Alias ARN 自動切替 → Phase 7
- SAM CLI ローカルテストの実機検証 → Docker 環境が必要（ローカル実施推奨）
- 多言語対応（en/ko/zh/fr/de/es） → Phase 7 以降で任意実施
