# UC29 / UC30 クリーンアップ runbook

両UC の検証環境を安全に撤去する手順。**CloudFormation 外で手動作成した成果物**を含むため、
削除順序が重要（特に Glue テーブルと非空 S3 バケット）。

> 既存の FSx for ONTAP・S3 Access Point・Knowledge Base **本体**は再利用リソースのため**削除しない**。
> 本UCがデモ用に追加したものだけを撤去する。

## 前提変数（例）

```bash
REGION=ap-northeast-1
ALIAS=v4testkbsync-...-ext-s3alias        # 再利用した S3 AP エイリアス
KB_ID=9QGDVI3J1Q                          # 再利用 KB
DS_ID_UC29=QDANCNS9HU                      # UC29 用に新規作成したデータソース
DB=quick_workspace_db                      # UC30 Glue DB（スタックが作成）
WG=quick-workspace-wg
```

## 手順（推奨順序）

### 1. UC30 Glue テーブルを削除（手動作成分）

スタックが作る Glue **Database** の中に、手動で作った **テーブル**が残るとスタック削除が失敗する。

```bash
aws glue delete-table --database-name "$DB" --name sales_pipeline --region "$REGION" || true
aws glue delete-table --database-name "$DB" --name it_incidents  --region "$REGION" || true
```

### 2. UC30 Athena 結果バケットを空にする

スタックが作る S3 バケットは非空だと削除されない。

```bash
RESULTS_BUCKET=$(aws cloudformation describe-stack-resources \
  --stack-name fsxn-s3ap-uc30-quick-workspace --region "$REGION" \
  --query "StackResources[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" --output text)
aws s3 rm "s3://${RESULTS_BUCKET}" --recursive --region "$REGION" || true
```

### 3. Lake Formation 権限を revoke（任意・きれいに戻す場合）

```bash
ROLE=$(aws iam list-roles --query "Roles[?starts_with(RoleName,'fsxn-s3ap-uc30-quick-workspace-AthenaQueryRole')].Arn" --output text)
aws lakeformation revoke-permissions --region "$REGION" \
  --principal DataLakePrincipalIdentifier="$ROLE" \
  --resource '{"Database":{"Name":"quick_workspace_db"}}' --permissions DESCRIBE || true
aws lakeformation revoke-permissions --region "$REGION" \
  --principal DataLakePrincipalIdentifier="$ROLE" \
  --resource '{"Table":{"DatabaseName":"quick_workspace_db","TableWildcard":{}}}' --permissions SELECT DESCRIBE || true
```

### 4. CloudFormation スタックを削除

```bash
aws cloudformation delete-stack --stack-name fsxn-s3ap-uc30-quick-workspace --region "$REGION"
aws cloudformation delete-stack --stack-name fsxn-s3ap-uc29-selfservice-kb  --region "$REGION"
aws cloudformation wait stack-delete-complete --stack-name fsxn-s3ap-uc30-quick-workspace --region "$REGION"
aws cloudformation wait stack-delete-complete --stack-name fsxn-s3ap-uc29-selfservice-kb  --region "$REGION"
```

### 5. UC29 用に新規作成した Bedrock データソースを削除

KB 本体は残し、デモ用に追加したデータソースのみ削除。

```bash
aws bedrock-agent delete-data-source \
  --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID_UC29" --region "$REGION" || true
```

> 補足: KB のベクトルストアに残った本デモ由来のベクトルを完全除去したい場合は、
> データソース削除後に KB の再同期、または該当ベクトルの削除を行う。

### 6. S3 Access Point 上のデモデータを削除

```bash
aws s3 rm "s3://${ALIAS}/ai-knowledge/"    --recursive --region "$REGION" || true
aws s3 rm "s3://${ALIAS}/quick-workspace/" --recursive --region "$REGION" || true
aws s3api delete-object --bucket "$ALIAS" --key "_uc-deploy/marker.txt" --region "$REGION" || true
```

### 7. 残存確認

```bash
aws cloudformation describe-stacks --stack-name fsxn-s3ap-uc29-selfservice-kb --region "$REGION" 2>&1 | grep -q "does not exist" && echo "UC29 stack removed"
aws cloudformation describe-stacks --stack-name fsxn-s3ap-uc30-quick-workspace --region "$REGION" 2>&1 | grep -q "does not exist" && echo "UC30 stack removed"
aws s3 ls "s3://${ALIAS}/ai-knowledge/" --region "$REGION" | wc -l    # 0 を確認
aws s3 ls "s3://${ALIAS}/quick-workspace/" --region "$REGION" | wc -l # 0 を確認
aws glue get-table --database-name "$DB" --name sales_pipeline --region "$REGION" 2>&1 | grep -q "EntityNotFound" && echo "glue table removed"
```

## 撤去対象まとめ

| 種別 | リソース | 作成元 |
|------|---------|--------|
| CFn スタック | fsxn-s3ap-uc29-selfservice-kb / fsxn-s3ap-uc30-quick-workspace | CFn |
| Bedrock データソース | UC29 用 `QDANCNS9HU`（inclusionPrefixes=ai-knowledge/） | 手動 |
| Glue テーブル | sales_pipeline / it_incidents | 手動 |
| Lake Formation 付与 | Athena ロールへの DESCRIBE/SELECT | 手動 |
| S3 AP データ | ai-knowledge/ , quick-workspace/ , _uc-deploy/marker.txt | 手動投入 |
| Athena 結果バケット中身 | （スタック作成バケット内） | クエリ実行 |

## 残す（再利用）リソース

- FSx for ONTAP ファイルシステム、S3 Access Point、Knowledge Base 本体、既存データソース `N57CHFRSXR`

## Amazon Quick の扱い（重要・コスト）

UC30 の検証で **Amazon Quick をアカウントで有効化済み**（QuickSight から進化した Quick）。
**ユーザー/アカウントが有効な間は月額課金が発生**するため、検証終了後は明示的に停止すること。

- Quick コンソール → アカウント管理 → 不要ユーザーのアクセス権を取り消す
- アカウントごと解約する場合: Quick の「アカウント設定 → サブスクリプション解約（Unsubscribe）」
- 注意: 解約すると Quick Sight のデータセット/分析/ダッシュボードも削除される。再利用予定があるなら残す判断も可
- CLI 参考: `aws quicksight delete-user` / `aws quicksight delete-account-subscription`（要確認・破壊的）

> Quick は本テンプレート（CloudFormation）外で有効化したため、スタック削除では止まらない。課金停止は手動操作が必要。
