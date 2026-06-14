# UC30 PoC 前提条件チェックリスト

## 環境前提

- [ ] AWS CLI v2 / 認証情報（対象アカウント・リージョン）
- [ ] **Amazon Quick Suite がアカウントで有効化済み**（別途サブスクリプション/料金）
- [ ] 既存または新規の FSx for ONTAP ファイルシステム
- [ ] S3 Access Point（NetworkOrigin を確認。Internet origin 推奨）
- [ ] S3 AP 経由の List/Get/Put 疎通確認

## データ基盤前提

- [ ] `quick-workspace/{index,analytics,flows}/<role>/` 構成でデータ投入
- [ ] **Glue テーブル作成**（[`scripts/create_glue_tables.sh`](../scripts/create_glue_tables.sh)）
- [ ] **Lake Formation 利用環境の場合**: Athena 実行ロールに LF 権限付与（DESCRIBE on DB / SELECT・DESCRIBE on tables）
- [ ] Athena WorkGroup の結果出力先バケットに書き込み可（`s3:GetBucketLocation` 含む）

## モデル前提

- [ ] Quick Flows 要約生成モデルの提供形態を確認（Nova は **推論プロファイル**）
- [ ] Action ロールに `bedrock:InvokeModel` + `bedrock:GetInferenceProfile`

## Amazon Quick 接続（コンソール）

- [ ] Quick Index データソースに S3 AP を接続（[Quick コンソール設定手順](quick-console-setup.md)）
- [ ] Quick Sight データセットを Athena テーブルから作成
- [ ] **文書レベル ACL / カスタム権限**（account/role/user）を設計（[LF-TBAC ノート](lake-formation-tbac.md) 併読）
- [ ] Quick Flows から Action API（IAM 認証 / SigV4）への接続を構成

## セキュリティ

- [ ] Action API は IAM 認証（未認証公開エンドポイントにしない）
- [ ] QuickDataSourcePrincipal を Quick 接続専用ロールに限定（既定の root を本番で使わない）
- [ ] 高リスク操作は `request_approval`（human-in-the-loop）を経由

> クリーンアップ手順は [UC29/UC30 クリーンアップ runbook](../../docs/uc29-uc30-cleanup-runbook.md) を参照。
