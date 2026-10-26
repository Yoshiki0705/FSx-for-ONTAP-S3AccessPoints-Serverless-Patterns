# Real-environment run: recorded [V1][V2][V3][V4][V5][V6][V7]; not recorded [E13] (status source: docs/verification-record.md)

🌐 **Language / 言語**: 日本語 | [English](procedure.en.md)

# 共有ボールト検証ラボの手順書

> Language / 言語: 日本語 | [English](procedure.en.md)

この手順書に残すのは、コードで表せない所と、表せるが意図して手動にする所だけです。リソースの作成・バックアップ・コピー・復元・取り消し・後片付けはスクリプトと CloudFormation が行い、ポータルの画面確認は `07_portal_config.sh --ui` が Playwright spec を起動します。権限の表は [README](../README.md) にあります。

## 冒頭の 4 項目

1. 実機での通しの日付と環境: 未実施。以降の記述は、実機で確認するまで未検証として読んでください。画面経由の確認（Playwright spec）もブラウザでの実行は未実機で、未自動化の部分と未実機の部分は別物です。
2. 削除できない期間: LAG の保持日数 N。下限は 7 日で、AWS が定める LAG ボールトの最小値です。上限の具体値は AWS のドキュメントを参照してください（[CreateLogicallyAirGappedBackupVault の `MinRetentionDays` / `MaxRetentionDays`](https://docs.aws.amazon.com/aws-backup/latest/devguide/API_CreateLogicallyAirGappedBackupVault.html)）。起点は元バックアップの作成時刻で、コピー完了時刻ではありません（1 回観測、N = 7）。復旧ポイントが入っている間はボールトも削除できません。空のボールトは削除できました（1 回観測）。Vault Lock の文書は、コンプライアンスモードのボールトは、グレースタイムの満了後は復旧ポイントを保持している間、どのユーザーに対しても AWS に対しても削除・変更ができないと述べています [E-012]。
3. KMS キーを復旧ポイントの失効前に削除予約しない理由: スタックから外した KMS キーは削除が予約され、待機は 7〜30 日（既定 30）、保留中は暗号操作に使えません。LAG の復旧ポイントが失効する前にキーが使えなくなったときの影響は未検証なので、キーを `Retain` で残し、削除は `10_teardown.sh --delete-key` が全 LAG ボールトの空を確認した後にだけ行います。「キーを残さないと復旧ポイントが壊れる」とは書きません。
4. 費用: FS の稼働、バックアップとコピーの保管、KMS キーに課金されます。現在の単価は `01_preflight.sh --estimate-cost`、実績は `06_verify.sh --cost` で取ります。価格表の取得日と、価格表の行の対応が不確かなことは README にあります。ロックによるリソース拘束と費用の切り分けは [README の「コストとリソース拘束」](../README.md#コストとリソース拘束) にあります。

## この手順書の位置づけ

権限の表、終了コード、パラメータ、スクリプトとリージョンの対応は README にあります。この手順書は、それらで埋まらない所だけを扱います。

## 2 つのアカウントとサインイン

所有者と受け手の 2 つのアカウントを使います。どのアカウントをどちらにするかは読者の判断です。01 は、選ばれた 2 つが異なること、アカウント ID がプロファイルと一致することを検査します。SSO のサインインは `aws sso login --profile <プロファイル>` で、認可はブラウザ上の人の対話です。

<!-- SCREENSHOT: lab-sso-account-chooser.png | the IAM Identity Center account list showing two selectable accounts | none (no account id or email) -->

## 所有者のコンソールで見る場所

同じ事実は 06 が API で出しますが、API の値と画面の表示の一致を自分の目で確かめる所です。コンソールの言語は英語に統一します（ラベルが日英の文書で共通になります）。

- AWS Backup → Vaults → LAG ボールトの詳細: タイプ、ロック、最小・最大保持、暗号化キーの種類。
- Jobs → Copy jobs: 完了したコピージョブ。
- LAG ボールト → Recovery points: 1 件と失効日。
- RAM → Shared by me: ACTIVE の共有とリソースタイプ。

<!-- SCREENSHOT: lab-backup-lag-vault-owner.png | AWS Backup LAG vault detail: type, lock, min and max retention, encryption key kind | mask the account id and the vault ARN -->
<!-- SCREENSHOT: lab-backup-copy-job.png | the completed copy job in Jobs > Copy jobs | mask the account id and the recovery-point ARNs -->
<!-- SCREENSHOT: lab-backup-lag-recovery-points.png | the LAG vault Recovery points list showing one point and its expiry | mask the account id and the recovery-point ARN -->
<!-- SCREENSHOT: lab-backup-account-sharing.png | the Account sharing section of the vault detail showing the recipient | mask both account ids -->
<!-- SCREENSHOT: lab-ram-owner-share.png | RAM > Shared by me showing the ACTIVE share and its resource type | mask the account ids and the resource-share ARN -->

## 受け手のコンソールで見る場所

- RAM → Shared with me: 保留中の招待と承認。
- Backup → Vaults → shared through RAM: 共有ボールトと所有者の列。
- 復旧ポイントの復元フォーム: SVM、ボリューム名、ジャンクションパス。
- Jobs → Restore jobs: 実行中と完了。
- FSx → ボリューム: 復元されたボリューム。

<!-- SCREENSHOT: lab-ram-recipient-invitation.png | RAM > Shared with me showing the pending invitation and the accept action | mask both account ids and the invitation ARN -->
<!-- SCREENSHOT: lab-backup-shared-vault-recipient.png | Backup > Vaults showing the shared vault and the owner column | mask both account ids and the vault ARN -->
<!-- SCREENSHOT: lab-backup-restore-form.png | the recovery-point restore form showing the SVM, volume name and junction path | mask the file-system and SVM ids -->
<!-- SCREENSHOT: lab-backup-restore-job.png | Jobs > Restore jobs showing a running and a completed restore | mask the account id and the restore-job ARN -->
<!-- SCREENSHOT: lab-fsx-restored-volume.png | FSx volumes showing the restored volume | mask the file-system, SVM and volume ids -->

## ポータルの画面確認の範囲

ポータルの画面確認は `07_portal_config.sh --ui --expect <状態>` が起動します。資格情報の用意、前提（Node、`node_modules`、chromium）の導入、スキップを失敗として数える判定は 07 が持つので、ここには書きません。spec が見るのは要素の存在と文言までで、見た目や操作感の判断は含みません。spec はブラウザでの実行が未実機です（E25）。

<!-- SCREENSHOT: portal-ja-recovery-region-selector.png | the Recovery points panel region selector | mask the account id in any ARN shown -->
<!-- SCREENSHOT: portal-en-recovery-region-selector.png | the Recovery points panel region selector (English UI) | mask the account id in any ARN shown -->
<!-- SCREENSHOT: portal-ja-recovery-shared-vault.png | the shared-vault choice and the owner-account column | mask both account ids -->
<!-- SCREENSHOT: portal-en-recovery-shared-vault.png | the shared-vault choice and the owner-account column (English UI) | mask both account ids -->

## コスト配分タグの有効化の待ち時間と請求画面の場所

費用の取得は `06_verify.sh --cost` が行います。手順書に残すのは、`Project` タグをコスト配分タグとして有効化した後に反映されるまでの待ち時間と、Cost Explorer のどの画面でタグを絞るかです。有効化の 1 行コマンドは README にあり、スクリプトは実行しません。反映までの時間は公式文書で確認して書きます（実装時）。

<!-- SCREENSHOT: lab-billing-cost-explorer-tag.png | Cost Explorer filtered by the Project tag, same period as 06 --cost | mask the account id -->
<!-- SCREENSHOT: portal-ja-recovery-restore-dialog.png | the restore dialog with its confirmation checkbox | mask the file-system and SVM ids -->
<!-- SCREENSHOT: portal-en-recovery-restore-dialog.png | the restore dialog with its confirmation checkbox (English UI) | mask the file-system and SVM ids -->

## コードに出ない前提

- 読者の組織の SCP や他アカウントの自動修復は、読者のアカウントの API の一覧から網羅できません。LAG ボールトへのコピーが、他チームの取り消し操作で失敗する場合があります。
- LAG ボールトの対応リージョンは、コピー先を決める前に確認します。一覧は AWS Backup の LAG ボールトの文書にあり、改訂されるため、ここには写さずリンクを置きます（[該当ページ](https://docs.aws.amazon.com/aws-backup/latest/devguide/logicallyairgappedvault.html)）。「API が見当たらない」とは書きません。

<!-- SCREENSHOT: portal-ja-recovery-revoked-notice.png | the return to the default display and the notice after revocation | mask the account id -->
<!-- SCREENSHOT: portal-en-recovery-revoked-notice.png | the return to the default display and the notice after revocation (English UI) | mask the account id -->

## 既存 sandbox を更新するとき

既存の sandbox を持ち、依存が更新された状態で `make sandbox` を再実行すると、AwsCliLayer の内容が変わることがあります。ポータルの `backend.ts` はこの層の論理 ID に asset hash を含めるので、更新は置換ではなく作成 + 削除になり、Express モードの sandbox でも通ります（`docs/agent/portal-cdk-quality-gates.md` の AwsCliLayer の行）。この対策より前のポータルで作った sandbox でも、対策後の `backend.ts` でデプロイすれば同じく作成 + 削除になります。それでも `07 --deploy` が `UPDATE_FAILED` で止まった場合の回復手段の選択（削除と再作成は Cognito ユーザーと DynamoDB を消します）は、ポータルの利用者データの扱いに関わる人の判断です。

## このラボの範囲外である MPA の経路

LAG ボールトの MPA（マルチパーティー承認）は、`CreateRestoreAccessVault` の承認を 3〜20 人の承認チームで守る経路で、このラボが検証する RAM 共有による復元とは別物です。プライマリの組織に加えてリカバリ用の AWS Organizations をもう 1 つ必要とし、`MpaApprovalTeamArn` はボールトの作成時に設定します（作成後は変更できず、変更はボールトの置換を伴います）。このラボの単一組織・2 アカウント構成はそれを満たさないため MPA を実行せず、テンプレートの `MpaApprovalTeamArn` パラメータは空のままにします。この経路は実機では未実行です（追跡は follow-up issue #471）。詳細は [AWS Backup の MPA のガイド](https://docs.aws.amazon.com/aws-backup/latest/devguide/multipartyapproval.html) と [Multi-party approval とは](https://docs.aws.amazon.com/mpa/latest/userguide/what-is.html) にあります。<!-- allow:not-a-claim: these are documented MPA prerequisites cited from the linked AWS MPA guide, not a claim of vendor absence -->

## 撮影一覧

マーカーは `<!-- SCREENSHOT: <ファイル名> | 写っているべき内容 | マスク対象 -->` の形で、該当箇所と、この一覧に同数置きます。マーカーは英語で書きます。P01〜P04 の原本は spec が `LAB_CAPTURE_DIR` に書き出します（手で撮りません）。撮影そのものは未実施です。

| ID | ファイル名（案） | 画面 |
|---|---|---|
| S01 | lab-sso-account-chooser.png | IAM Identity Center のアカウント一覧 |
| S02 | lab-backup-lag-vault-owner.png | 所有者の LAG ボールトの詳細 |
| S03 | lab-backup-copy-job.png | 所有者のコピージョブ |
| S04 | lab-backup-lag-recovery-points.png | 所有者の復旧ポイント |
| S05 | lab-backup-account-sharing.png | 所有者の Account sharing |
| S06 | lab-ram-owner-share.png | 所有者の RAM 共有 |
| S07 | lab-ram-recipient-invitation.png | 受け手の RAM 招待 |
| S08 | lab-backup-shared-vault-recipient.png | 受け手の共有ボールト |
| S09 | lab-backup-restore-form.png | 受け手の復元フォーム |
| S10 | lab-backup-restore-job.png | 受け手の復元ジョブ |
| S11 | lab-fsx-restored-volume.png | 受け手の復元ボリューム |
| S12 | lab-billing-cost-explorer-tag.png | Cost Explorer のタグ絞り込み |
| P01 | portal-ja-recovery-region-selector.png | ポータルのリージョン選択欄（日本語 UI） |
| P01 | portal-en-recovery-region-selector.png | ポータルのリージョン選択欄（英語 UI） |
| P02 | portal-ja-recovery-shared-vault.png | ポータルの共有ボールト選択（日本語 UI） |
| P02 | portal-en-recovery-shared-vault.png | ポータルの共有ボールト選択（英語 UI） |
| P03 | portal-ja-recovery-restore-dialog.png | ポータルの復元ダイアログ（日本語 UI） |
| P03 | portal-en-recovery-restore-dialog.png | ポータルの復元ダイアログ（英語 UI） |
| P04 | portal-ja-recovery-revoked-notice.png | ポータルの取り消し後の通知（日本語 UI） |
| P04 | portal-en-recovery-revoked-notice.png | ポータルの取り消し後の通知（英語 UI） |
