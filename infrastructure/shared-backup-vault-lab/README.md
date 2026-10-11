# Real-environment run: not yet done (status source: docs/verification-record.md)

# 共有ボールト検証ラボ

> Language / 言語: 日本語 | [English](README.en.md)

AWS Backup の論理エアギャップ（LAG）ボールトを 2 つのアカウント間で RAM 共有し、共有先のアカウントと Amplify ポータルから復旧ポイントを参照・復元する経路を、コードとパラメータだけで自分の環境に再現するためのラボです。CloudFormation 3 本、番号付きスクリプト 10 本、ポータルの画面確認 spec、日英の手順書と検証記録で構成します。

## 冒頭の注意

- **実機での通しは未実施です。** この時点で実機で動いたものはありません。スクリプトの先頭と文書の冒頭に状態の行があり、状態の唯一の出所は [`docs/verification-record.md`](docs/verification-record.md) です。
- **LAG ボールトの作成は不可逆です。** 保持日数（7〜35 日）は作成時に固定され、復旧ポイントが入っている間はボールトを削除できません。空のボールトは削除できました（1 回観測）。詳細は [`docs/procedure.md`](docs/procedure.md) の冒頭にあります。
- **費用が発生します。** FS の稼働、バックアップとコピーの保管、KMS キーに課金されます。後片付けは [`10_teardown.sh`](scripts/10_teardown.sh) が行い、残るものを一覧します。

## クイックスタート

```bash
cp lab.env.example lab.local.env     # 値を自分の環境に置き換える
./scripts/01_preflight.sh --side both   # 前提を課金前に検査する（読み取りのみ）
./scripts/02_deploy.sh --side owner --apply
./scripts/02_deploy.sh --side recipient --apply
./scripts/03_deploy_lag_share.sh --retention-days 7 --apply --confirm <TOKEN>
./scripts/04_backup_and_copy.sh --phase all --retention-days 7 --apply --confirm <TOKEN>
./scripts/05_accept_share.sh --apply
./scripts/06_verify.sh
./scripts/10_teardown.sh --apply     # 後片付け。残るものを一覧する
```

状態を変えるスクリプトは、`--apply` を付けないとプランを表示して終了コード 10 で止まります。不可逆な操作（03・04・10）はさらに、パラメータに結びついたトークン（`--confirm`）を要求します。トークンの文字列は、`--apply` なしの実行がプランと一緒に表示します。

## パラメータ

全変数は `lab.env.example` にダミー値つきで並びます。環境依存の値は全て `LAB_` 接頭辞の環境変数で、アカウント ID・プロファイル・リージョン・VPC・サブネット・SG・名前を含みます。既定値の一部や成立条件は 1 回だけの手動観測に基づくものがあり、観測値と条件は [`docs/verification-record.md` の参考節](docs/verification-record.md#参考-初回の手動観測) にあります（README には観測値を写しません）。

| 変数 | 必須 | 既定 | 使う所 |
|---|---|---|---|
| `LAB_OWNER_PROFILE` / `LAB_RECIPIENT_PROFILE` | ○ | — | 全スクリプト |
| `LAB_OWNER_ACCOUNT_ID` / `LAB_RECIPIENT_ACCOUNT_ID` | ○ | — | 全スクリプト |
| `LAB_PRIMARY_REGION` | ○ | — | 全スクリプト |
| `LAB_OWNER_SUBNET_ID` | ○ | — | 01, 02（所有者） |
| `LAB_RECIPIENT_SUBNET_ID` | EXISTING が空のとき ○ | — | 01, 02（受け手） |
| `LAB_SECOND_REGION` | — | 空（1 リージョン） | 01, 02（受け手）, 03〜10 |
| `LAB_TAG` | — | `shared-vault-lab` | タグ・スタック名・エイリアス・名前の既定 |
| `LAB_STANDARD_VAULT_NAME` / `LAB_LAG_VAULT_NAME` / `LAB_SHARE_NAME` | — | `${LAB_TAG}-*` | 02〜10 |
| `LAB_ALLOW_EXTERNAL_PRINCIPALS` | — | `true` | 03 |
| `LAB_RECIPIENT_EXISTING_FS_ID` | — | 空（最小 FS を作る） | 01, 02（受け手） |
| `LAB_MIN_SSO_MINUTES` | — | `30` | 02, 03, 04, 07, 08, 10 |
| `PORTAL_URL` / `PORTAL_USER` / `PORTAL_PASSWORD` | — | 空 | 07 `--ui` |

`PORTAL_*` と `LAB_UI_EXPECT` は `LAB_` 接頭辞を持たない例外です。`PORTAL_URL` / `PORTAL_USER` / `PORTAL_PASSWORD` は既存のポータルの E2E が使う名前をそのまま使います。`LAB_UI_EXPECT` は 07 が spec に渡す値（`arn-missing` / `arn-present` / `revoked`）で、読者は設定しません。

## スクリプトとリージョン

`--region` の意味はスクリプトごとに違います。省略時の既定も違います。

| スクリプト | 役割 | 読むリージョン | 変更するリージョン | `--region` 省略時 |
|---|---|---|---|---|
| 01 | 前提の検査（読み取りのみ） | PRIMARY, SECOND | なし | 設定された全リージョン |
| 02 | FS・SVM・ボリューム・標準ボールト・ロール（owner / recipient） | 指定 | 指定 | 所有者は PRIMARY のみ、受け手は全リージョン |
| 03 | LAG ボールトと RAM 共有 | 指定 | 指定 | PRIMARY → SECOND の順 |
| 04 | バックアップとコピー | PRIMARY と宛先の LAG | バックアップは PRIMARY、コピーは宛先 | 全宛先 |
| 05 | RAM 招待の承認 | 受け手の指定 | 受け手の招待 | 全リージョン |
| 06 | 検証（読み取りのみ）、`--cost` は費用の実績 | 両アカウントの指定 | なし | 全リージョン |
| 07 | ポータル設定・画面確認 | 受け手のホーム | `--deploy` のみ | `--print` は全リージョン、他はホーム |
| 08 | 復元 | 受け手の指定 | 指定の復元先 | PRIMARY のみ |
| 09 | RAM 共有の取り消し | 所有者と受け手 | 所有者の共有 | 全リージョン |
| 10 | 後片付け | PRIMARY, SECOND | PRIMARY, SECOND | `--region` を受け付けず全リージョン |

## 終了コード

| コード | 意味 |
|---|---|
| 0 | 成功 |
| 1 | 失敗または中断 |
| 2 | 使い方の誤り（引数の形式違反を含む） |
| 10 | プラン表示のみ（`--apply` が無い） |
| 75 | ツール不足 |
| 78 | 環境が整っていない（01 のみ） |

## 必要な権限

実行者に必要な `service:operation` は [`scripts/lib/required-actions.json`](scripts/lib/required-actions.json) に 1 か所でまとまり、01 の権限シミュレーション、この表、スタブの呼び出し記録の 3 つが同じ集合を参照します。表の集合がこの JSON と一致することをテストが固定します。

`iam simulate-principal-policy` は、権限が足りない可能性を課金前に見つける検査で、足りる保証ではありません。SCP や RCP が評価に含まれるかは未確認です（E18）。CloudFormation の資源の権限のうち、FSx の 3 型はスキーマに権限が無く、公式文書から転記したもので、列挙の正しさは未検証です（E23）。

所有者側の操作者（`operator-owner`。呼び出し先ロールへの `iam:PassRole` を含む）:

```
backup:DeleteRecoveryPoint
backup:DescribeBackupJob
backup:DescribeBackupVault
backup:DescribeCopyJob
backup:DescribeRecoveryPoint
backup:DescribeRegionSettings
backup:ListBackupJobs
backup:ListBackupVaults
backup:ListCopyJobs
backup:ListRecoveryPointsByBackupVault
backup:StartBackupJob
backup:StartCopyJob
cloudformation:CreateChangeSet
cloudformation:DeleteStack
cloudformation:DescribeChangeSet
cloudformation:DescribeStackEvents
cloudformation:DescribeStackResource
cloudformation:DescribeStacks
cloudformation:DescribeType
cloudformation:ExecuteChangeSet
ec2:DescribeSecurityGroups
ec2:DescribeSubnets
fsx:DeleteVolume
fsx:DescribeBackups
fsx:DescribeFileSystems
fsx:DescribeStorageVirtualMachines
fsx:DescribeVolumes
fsx:ListTagsForResource
iam:GetRole
iam:PassRole
iam:SimulatePrincipalPolicy
kms:DeleteAlias
kms:DescribeKey
kms:ScheduleKeyDeletion
ram:DeleteResourceShare
ram:GetResourceShares
```

受け手側の操作者（`operator-recipient`）:

```
backup:DescribeRestoreJob
backup:GetRecoveryPointRestoreMetadata
backup:ListBackupVaults
backup:ListRecoveryPointsByBackupVault
backup:ListRestoreJobs
backup:StartRestoreJob
cloudformation:CreateChangeSet
cloudformation:DeleteStack
cloudformation:DescribeChangeSet
cloudformation:DescribeStackEvents
cloudformation:DescribeStacks
cloudformation:ExecuteChangeSet
ec2:DescribeSecurityGroups
ec2:DescribeSubnets
fsx:DeleteVolume
fsx:DescribeFileSystems
fsx:DescribeStorageVirtualMachines
fsx:DescribeVolumes
fsx:ListTagsForResource
fsx:TagResource
iam:GetRole
iam:GetRolePolicy
iam:PassRole
iam:SimulatePrincipalPolicy
ram:AcceptResourceShareInvitation
ram:GetResourceShareInvitations
```

CloudFormation が呼び出し元の資格情報で資源を作るときの権限は、所有者側が `cloudformation-provisioning-owner`、受け手側が `cloudformation-provisioning-recipient` の群で、全集合は [`scripts/lib/required-actions.json`](scripts/lib/required-actions.json) にあります。無くても本体の手順が進む読み取り（`operator-optional`。`ce:GetCostAndUsage`、`pricing:GetProducts` など）は、01 が `allowed` 以外でも ❌ にせず ⚠ を出します。

## 作成する資源の型

テンプレートが作る CloudFormation の型です。FSx の 3 型（`AWS::FSx::FileSystem` / `StorageVirtualMachine` / `Volume`）の権限は、スキーマに無く公式文書から転記したもので、未検証です（E23）。

| テンプレート | 型 |
|---|---|
| owner-base | `AWS::KMS::Key`, `AWS::KMS::Alias`, `AWS::FSx::FileSystem`, `AWS::FSx::StorageVirtualMachine`, `AWS::FSx::Volume`, `AWS::Backup::BackupVault`, `AWS::IAM::Role` |
| owner-lag-share | `AWS::Backup::LogicallyAirGappedBackupVault`, `AWS::RAM::ResourceShare` |
| recipient-restore | `AWS::IAM::Role`, `AWS::FSx::StorageVirtualMachine`, `AWS::FSx::FileSystem`（`ExistingFileSystemId` が空のときだけ） |

## スクリプトを通さない直接デプロイ

CloudFormation を直接使う読者は、例ファイルをコピーして値を入れ、次の形でデプロイできます（所有者側の例。`<…>` は読者の値）。

```
aws cloudformation deploy --template-file cloudformation/owner-base.yaml --stack-name <LAB_TAG>-owner-base --capabilities CAPABILITY_IAM --parameter-overrides file://cloudformation/parameters/owner-base.local.json --profile <PROFILE> --region <REGION>
```

直接デプロイは、スクリプトの確認機構（トークン、事後検査、アカウントの一致検査）の外にあります。保持日数・宛先・アカウントを自分で確かめてください。テンプレートに残る唯一の防御は `owner-lag-share.yaml` の `Rules` ですが、`aws cloudformation deploy` が `Rules` の不一致を実際に拒否するかは確認できていません（E1）。また、`--parameter-overrides file://…` が例ファイルの形式を受理するかも確認できていません（E22）。

## 組織共有とコスト配分タグの有効化

次の 2 つは組織全体・支払いアカウントの設定で、ラボのスクリプトは実行しません。01 は状態を読み取りで報告するだけです。必要なときは、影響範囲を理解したうえで管理アカウントの資格情報で実行してください。

```
aws ram enable-sharing-with-aws-organization --profile <管理アカウント>
aws ce update-cost-allocation-tags-status --cost-allocation-tags-status TagKey=Project,Status=Active --profile <支払いアカウント>
```

既定の経路（`LAB_ALLOW_EXTERNAL_PRINCIPALS=true`）ではどちらも不要です。コスト配分タグは `06 --cost` の `Project` での絞り込みにだけ効きます。

## 費用の確認

現在の単価は `01_preflight.sh --estimate-cost` が価格表から読んで表示します。費用の実績は `06_verify.sh --cost` が `ce get-cost-and-usage` を `Project` タグで絞って取ります（読み取りのみ）。

**Cost Explorer の API は、ページ分割された 1 リクエストごとに 0.01 USD 課金されます**（[Cost Explorer のユーザーガイド](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html)、2026-10-11 に全文を取得。再確認はしていません）。`06 --cost` の 1 実行は、2 アカウント × 2（タグ絞りと合計）= 4 リクエストで、ページ分割で増えます。`ce list-cost-allocation-tags`（01 `--estimate-cost`）の課金は確認できていません。Cost Explorer の値は請求額ではなく、取得直後は反映が遅れて空になりえます。

## 状態の行の読み方

スクリプトと文書の先頭にある状態の行は、[`docs/verification-record.md`](docs/verification-record.md) の記録から導きます。全項目が成立するまでの中間状態があり、`recorded [V1][V4]; not recorded [E13]` の形で、成立した項目だけを並べます。`recorded` が空のときだけ `not yet done` です。文法の全体は検証記録の状態の節にあります。

## 関連文書

- [手順書](docs/procedure.md)（コンソールで見る場所、サインイン、コードに出ない前提）
- [検証記録](docs/verification-record.md)（V / E の定義、実機の記録、初回の手動観測）
- [AWS RAM による FSx for ONTAP リソース共有](../../docs/multi-account/ram-sharing.md)
- [Disaster Recovery パターン](../../docs/multi-region/disaster-recovery.md)
- [ポータル設計ガイド](../../solutions/amplify-portal/docs/data-protection-recovery-design.md)
