# データ保護の復旧層 — AWS Backup 論理エアギャップボールトのポータル設計ガイド

🌐 **Language / 言語**: 日本語 | [English](data-protection-recovery-design.en.md)

> 目的: AWS Backup の論理エアギャップボールト（logically air-gapped vault、以降 LAG ボールト）という復旧層が、本ポータルにどう接続するかの設計枠を示します。AWS の仕様そのものは別リポジトリ（下記「参照」）が持ちます。本ガイドは仕様を再導出せず、ポータル側の接続点と、人の承認を挟む復元導線の置き場所だけを決めます。
>
> 本ガイドは設計のみです。ボールト・Vault Lock・RAM 共有・マルチパーティー承認（MPA）はポータルの外（ガバナンス側）で既に用意されている前提に立ちます。

## 対象読者と前提

Amazon FSx for NetApp ONTAP（以降 FSx for ONTAP）の S3 Access Points をフロントするこの Amplify ポータルに、復旧点の一覧と承認付き復元の導線を足す設計を検討する人を対象にします。前提として、ポータルは既に ONTAP のスナップショット一覧とロック（Tamperproof、SnapLock、ARP 状態）を扱えますが、AWS Backup の復旧点や復元ジョブを扱う面はまだありません。

## 復旧層としての LAG ボールトの位置づけ

LAG ボールトは、AWS アカウント（管理境界）そのものが侵害された場合の復旧層です。同じ管理境界の中にあるスナップショットや SnapMirror の宛先は、侵害された AWS アカウントや ONTAP 管理者の操作が届く範囲にあります。LAG ボールトはバックアップを AWS Backup のサービス所有アカウントに保存し、ONTAP の管理操作が届かない場所に置くことで、この境界の外側に復旧点を持ちます。

この層が守るのは復旧点の可用性と完全性です。持ち出されたデータの機密性は守りません。機密性はアクセス制御・暗号化・監査という別の制御が担います。ポータルの画面でも、復旧点の一覧や復元は「データを取り戻す」操作であって「流出を止める」操作ではない、という区別を文言で示します。

## ONTAP スナップショットと AWS Backup 復旧点の区別

読者が 2 つを混同しないよう、ポータルの画面と本ガイドでは両者を明確に分けて扱います。

| 観点 | ONTAP スナップショット（実装済み） | AWS Backup 復旧点（本ガイドの対象） |
|------|-----------------------------------|------------------------------------------|
| 保存場所 | 同じ FSx for ONTAP ファイルシステム内 | AWS Backup のボールト（LAG ボールトは AWS サービス所有アカウント） |
| 管理境界 | ONTAP / AWS アカウントの管理境界の中 | LAG ボールトは管理境界の外 |
| ポータルの既存面 | `functions/snapshots`、`functions/data-protection`（一覧・ロック状態・ARP 状態・Tamperproof ロック） | なし |
| 想定 API | ONTAP REST（`GET /api/storage/volumes/{uuid}/snapshots` ほか） | AWS Backup（`backup:ListRecoveryPointsByBackupVault` ほか） |
| 守る対象 | 近接の改ざん・誤削除からの復旧点 | AWS アカウント全体の侵害からの復旧点 |

## ポータルへの接続点

ポータルには、この復旧層をそのまま載せられる既存の仕組みが揃っています。新しく作るのは、AWS Backup を呼ぶハンドラと、それを既存の承認・オーケストレーションに接続する配線です。

- **復旧点の一覧パネル**: 既存の Data Protection セクションのスナップショット一覧の隣に、AWS Backup の復旧点一覧を置きます。ONTAP スナップショットと取り違えないよう、ラベルで明示的に分けます。これは読み取り専用の面です。
- **承認付き復元フロー**: 復元の起票は、既存の人の承認（`agent-chat` の `request_action_approval`、"safety-controller"）と、既存の不可逆操作の確認ガード（`_require_ack` / `acknowledgeIrreversible`）を再利用して段階的に承認を取ります。復元の実行は、休眠中の AppSync → Step Functions 配線（`amplify/custom/step-functions.ts`、呼び出し側はコメントアウト済み）を活性化し、人の承認待ちを挟んだ追跡可能な実行として回します。
- **新しいボリュームへの復元**: 復元は常に新しいボリュームに対して行い、元のボリュームを上書きしません。これは参照元の Option D と LAG ボールト文書の仕様に合わせたものです。

## 既存の承認・ガードの再利用

ポータルには、不可逆操作を人の承認の後ろに置くための仕組みが既にあります。新しい復元導線はこれらを再利用し、独自の承認機構を作りません。

| 既存の仕組み | 置き場所 | 復元導線での使い方 |
|------------|---------|------------------|
| 不可逆操作の確認ガード | `functions/data-protection`（`_require_ack`）、`functions/snapshots`（`acknowledgeIrreversible`） | 復元の起票時に、結果を一文で示したうえで明示的な確認を要求 |
| 人の承認ツール | `functions/agent-chat`（`request_action_approval`、"safety-controller"） | 復元ジョブの開始前に承認を経由させる |
| AppSync → Step Functions 配線 | `amplify/custom/step-functions.ts`（休眠中） | 人の承認待ち状態を挟んだ復元実行のオーケストレーション |

読み取り専用の一覧パネルには `acknowledgeIrreversible` は不要です。確認ガードと人の承認は、復元ジョブの開始という書き込み・不可逆の操作にだけかけます。

## クロスリージョン・クロスアカウントの可視化

復旧点の一覧は、RAM 共有された別アカウント・別リージョンのボールトも対象にできます。参照元 Option D の手順では、`aws backup list-recovery-points-by-backup-vault` に `--backup-vault-account-id` を渡して、共有先の復旧アカウントから一覧します。ポータルの一覧パネルも同じ引数を取れるよう設計し、別アカウント・別リージョンの復旧点と、そこへ復元できるかどうかを見られるようにします。

監視する状態は次の 3 つです。これらの状態そのもののアラートはポータル側で作らず、Observability 側（`fsxn-observability-integrations`）に委ねます。ポータルは可視化と導線を持ち、アラートは Observability が持つ、という役割分担です。

- ボールトのコピージョブの失敗。
- 「Completed with issues」（元のファイルシステムが AWS マネージドキーで暗号化されていると、バックアップはボールトへコピーされず、ジョブはこの状態で完了します。参照元リポジトリに [E-009] として登録された所見）。
- RAM 共有の取り消し（共有先の復旧アカウントが一覧・復元の権限を失います。参照元 [E-014]）。

接続先は既存の `docs/multi-account/ram-sharing.md` と `docs/multi-region/disaster-recovery.md` です。

## ベンダーの仕様に関する補足

AWS 公開文書に基づく仕様のうち、設計に効くものを参照元の登録済み所見として引きます。本ガイドでは再導出しません。

- Malware Protection for AWS Backup は FSx for ONTAP の復旧点をスキャンの対象にしません（参照元リポジトリに [E-008] として登録済み）。復元した中身の確認は、FlexClone と S3 Access Points 経由のスキャンで行います。
- 元のファイルシステムが AWS マネージドキーで暗号化されている場合、バックアップは LAG ボールトへコピーされず、ジョブは「Completed with issues」で完了します（[E-009]）。LAG ボールトを使う前提は、元のファイルシステムがカスタマーマネージドキーで暗号化されていることです。
- バックアップの対象は RW ボリュームです。DP / LSM / FlexCache と SnapMirror の宛先ボリューム、SnapLock FlexGroup ボリュームは対象外です（[E-010]）。

## 繰り延べる不可逆な境界

本ガイドと後続のポータル作業は、次を行いません。いずれもポータルの外・ガバナンス側が持つ決定で、使い捨ての検証環境を要します。

- **ボールトの作成・Vault Lock の設定を行いません。** Vault Lock のコンプライアンスモードは常に有効で、後から無効にできません（[E-020]）。ボールトの暗号化キーは作成時に決まり、後から変えられません（[E-020]）。ボールトを作るのは不可逆で、ポータルの外・アカウント／ガバナンス側が持つ決定です。
- **実際の MPA 承認者の構成を行いません。** MPA の承認チームのリソースは `us-east-1` にあり、実際の復旧アクセスをゲートします。実承認者の配線は、使い捨ての検証環境を要する別 Issue です。
- ポータルの作業範囲は、読み取り（一覧）＋承認付き復元（新しいボリュームへの復元の起票）＋設計ガイド＋クロスアカウント／リージョンの可視化に限られます。ボールト・Vault Lock・RAM 共有・MPA は別の場所で既に構成済みである前提に立ちます。

## #459 で実装した読み取り専用の一覧

#459 では、本ガイドの「ポータルへの接続点」の一覧パネルを読み取り専用で実装しました。既存の ARP/AI・SnapLock などの機能と同じ粒度で、ポータルの Data Protection セクションに「復旧ポイント」のパネルを足しています。

- **一覧は API から取得します。** パネルは `ListRecoveryPointsByBackupVault` を `ByResourceType="FSx"` で呼び、FSx for ONTAP の復旧ポイントだけを一覧します。AWS Backup コンソールのボールト一覧とボールト詳細には、どちらにも「表示される復旧ポイント数は概算値である可能性があり、正確な数は `ListRecoveryPointsByBackupVault` を参照する」旨の注記があります（O-1）。パネルはこの概算値ではなく API の結果を表示します。
- **表示する列は、作成日時・ステータス・リソースタイプ・サイズ・暗号化です。** これに加えてボールト名と、論理エアギャップボールト（`VaultType == "LOGICALLY_AIR_GAPPED_BACKUP_VAULT"`）であることを示すバッジを出します。
- **ステータスは `Status` と `StatusMessage` をそのまま表示します。** 復旧ポイントの `Status` の取り得る値は `COMPLETED | PARTIAL | DELETING | EXPIRED | AVAILABLE | STOPPED | CREATING` で、「Completed with issues」はこの列挙に含まれません。これはコピー／バックアップジョブ側の状態であって、復旧ポイントの `Status` ではないため、パネルは「Completed with issues」という文字列に UI ラベルを対応づけません。この状態の監視と意味づけは #461／Observability 側に委ねます。
- **マルウェアスキャン結果の列は出しません。** FSx for ONTAP は Malware Protection for AWS Backup の対象外であり（[E-008]）、同名の列を作ると誤解を生むためです。
- **ソースアカウント ID の列やアカウント切り替えの導線は、このパネルには出しません。** ハンドラは将来のクロスアカウント表示のために `backupVaultAccountId` 引数を受け取れますが、それを設定する UI は持ちません。クロスアカウントの UI は #461、復元の起票は #460 に繰り延べます。

## #460 で実装した承認付き復元

#460 では、本ガイドの「承認付き復元フロー」を、新しいボリュームへの復元の起票として実装しました。復元は `backup:StartRestoreJob` を呼び、選択した復旧ポイントから既存のファイルシステムの中に新しい FSx for ONTAP ボリュームを作成します。ポータルで初めての書き込み・不可逆の AWS Backup 導線です。

- **復元は常に新しいボリュームを作成します。上書きの導線はありません。** AWS Backup のドキュメント [restoring-fsx.html](https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-fsx.html) は 2 つの文を載せています。(1)「既存の Amazon FSx ファイルシステムへは復元できず、個々のファイルやフォルダも復元できない」。(2)「Amazon FSx for NetApp ONTAP は、既存のファイルシステムへのボリュームの復元を許可する」。この 2 文は対象が異なり、矛盾しません。(1) は「ファイルシステムを復元先にすること」の否定で、復元は既存ファイルシステムの中身へは書き込まず、個々のファイル・フォルダも復元しません。(2) は FSx for ONTAP 固有の配置の例外で、作成する新しいボリュームを、新しいファイルシステムではなく、選択した SVM を介して既存のファイルシステムに置けます。したがってポータルは復元を「既存ファイルシステムの中に新しいボリュームを作成する」操作として提示し、既存ボリュームの上書きや個々のファイル復元はできません [E-011]。この規則は参照元リポジトリに [E-011] として登録済みです。
- **二段の承認ゲートを再利用します。** サーバー側のハードゲートは `_require_ack`（`acknowledgeIrreversible` が `true` でなければ `StartRestoreJob` を呼ばず拒否）で、`functions/data-protection/handler.py` と同じ仕組みです。UI は `SnaplockConfirmDialog` と同じ形の確認ダイアログで一文の結果を示し、チェックボックスの同意を取ってから `acknowledgeIrreversible: true` を送ります。復元は加算的（新しいボリュームの作成）なので、SnapLock のような打鍵確認ではなくチェックボックスで足ります。チャット側では `request_action_approval`（"safety-controller"）が破壊的操作の提案前の人の承認アドバイザリとして働きます。
- **新しいボリュームのメタデータだけを集めます。** フォームは名前（必須）・SVM（必須、`restoreAllowedSvmIds` に限定したドロップダウン）・ジャンクションパス（必須）・ボリュームサイズ MB（必須の数値）・ストレージ効率化（任意のチェックボックス、既定オフ）・階層化ポリシー（任意のドロップダウン、既定値）を取ります。復元先の既存ファイルシステムは選択した SVM で決まります（ONTAP の復元メタデータに独立したファイルシステムキーはありません）。ハンドラは SVM を `ALLOWED_SVM_IDS` に照合し、範囲外なら拒否します。
- **成功時は復元ジョブ ID を表示します。進捗のポーリングはしません。** 成功レスポンスの `RestoreJobId` と「進捗は AWS Backup コンソールまたは Observability で確認」の案内を出します。タイマーでの `DescribeRestoreJob` のポーリングは #133／#134（Restore Job State Change の取り込み）と重なるため行いません。
- **復元ジョブの Status は復旧ポイントの Status とは別の列挙です。** 復元ジョブの `Status` は `PENDING | RUNNING | COMPLETED | ABORTED | FAILED` で、#459 の復旧ポイントの `Status`（`COMPLETED | PARTIAL | DELETING | EXPIRED | AVAILABLE | STOPPED | CREATING`）とは別物です。両者を混同しません。
- **Step Functions の人の承認待ち状態（マルチパーティー承認）は繰り延べます。** このリポジトリには人の承認待ち（`waitForTaskToken`／手動承認）のステートマシンがデプロイされていません。`amplify/custom/step-functions.ts` は呼び出し側がコメントアウトされた休眠中の構成です。#460 は `_require_ack` ＋ 確認ダイアログ ＋ チャットのアドバイザリで承認を取り、ステートマシンによる多者承認は後続 Issue に回します。
- **実際の復元の成功確認は Issue のチェックボックスに繰り延べます。** アカウントに復旧ポイントが存在しないため、#460 は `StartRestoreJob`／`DescribeRestoreJob` をモックした単体テストだけを載せます。

## 後続 Issue

本ガイドは次の 3 本の後続 Issue が実装する設計枠です。各 Issue は本ガイドのどの部分を実装するかを対応づけます。

- [#459](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/issues/459) — 復旧点の一覧（読み取り専用）。本ガイドの「ポータルへの接続点」の一覧パネル。
- [#460](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/issues/460) — 承認付き復元。本ガイドの承認付き復元フローと、既存の承認・ガードの再利用。
- [#461](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/issues/461) — クロスリージョン・クロスアカウントの可視化。本ガイドの該当節。

## 参照

AWS の仕様はこれらが持ちます。本ガイドは再導出せず、設計の判断材料として引きます。

- [AWS Backup Logically Air-Gapped Vault for Amazon FSx for NetApp ONTAP](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/blob/main/docs/data-protection/aws-backup-logically-air-gapped-vault.md) — ボールトの前提条件（カスタマーマネージドキー必須、AWS マネージドキーのファイルシステムはコピーされず「Completed with issues」、RW ボリュームのみ）、構成の選択肢、復元と復元テスト、隔離方式の選び方。
- [Ransomware Recovery Runbook — Option D](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/blob/main/docs/runbooks/ransomware-recovery.md) の「Option D: 論理エアギャップボールトからの復旧」 — 共有先の復旧アカウントでの復元（`list-recovery-points-by-backup-vault` に `--backup-vault-account-id`、`start-restore-job` で新しいボリュームへ復元）。
