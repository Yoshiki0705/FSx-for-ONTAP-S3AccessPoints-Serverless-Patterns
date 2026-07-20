# AWS DevOps Agent — CDK メンテナンス自動化の評価

> CDK Conference Japan 2026 セッション「AWS DevOps Agent で CDK メンテナンスは楽になるのか？〜検証から見えた最適解〜」(奥田) の知見を反映。

## DevOps Agent とは

AWS DevOps Agent (GA 2026/3) は、GitHub リポジトリに接続し、コード変更の分析・テスト生成・リリースリスク評価を自動化する AI エージェント。CDK リソース定義: `AWS::DevOpsAgent::AgentSpace`。

## このプロジェクトへの適用可能性

### 適用可能な領域

| ユースケース | DevOps Agent の機能 | 本プロジェクトでの価値 |
|-------------|-------------------|-------------------|
| **CDK バージョンアップ影響分析** | コード変更の影響範囲を自動分析 | `aws-cdk-lib` の minor/major update 時に破壊的変更を自動検知 |
| **PR レビュー支援** | 組織標準に対する自動評価 | cdk-nag suppression の妥当性レビュー |
| **テスト生成** | 変更に応じたテスト自動生成 | 新 Lambda 追加時に CDK ハーネステストを自動追記 |
| **インシデント調査** | ログ/メトリクス横断分析 | AppSync エラー → Lambda エラー → S3 AP タイムアウトの根本原因追跡 |

### 現時点での制約

| 制約 | 影響 |
|------|------|
| **リージョン**: us-east-1, us-west-2, eu-west-1 のみ | ap-northeast-1 のリソースはモニタリング対象外（GitHub 接続は OK） |
| **コスト**: 従量課金（会話数 + 調査数） | 個人プロジェクトでは費用対効果が不明確 |
| **Amplify Gen2 対応**: backend.ts の synth フローを理解するか未検証 | defineBackend パターンが標準 CDK と異なるため誤検知の可能性 |
| **Memory 制限**: 25KB / 120 行推奨 | 大規模な AGENTS.md の内容を全て記憶させるのは困難 |

## 現在のアプローチとの比較

| 機能 | 現在のツール | DevOps Agent に置換するか |
|------|------------|:---:|
| 依存関係更新 | Renovate (自動 PR) | ❌ Renovate で十分 |
| セキュリティスキャン | gitleaks + zizmor + cfn-guard | ❌ 既存で十分 |
| IAM 検証 | validate-iam-policies.py (Access Analyzer) | ❌ 専用スクリプトの方が精度高い |
| 破壊的変更検知 | cdk-nag + CDK ハーネステスト | ⚠️ DevOps Agent が補完できる可能性 |
| テスト生成 | 手動 | ✅ 新機能追加時のテスト自動生成に有用 |
| インシデント調査 | CloudWatch ダッシュボード手動確認 | ✅ 横断分析で価値あり |

## 判断

### 今すぐ導入しない理由

1. **Renovate + cdk-nag + CDK ハーネス** で依存管理・品質ゲートは十分カバーされている
2. ap-northeast-1 リソースのモニタリングに非対応（GitHub 連携のみ）
3. ソロ開発のため PR レビュー支援の恩恵が限定的
4. 従量課金のため、個人プロジェクトでのコスト正当化が困難

### 導入を検討するタイミング

- チーム開発に移行し、PR レビュー負荷が増えた場合
- `aws-cdk-lib` の major version upgrade（v3 等）で大規模移行が必要な場合
- 本番インシデントが発生し、横断的な根本原因分析が必要な場合
- DevOps Agent が ap-northeast-1 モニタリングに対応した場合

## 代替: CDK バージョンアップの自動化（現行アプローチ）

現在は **Renovate** で `aws-cdk-lib` を自動更新し、CI で以下を検証:

```
Renovate PR (aws-cdk-lib bump)
    → cfn-lint (テンプレート構文)
    → cdk-nag (コンプライアンス)
    → CDK ハーネステスト (構造アサーション 17 tests)
    → IAM policy validation (Access Analyzer)
    → Unit tests (2,162+ tests)
```

この多層防御で、DevOps Agent がなくても破壊的変更の大半を検知できる。

## 参考

- [AWS DevOps Agent — User Guide](https://docs.aws.amazon.com/devopsagent/latest/userguide/)
- [AWS DevOps Agent GA announcement (2026/3)](https://aws.amazon.com/about-aws/whats-new/2026/03/aws-devops-agent-generally-available/)
- [Getting started with AWS CDK](https://docs.aws.amazon.com/devopsagent/latest/userguide/getting-started-with-aws-devops-agent-getting-started-with-aws-devops-agent-using-aws-cdk.html)
- [CDK Conference Japan 2026](https://qiita.com/issy929/items/f8c5abf9f2e327bec8da)
