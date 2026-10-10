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

監視する状態は次の 3 つです。これらの状態そのもののアラートはポータル側で作らず、Observability 側（[FSx-for-ONTAP-Observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/ja/cyber-resilience-capability-map.md)）に委ねます。ポータルは可視化と導線を持ち、アラートは Observability が持つ、という役割分担です。

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
- **#459 の時点では、ソースアカウント ID の列やアカウント切り替えの導線は出しませんでした。** ハンドラは将来のクロスアカウント表示のために `backupVaultAccountId` 引数を受け取れましたが、それを設定する UI は持っていませんでした。復元の起票は #460、クロスアカウントとクロスリージョンの UI は #461 で入りました。

## #460 で実装した承認付き復元

#460 では、本ガイドの「承認付き復元フロー」を、新しいボリュームへの復元の起票として実装しました。復元は `backup:StartRestoreJob` を呼び、選択した復旧ポイントから既存のファイルシステムの中に新しい FSx for ONTAP ボリュームを作成します。ポータルで初めての書き込み・不可逆の AWS Backup 導線です。

- **復元は常に新しいボリュームを作成します。上書きの導線はありません。** AWS Backup のドキュメント [restoring-fsx.html](https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-fsx.html) は 2 つの文を載せています。(1)「既存の Amazon FSx ファイルシステムへは復元できず、個々のファイルやフォルダも復元できない」。(2)「Amazon FSx for NetApp ONTAP は、既存のファイルシステムへのボリュームの復元を許可する」。この 2 文は対象が異なり、矛盾しません。(1) は「ファイルシステムを復元先にすること」の否定で、復元は既存ファイルシステムの中身へは書き込まず、個々のファイル・フォルダも復元しません。(2) は FSx for ONTAP 固有の配置の例外で、作成する新しいボリュームを、新しいファイルシステムではなく、選択した SVM を介して既存のファイルシステムに置けます。したがってポータルは復元を「既存ファイルシステムの中に新しいボリュームを作成する」操作として提示し、既存ボリュームの上書きや個々のファイル復元はできません [E-011]。この規則は参照元リポジトリに [E-011] として登録済みです。
- **二段の承認ゲートを再利用します。** サーバー側のハードゲートは `_require_ack`（`acknowledgeIrreversible` が `true` でなければ `StartRestoreJob` を呼ばず拒否）で、`functions/data-protection/handler.py` と同じ仕組みです。UI は `SnaplockConfirmDialog` と同じ形の確認ダイアログで一文の結果を示し、チェックボックスの同意を取ってから `acknowledgeIrreversible: true` を送ります。復元は加算的（新しいボリュームの作成）なので、SnapLock のような打鍵確認ではなくチェックボックスで足ります。チャット側では `request_action_approval`（"safety-controller"）が破壊的操作の提案前の人の承認アドバイザリとして働きます。
- **新しいボリュームのメタデータだけを集めます。** フォームは名前（必須）・SVM（必須、`restoreAllowedSvmIds` に限定したドロップダウン）・ジャンクションパス（必須）・ボリュームサイズ MB（必須の数値）・ストレージ効率化（任意のチェックボックス、既定オフ）・階層化ポリシー（任意のドロップダウン、既定値）を取ります。復元先の既存ファイルシステムは選択した SVM で決まります（ONTAP の復元メタデータに独立したファイルシステムキーはありません）。ハンドラは SVM を `ALLOWED_SVM_IDS` に照合し、範囲外なら拒否します。
- **成功時は復元ジョブ ID を表示します。進捗のポーリングはしません。** 成功レスポンスの `RestoreJobId` と「進捗は AWS Backup コンソールまたは Observability で確認」の案内を出します。タイマーでの `DescribeRestoreJob` のポーリングは #133／#134（Restore Job State Change の取り込み）と重なるため行いません。
- **復元ジョブの Status は復旧ポイントの Status とは別の列挙です。** 復元ジョブの `Status` は `PENDING | RUNNING | COMPLETED | ABORTED | FAILED` で、#459 の復旧ポイントの `Status`（`COMPLETED | PARTIAL | DELETING | EXPIRED | AVAILABLE | STOPPED | CREATING`）とは別物です。両者を混同しません。
- **Step Functions の人の承認待ち状態（マルチパーティー承認）は繰り延べます。** このリポジトリには人の承認待ち（`waitForTaskToken`／手動承認）のステートマシンがデプロイされていません。`amplify/custom/step-functions.ts` は呼び出し側がコメントアウトされた休眠中の構成です。#460 は `_require_ack` ＋ 確認ダイアログ ＋ チャットのアドバイザリで承認を取り、ステートマシンによる多者承認は後続 Issue に回します。
- **実際の復元の成功確認は Issue のチェックボックスに繰り延べます。** アカウントに復旧ポイントが存在しないため、#460 は `StartRestoreJob`／`DescribeRestoreJob` をモックした単体テストだけを載せます。

## #461 で実装したクロスアカウント／クロスリージョンの可視化

#461 では、「クロスリージョン・クロスアカウントの可視化」の節で設計した一覧を、既存の「復旧ポイント」パネルに足しました。別のパネルは作らず、同じ表に行を出します。パネルが扱うのは一覧と復元の導線までで、ジョブ失敗や RAM 共有の取り消しの監視は含みません。

- **ボールトの選択肢は 3 つです。** 関数自身のリージョンにある、このアカウントの設定済みボールト（#459 の表示そのまま）、このアカウントのボールト（選択したリージョンの `ListBackupVaults`）、他のアカウントから RAM で共有されたボールト（同じリージョンの `ListBackupVaults` に `ByShared=True`）です。共有ボールトは所有アカウント ID とボールト名の組で選び、手入力の欄はありません。RAM で共有できるボールトの種類は LAG ボールトです（[AWS Backup の LAG ボールトの文書](https://docs.aws.amazon.com/aws-backup/latest/devguide/logicallyairgappedvault.html)）。
- **リージョンは 1 回の要求で 1 つだけ引きます。** 選べるのは関数自身のリージョンと、`AMPLIFY_PORTAL_BACKUP_REGIONS` に挙げたリージョンです。それ以外はハンドラが `RegionNotAllowed` で拒否します。`backup:ListBackupVaults` の許可はリソース `*` なので、IAM はリージョンを限定していません。この許可リストが呼び出し先を限定します。設定が空のとき、リージョンの選択欄は出ません。全リージョンへ並行して問い合わせる方式は採りませんでした。1 要求が N 回の API 呼び出しになって関数のタイムアウト（30 秒）の中に収める必要が生じ、無効なオプトインリージョンなどでの部分失敗を仕様に持ち込むためです。リージョンが 3 つ以上あり、1 画面で全体を見たいという要望が出たときに再検討します。
- **ホームリージョン以外と他アカウントのボールトは、名前を必ず指定します。** 設定済みのボールト名は、このアカウントのホームリージョンでだけ意味を持つためです。名前がないとハンドラは `VaultNameRequired` を返し、設定済みの名前で別のボールトを引くことはしません。
- **共有ボールトは、現在の共有一覧に載っているときだけ引きます。** ハンドラは、同じリージョンの `ListBackupVaults`（`ByShared=True`）に（ボールト名, 所有アカウント）の組があることを確認してから、`BackupVaultAccountId` を付けて `ListRecoveryPointsByBackupVault` を呼びます。載っていなければ `VaultNotShared` を返し、復旧ポイントの一覧は呼びません。任意のアカウント ID の探索を防ぎ、RAM 共有の取り消し・未承認・存在しない組を 1 つの結果で扱うためです。UI は、選択中の共有ボールトが再取得した一覧から消えたとき、既定の表示に戻して通知を出します。
- **アカウント ID は 12 桁の半角数字だけを受け付けます。** 数値型、全角数字、前後に空白のある値は `InvalidParameter` で拒否し、AWS の呼び出しの前に止めます。
- **復元の起票はポータルと同じリージョンの行に限ります。** 復元ハンドラ（`functions/restore`）はリージョンを指定せずにクライアントを作るため、他のリージョンの行は一覧に出ても復元ボタンは無効です。共有ボールトのうち同じリージョンの行は、ボタンが有効のままです。共有ボールトからの復元が実環境で成功するかは、未検証です。ボールトが CMK で暗号化されている場合は、所有者側の KMS キーポリシーに復旧アカウントのロールの許可が要ります（LAG ボールトの文書の KMS の節）。
- **共有ボールトを参照するには、IAM のリソース範囲に ARN を足します。** 新しい IAM アクションは要りません。`ByShared` は `ListBackupVaults` の入力で、既存の `backup:ListBackupVaults`（リソース `*`）で足ります。一方、`backup:ListRecoveryPointsByBackupVault` はポータルのロールで `AMPLIFY_PORTAL_BACKUP_VAULT_ARNS` の ARN だけに許可しています。共有ボールトの ARN には所有者のアカウント ID が入るため（例: `arn:aws:backup:us-east-1:111122223333:backup-vault:shared-lag-vault`）、その ARN を `AMPLIFY_PORTAL_BACKUP_VAULT_ARNS` に足して再デプロイします。ワイルドカード（`backup-vault:*`）は勧めません。cdk-nag の IAM5 に新しい指摘が出る場合があること、共有の範囲が他アカウントの所有者の管理下にあることが理由です。共有ボールトの場合にサービスがどの ARN で評価するかは、実環境で未検証です。
- **認可の範囲は #459 から変えていません。** 復旧ポイントのクエリは `allow.authenticated()` のままです。サインインした全ユーザー（外部メンバーを含む）が、IAM が許す範囲に限り、他アカウントのボールト名・所有アカウント ID・復旧ポイントのメタデータを読めます。実質の境界は IAM のリソース範囲です。一覧を `storage-admin` に限るかどうかは、この設計に含めていません。
- **「Completed with issues」は、復旧ポイントの一覧ではなくバックアップジョブから読み取ります。** Observability 側の記述では、バックアップジョブが `COMPLETED` で状態メッセージを伴う場合として検知しており、EventBridge の個別の状態ではなく、対象はバックアップジョブでコピージョブは含みません。上の「ベンダーの仕様に関する補足」と「#459 で実装した読み取り専用の一覧」にある「コピー／バックアップジョブ側の状態」との差は、ポータル側の根拠を読み直すまで未解消です。パネルは復旧ポイントの `Status` と `StatusMessage` をそのまま表示し、ラベルへの変換はしません。
- **監視は Observability integrations に任せ、ポータルにはリンクだけを置きます。** ジョブの失敗、「Completed with issues」、RAM 共有の取り消しの検知（`BackupJobFailed`、`CopyJobFailed`、`BackupCompletedWithIssues`、`RestoreJobFailed`、`RamShareRevoked`）は、[Observability integrations の機能マップ](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/ja/cyber-resilience-capability-map.md) の Detect 節にある「Backup / LAG-vault event-feed note」が説明しています。実装は [aws-backup-events.yaml](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/shared/templates/aws-backup-events.yaml) です。RAM 取り消しの検知には、CloudTrail の管理イベント証跡が前提です。
- **実環境での確認は済んでいません（未検証）。** このアカウントには共有ボールトも復旧ポイントもないため、次の点は確認していません。(1) `ByShared` が返すのが受け手側の一覧か、所有者側の一覧か。文書の文面からは決められず、未確認です。ハンドラは、所有者が自アカウントのエントリに `ownedByThisAccount` を付け、UI は選択肢から除くので、どちらの返り方でも動きますが、受け手側の一覧が空なら共有ボールトは選択肢に出ません。(2) 共有ボールトの ARN を `AMPLIFY_PORTAL_BACKUP_VAULT_ARNS` に足すとアクセスが通ること。(3) Lambda ランタイム同梱の boto3 が `ByShared` と `BackupVaultAccountId` を受け付けること（手元の boto3 1.43.36 では確認、ランタイム同梱版は未確認）。(4) RAM 共有を取り消してから共有一覧から消えるまでの時間。(5) 共有ボールトからの復元と、他のリージョンの復旧ポイントの復元。(6) 「Completed with issues」のバックアップジョブが作る復旧ポイントの `Status` と `StatusMessage`。単体テストはハンドラも UI も API のスタブで動くので、これらの挙動は固定していません。ボールトの作成は不可逆（コンプライアンスモードの Vault Lock、作成時に固定される暗号化キー）なため、所有者の承認を得た使い捨ての環境で確認します。

## 後続 Issue

本ガイドは次の 3 本の後続 Issue が実装する設計枠です。各 Issue は本ガイドのどの部分を実装するかを対応づけます。

- [#459](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/issues/459) — 復旧点の一覧（読み取り専用）。本ガイドの「ポータルへの接続点」の一覧パネル。
- [#460](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/issues/460) — 承認付き復元。本ガイドの承認付き復元フローと、既存の承認・ガードの再利用。
- [#461](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/issues/461) — クロスリージョン・クロスアカウントの可視化。本ガイドの該当節。

## 参照

AWS の仕様はこれらが持ちます。本ガイドは再導出せず、設計の判断材料として引きます。

- [AWS Backup Logically Air-Gapped Vault for Amazon FSx for NetApp ONTAP](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/blob/main/docs/data-protection/aws-backup-logically-air-gapped-vault.md) — ボールトの前提条件（カスタマーマネージドキー必須、AWS マネージドキーのファイルシステムはコピーされず「Completed with issues」、RW ボリュームのみ）、構成の選択肢、復元と復元テスト、隔離方式の選び方。
- [Ransomware Recovery Runbook — Option D](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/blob/main/docs/runbooks/ransomware-recovery.md) の「Option D: 論理エアギャップボールトからの復旧」 — 共有先の復旧アカウントでの復元（`list-recovery-points-by-backup-vault` に `--backup-vault-account-id`、`start-restore-job` で新しいボリュームへ復元）。
