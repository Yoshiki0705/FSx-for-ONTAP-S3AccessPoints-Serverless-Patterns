# ポータル認可モデル

🌐 **Language / 言語**: 日本語 | [English](../en/portal-authorization-model.md)

> Cognito グループによるポータル機能のアクセス制御。すべての操作は AppSync 認可レイヤーで強制されます。フロントエンドはグループ所属に基づいて UI を描画しますが、バックエンドは UI の状態に関係なく不正な呼び出しを拒否します。

## 概要

ポータルは **Amazon Cognito User Pool Groups** でロールベースアクセス制御を実装しています。AppSync スキーマレベルの認可 (`allow.groups(["storage-admin"])`) により、指定された管理者のみが ONTAP インフラへの書き込み操作を実行できます。

| | Authenticated（全ユーザー） | storage-admin グループ |
|---|---|---|
| **ロール** | サインイン済みの全ユーザー | ストレージ管理者 |
| **アクセス** | 読み取り + AI 処理 | 全読み取り + 書き込み + ONTAP 設定変更 |
| **可能な操作** | ファイル閲覧/DL/UL | 左列のすべてに加えて: |
| | Snapshot/ARP/AI ステータス表示 | Volume 作成/リサイズ/削除 |
| | AI 処理ジョブ起動 | クォータルール管理 |
| | Athena SQL, Bedrock Q&A | Export Policy/SMB 共有 CRUD |
| | Rekognition, Quick MCP | QoS ポリシー管理 |
| | Presigned URL 生成 | SnapLock 保持期間設定 |
| | 最近のファイル, お気に入り, タグ | Qtree 管理 |
| | FlexClone 復元 | ARP/AI 状態変更 + 一括有効化 |
| | 保護サマリー表示 | Snapshot 作成/削除/ロック |
| | | Tamperproof Snapshot 設定 |
| | | 脅威封じ込め（ブロック/解除） |
| | | CIFS 共有管理 |
| | | ストレージ効率表示 |
| **不可** | ONTAP 設定変更 | |
| | ユーザーのブロック/解除 | |
| | ARP 状態変更 | |
| | ボリューム削除 | |
| | クォータ/ポリシー管理 | |
| **強制ポイント** | AppSync: `allow.authenticated()` | AppSync: `allow.groups(["storage-admin"])` |

## 2 軸のグループ: role と scope

上の表は `enforceRoles` を **`false`** にしたときの姿です。既定は **`true`** なので、
書き込み系の `fileMutation` / `folderMutation` は `contributor` 以上を要求します。
この節はその 2 軸を説明します。

**role を持たない利用者は閲覧・プレビュー・ダウンロード・検索はできて、書き込みができません。**
これは意図した状態で、管理系 5 エンドポイントが以前から（`enforceRoles` に関係なく）
`storage-admin` を要求してきたのと同じ形です——このポータルは元々、グループを付与するまで
完全には使えません。新規デプロイの手順は後述の「最初の 1 人」にあります。

グループは 2 軸に分かれていて、**それぞれ強制される場所が違います**。1 軸にまとめると
両方の場所で強制しなければならなくなるので、分けてあります。

| 軸 | 何を決めるか | どこで強制されるか |
|---|---|---|
| **role** | どの操作を呼べるか | AppSync の認可（`allow.groups`） |
| **scope** | どのデータに届くか | S3 Access Point + パス境界（Lambda） |

利用者は role を 1 つ、scope を 1 つ持ちます。積（6 通り）のグループを作らないのは、
`cognito:groups` が配列で、1 つずつ持たせるのが自然な表現だからです。

### role（4 種類）

| role | できること |
|---|---|
| `viewer` | 閲覧とダウンロードのみ |
| `contributor` | 加えて書き込み: アップロード、リネーム、移動、ゴミ箱、フォルダ作成 |
| `storage-admin` | 加えて ONTAP 設定と分析コンソール（既存のグループ。名前は変更していません） |
| `auditor` | 監査証跡の閲覧 |

`auditor` は `viewer` の上位ではなく**直交**です。「誰が何をしたかを読めて、変更はできない」
役割なので、読み書きの階段の 1 段ではありません。したがって `queryAuditLog` は
`auditor` と `storage-admin` だけを許可し、`viewer` を含めません。

### scope（2 種類）

| scope | 意味 |
|---|---|
| `internal` | 組織内。ファイルシステム上に Windows / UNIX アカウントを持つ |
| `external` | 組織外。ONTAP identity を持たず、メールアドレスだけで識別される |

### `external` が効く 3 か所

| 対象 | 挙動 | 変更方法 |
|---|---|---|
| パス境界 | `groupPathPrefixes` の外に出られない。`storage-admin` の迂回も無効になる | `groupPathPrefixes` |
| AI 系 6 エンドポイント | 既定で拒否（ファイル内容がモデルに渡る + トークン課金） | `externalDefaults.aiEnabled` |
| 共有リンク | role ごとに可否を設定。既定は全 role 拒否 | `externalDefaults.shareLinksByRole` |

**`storage-admin` の迂回制限は「`external` を持っていないこと」が条件です**
（`internal` を持つことではありません）。既にデプロイ済みの管理者はどちらの scope も
持っていないため、`internal` を要求すると出荷した瞬間に全員が制限され、これは障害として
現れます。既定の側に倒れる条件を選んでいます。

### 共有リンクは「拒否」ではなく「期限の上限」

同じ AppSync クエリ `getPresignedUrl` が、プレビュー・ダウンロードボタン・共有ダイアログの
3 つから呼ばれます。リクエストからは区別できません（共有ダイアログの最短 TTL 300 秒は
プレビューと同じ値です）。`purpose` のようなフラグを足しても、送る内容を決めるのは
呼び出し側なので判定には使えません。

そこで**期限を上限で抑えます**。role が共有リンクを許されていない外部利用者は、
プレビュー（300 秒）とダウンロード（60 秒）はそのまま使えて、それより長い TTL が
300 秒に切り詰められます。

> **セキュリティに関する補足**: これは**露出時間を短くする**もので、転送を防ぐものでは
> ありません。presigned URL は有効な間、AWS 資格情報なしで誰でも使えます。変わるのは
> 「どれだけの間」だけです。

一方、**渡すことだけが目的のエンドポイントは期限ではなく拒否**します。QR コード
（`generateQrCode`）と、未サインインの相手に渡すアップロードリンク
（`createUploadLink`、最大 24 時間の書き込み資格情報）です。セッション内で保つべき用途が
無いので、切り詰める意味がありません。

### アップロードタブは AppSync を通らない

**この 1 か所だけは AppSync が判定しません。** アップロードタブ
（`@aws-amplify/ui-react-storage`）はブラウザから Identity Pool の資格情報で S3 を直接呼ぶため、
`enforceRoles` もパスプレフィックスも（どちらも Lambda ハンドラ内の判定なので）かかりません。
**選択された IAM ロールが与えるものが、そのタブができることの全部です。**

Amplify Gen2 は `defineAuth` に宣言した各グループに IAM ロールを作り、グループの `RoleArn` に
設定し、Identity Pool を `Type: Token` で紐付けます。Cognito は `cognito:preferred_role`
——**所属グループのうち precedence が最小のもののロール**——を返します
（[CreateGroup: Precedence](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_CreateGroup.html)）。

デプロイ済みのプールで実測しました（2026-08-27、ap-northeast-1）。

| 利用者 | 引き受けたロール | S3 の結果 |
|---|---|---|
| `contributor` + `external` | contributor **グループ**ロール | `AccessDenied`（ListBucket） |
| グループ無し | authenticated ロール | どのプレフィックス設定も許可していない位置への PutObject が**成功** |

つまり以前は、**役割を与えられた利用者はアップロードタブが動かず、役割を与えられていない
利用者だけが任意の位置に書けていました。** どちらも意図した挙動ではありません。

現在は付与先をグループロールに移し、precedence を明示しています。

| グループ | precedence | 直接 S3 |
|---|---|---|
| `external` | 0 | **なし** |
| `storage-admin` | 1 | 読み + 書き |
| `contributor` | 2 | 読み + 書き |
| `viewer` | 3 | 読みのみ |
| `auditor` | 4 | 読みのみ |
| `internal` | 5 | 読みのみ |
| （グループ無し） | — | 読みのみ（authenticated ロール） |

**アクセスポイントの ARN は、リージョンとアカウントがデプロイ先で埋められます。** 既定の `arn:aws:s3:*:*:accesspoint/*` は全アカウントの全アクセスポイントを許可しますが、アクセスポイントはエイリアスで addressing され 1 アカウント内で解決するので、他アカウントを含める必要がありません（`scopeS3ApArns`）。**アクセスポイント名のワイルドカードは残します**——テナント分離に効くのはそちらで、どのアクセスポイントが存在するかは運用者しか知らないためです。`groupApMapping` を使っている場合に限り synth で拒否します。

**`external` を先頭に置くことが要点です。** 選ばれるロールは 1 つなので、1 つの順序で
honour できる軸は 1 つだけです。外部利用者については scope が勝たなければなりません——
彼らの範囲はパスプレフィックスで定義され、**全外部利用者が共有するロールのポリシーでは
それを表現できない**（Identity Pool のセッションに `cognito:groups` 条件キーはありません）
ためです。このロールに何も与えないことで直接経路を閉じ、プレフィックスが効く AppSync 経路
だけを残します。`internal` を最後に置くのは対称の理由です——role より上位に来ると、
全内部利用者が同じロールに寄せられ、role 軸が何も決めなくなります。

precedence を Amplify の既定（`ALL_PORTAL_GROUPS` の添字）に任せられないのは、その順序が
`viewer` を `contributor` より上位にするためです。両方を持つ利用者が読み取り専用に落ち、
**複数 role では最も緩いものが効く**という AppSync 側の規則と逆になります。

> **セキュリティに関する補足**: 2 つのグループが同じ precedence を持つと
> `cognito:preferred_role` は**設定されません**。その場合 Identity Pool は
> `AmbiguousRoleResolution`（= authenticated ロール）に落ちるので、両グループの全員が
> 自分の付与ではなく読み取り専用の既定を得ます。`directS3Problems()` が synth で止めます。

外部利用者にファイルを渡してもらう経路は、アップロードタブではなく**アップロードリンク**
（`createUploadLink`）です。こちらは AppSync 経由なのでプレフィックスが効きます。

### アカウントの作り方と MFA

この 2 つは以前は固定値でした。**固定値は「このデプロイのために誰かが決めた」ように読めますが、
実際は誰も選んでいない既定値でした。**

| 設定 | 既定 | 意味 |
|---|---|---|
| `signIn.selfSignUpEnabled` | `false` | アカウントは管理者が作る。`admin-create-user` が唯一の入口 |
| `signIn.mfa` | `"OPTIONAL"` | MFA を使うかどうかは利用者が各自で決める |

以前はこの 2 つが `true` / `false`、つまり**サインイン画面に到達できる人は誰でも登録でき、
登録した利用者はアップロードと削除ができる**状態が既定でした。後方互換のためでしたが、
このリポジトリをフォークして使っている利用者は居ないため、互換性を保つ対象が存在しませんでした。
現在はどちらも制限側が既定です。

> **セキュリティに関する補足**: 環境変数は**制限を外す側の語を正確に書かないと外れません**
> （`AMPLIFY_PORTAL_SELF_SIGN_UP=true` / `AMPLIFY_PORTAL_ENFORCE_ROLES=false`）。
> 以前は `ENFORCE_ROLES=treu` のような綴り間違いが「true ではない」と読まれて
> **認可規則を黙って外していました**。誤記が制限側に落ちる向きに変えてあります。

`"OPTIONAL"` は正確に読む必要があります。**各利用者が選ぶ**という意味なので、
探しに行かない人にとっては `"OFF"` です。全セッションで MFA を成立させたいなら
`"REQUIRED"` です。

自己サインアップは既定で切れているので、招待だけが入口です。MFA を全セッションで
成立させたい場合はここも変えます（既定は各自任せの `"OPTIONAL"`）。

```ts
// portal-config.ts — selfSignUpEnabled は既定値。MFA だけが既定からの変更
signIn: {
  selfSignUpEnabled: false,
  mfa: "REQUIRED",
},
```

```bash
# 招待してアカウントを作る
aws cognito-idp admin-create-user --user-pool-id <pool> \
  --username partner@example.net \
  --user-attributes Name=email,Value=partner@example.net Name=email_verified,Value=true
```

こうすると入口が招待だけになり、監査証跡の意味も変わります——**すべてのアカウントが
「誰が発行したか」に辿れる**ようになります。

> **実装上の注記**: 自己サインアップは `defineAuth` に対応する項目がなく、
> `@aws-amplify/auth-construct` の既定は `ALLOW_SELF_SIGN_UP: true` です。そのため
> `backend.ts` が L1 の `AdminCreateUserConfig.AllowAdminCreateUserOnly` を
> `addPropertyOverride` で上書きします。オブジェクト全体を代入しないのは、同じ
> オブジェクトに招待メールのテンプレートが入る可能性があり、置き換えるとエラーなしで
> それが消えるためです。

### 最初の 1 人、そして 2 人目以降

`enforceRoles` が既定で有効なので、**役割の付与がデプロイ後の最初の作業**です。自己サインアップ
も既定で閉じているため、アカウントを作る人と役割を付ける人は同じ操作者になります。

```bash
# 1. 自分のアカウントを作る（自己サインアップは閉じている）
aws cognito-idp admin-create-user --user-pool-id <pool> \
  --username you@example.com \
  --user-attributes Name=email,Value=you@example.com Name=email_verified,Value=true

# 2. 役割と scope を付与する（冪等。--apply が無ければ dry run）
make portal-grant-roles ARGS='--apply --assign you@example.com=storage-admin,internal'

# 3. サインイン
```

2 人目以降も同じ順です。**既にサインインしている利用者に付与した場合は、サインアウトと
サインインが必要です**——グループは ID トークンに入るので、付与前に発行されたトークンには
載っていません。付与したのに変わらないという報告のほとんどはこれです。

`make portal-grant-roles` は 3 通りの結果を返します（付与する / 既に持っている / 拒否）。

`make portal-grant-roles` は 3 通りの結果を返します（付与する / 既に持っている /
拒否）。拒否になるのは、role を 2 つ指定した、scope を両方指定した、scope を指定して
いない、pool にまだそのグループが無い、といった場合です。**グループをスクリプト側で
作りません**——`defineAuth` の管理外のグループが残り、次のデプロイで drift 検査が
見つけて理由が分からなくなるためです。

### 「入っているのに効かない」設定の synth での停止

`groupPathPrefixes` の prefix に末尾の `/` が無い（`teams/a` は `teams/ab/` にも一致する）、
`shareLinksByRole` のキーに role でない名前を書いた（`{"external": true}` は「外部利用者に
許可」と読めますが、role を見るので誰にも一致しません）、`groupApMapping` の alias が
空文字、prefix が空リスト（「何も許さない」と読めて実際は「無制限」）。いずれも
デプロイは成功し、実行時にもエラーになりません。`backend.ts` が synth で止めます。

## 監査の 2 つのソース

監査タブには**別々のセクション**として 2 つのソースがあります。片方が他方の代わりになりません。

| ソース | 記録するもの | 誰が操作したか | 空だったときの意味 |
|---|---|---|---|
| CloudTrail (S3 データイベント) | S3 への到達すべて | **分からない**（呼び出し元は Access Point の IAM ロールで、ポータル利用者全員が同一プリンシパル） | その期間にオブジェクトアクセスが無かった |
| ポータル操作履歴 | ポータルへのリクエスト | Cognito ユーザー | **ポータル経由の操作が無かった**（ポータルを経由しないアクセスは含まれない） |

統合したテーブルにしていないのは、`user` 列の意味が行ごとに変わってしまうからです。

### ポータル操作履歴に残る操作

| action | いつ書かれるか |
|---|---|
| `SHARE_LINK` | `getPresignedUrl` が URL を発行したとき。プレビュー・ダウンロード・共有ダイアログは同じクエリなので**区別できません** |
| `DOWNLOAD` | フォルダ ZIP ダウンロード。URL を辿るかどうかに関係なく、ファイルはこの時点で読まれています |
| `UPLOAD_LINK` | `createUploadLink` がアップロード用 URL を発行したとき |
| `DELETE` | ゴミ箱への移動（`reversible: true`）と完全削除（`reversible: false`） |

各行には操作時点の**グループも記録**されます。グループ所属は変わるので、利用者名だけでは
「そのとき何を持っていたか」が後から分かりません。

保持は 90 日（`ttl`）です。テーブルはコード上 `RETAIN` ですが、**sandbox では効きません**（実測 2026-08-27: sandbox は removal policy を一律 `Delete` に上書きする）。branch デプロイで尊重されるかは未確認です。

> **以前の状態**: この台帳は `URL_AUDIT_TABLE_NAME` という環境変数で名前を受け取り、
> **既定は空文字**でした。ハンドラは名前が空のとき書き込みを飛ばすので、**手でこの変数を
> 設定していないデプロイでは台帳が存在せず、そのことを何も知らせませんでした**。
> テーブルはスタックが作るようになり、IAM も `*` から当該テーブルの ARN に絞りました。

> **保持期間について**: 以前のインライン実装は各行を **URL の有効期限 + 1 日**で消して
> いました。つまり「誰にアクセスを渡したか」の記録が、アクセス自体の数日後に消えていました。
> 記録が対象より短命だと、後から訊かれた質問に答えられません——監査の質問は後から来ます。

### 権限

`queryAuditLog` は `auditor` と `storage-admin` のみです（`enforceRoles` は既定で有効。
`false` にすると監査証跡もサインイン済みの全員に開きます）。
`viewer` を含めていないのは、ファイルを読めることが**他人の操作履歴を読めること**を
意味しないからです。読み取りは `dynamodb:Scan` のみで、書き込み権限は与えていません
——監査経路が自分の報告する記録を書き換えられてはいけません。

## 機能別認可マトリクス

### Browse セクション（認証済み全ユーザー）

| 機能 | 認可レベル | AppSync 操作 |
|------|-----------|-------------|
| ファイル一覧 | authenticated | `listFiles` query |
| ファイル DL（Presigned URL） | authenticated | `getPresignedUrl` query |
| ファイル UL（Storage Browser） | `contributor` / `storage-admin`、かつ `external` でない | グループロールの IAM ポリシー（[AppSync を通らない](#アップロードタブは-appsync-を通らない)） |
| 画像/PDF/DOCX プレビュー | authenticated | `getPresignedUrl` query |
| 共有リンク生成 | authenticated | `getPresignedUrl` mutation |
| 最近のファイル | authenticated (owner-scoped) | `RecentFile` model (owner auth) |
| お気に入り | authenticated (owner-scoped) | `Favorite` model (owner auth) |
| ファイルタグ | authenticated (owner-scoped) | `FileTag` model (owner auth) |

### AI & Processing セクション（認証済み全ユーザー）

| 機能 | 認可レベル | AppSync 操作 |
|------|-----------|-------------|
| AI 処理ジョブ起動 | authenticated | `startProcessing` mutation |
| ジョブ状態確認 | authenticated | `getJobStatus` query |
| ジョブ実行履歴 | authenticated (owner-scoped) | `JobExecution` model |
| Bedrock Q&A | authenticated | `askBedrock` mutation |
| Rekognition 画像分析 | authenticated | `detectObjects` mutation |
| Athena SQL クエリ | authenticated | `runAthenaQuery` mutation |
| FlexClone 復元 | authenticated | `startProcessing` (FC7 パターン) |

### Data Protection セクション（混在）

| 機能 | 認可レベル | AppSync 操作 |
|------|-----------|-------------|
| Snapshot 一覧表示 | authenticated | `getSnapshotsWithLockStatus` query |
| ARP/AI ステータス表示 | authenticated | `getArpStatus` query |
| SnapLock ステータス表示 | authenticated | `getSnaplockStatus` query |
| 保護サマリー表示 | authenticated | `getProtectionSummary` query |
| **SMB ユーザーブロック** | **storage-admin** | `blockSmbUser` mutation |
| **NFS IP ブロック** | **storage-admin** | `blockNfsIp` mutation |
| **脅威封じ込め** | **storage-admin** | `containThreat` mutation |
| **ブロック解除** | **storage-admin** | `unblockSmbUser`/`unblockNfsIp` |
| **セッション切断** | **storage-admin** | `disconnectSessions` mutation |
| 有効なブロック一覧 | authenticated | `listActiveBlocks` query |

### Admin セクション（storage-admin のみ）

| 機能 | 認可レベル | AppSync 操作 |
|------|-----------|-------------|
| **リソース管理** | | |
| Volume CRUD | storage-admin | `listVolumes`/`createVolume`/`resizeVolume`/`deleteVolume` |
| クォータ管理 | storage-admin | `listQuotaRules`/`createQuotaRule`/`deleteQuotaRule`/`getQuotaReport` |
| Export Policy ルール | storage-admin | `listExportPolicies`/`createExportPolicyRule`/`deleteExportPolicyRule` |
| CIFS/SMB 共有 | storage-admin | `listCifsShares`/`createCifsShare`/`deleteCifsShare` |
| Qtree 管理 | storage-admin | `listQtrees`/`createQtree`/`deleteQtree` |
| QoS ポリシー | storage-admin | `listQosPolicies`/`createQosPolicy`/`deleteQosPolicy`/`assignQosToVolume` |
| SnapLock 設定 | storage-admin | `getSnaplockConfigAdmin`/`updateSnaplockRetention` |
| ストレージ効率 | storage-admin | `getEfficiencyStats` |
| **ARP/AI 管理** | | |
| 全ボリューム ARP 状態一覧 | storage-admin | `listArpVolumes` |
| ARP 状態変更 | storage-admin | `updateArpStateAdmin` |
| ARP 一括有効化 | storage-admin | `enableArpBulk` |
| 疑わしいファイル表示/クリア | storage-admin | `getArpSuspectsAdmin`/`clearArpSuspects` |
| サージパラメータ調整 | storage-admin | `updateArpSurgeParams` |
| **スナップショット管理** | | |
| スナップショット作成 | storage-admin | `createSnapshot` |
| スナップショット削除 | storage-admin | `deleteSnapshot` |
| スナップショットロック（tamperproof） | storage-admin | `lockSnapshot` |
| ARP 状態更新 | storage-admin | `updateArpState` |
| 保持ポリシー更新 | storage-admin | `updateRetentionPolicy` |
| スナップショットポリシー管理 | storage-admin | `listSnapshotPolicies`/`createSnapshotPolicy` |
| Tamperproof ロック有効化 | storage-admin | `enableSnapshotLocking` |

## storage-admin グループへのユーザー追加

```bash
# AWS CLI
aws cognito-idp admin-add-user-to-group \
  --user-pool-id <user-pool-id> \
  --username <user-email> \
  --group-name storage-admin

# AWS Console
# Cognito → User Pools → <pool> → Groups → storage-admin → Add users
```

## storage-admin グループの作成

Amplify バックエンド（`amplify/auth/resource.ts`）で自動作成されます。手動作成する場合:

```bash
aws cognito-idp create-group \
  --user-pool-id <user-pool-id> \
  --group-name storage-admin \
  --description "Storage administrators with ONTAP management access"
```

## セキュリティ設計原則

1. **多層防御**: フロントエンド UI をバイパスされても AppSync が不正な呼び出しを拒否
2. **最小権限**: 読み取り操作は広く許可し、書き込み操作は明示的なグループ所属を要求
3. **Owner スコープ**: 個人データ（お気に入り、履歴、タグ）は Amplify の `allow.owner()` で自分のものだけ表示
4. **監査証跡**: 全管理操作は `userId` を Lambda ペイロードに含み、CloudTrail で記録
5. **保護アカウント**: storage-admin でも `fsxadmin`/`administrator` はブロック不可（`ontap_response.py` の安全弁）
6. **確認ゲート**: 破壊的操作は、ブラウザのダイアログだけでなく Lambda のペイロードに明示的な `confirm: true` を要求します。対象は `deleteVolume`、`deleteExportPolicy`、`deleteCifsShare`、SnapMirror の `break`/`resync`/`delete`、Vscan と FPolicy のポリシー削除、クラスターピア削除、および ARP の封じ込めアクション全部（`blockSmbUser`、`blockNfsIp`、`containThreat`、`disconnectSessions`）です。解除系は意図的にゲートしていません — アクセスを戻す操作であり、誤ったブロックから復帰する経路に確認を挟むと回復が遅れるだけです。
7. **入力は SQL とリクエストパスの両方で検証する**: 監査ログの Athena クエリに入る値（`fileKeyPrefix`、`startDate`、`endDate`、`eventType`、`maxResults`）は、パターン検証を通してから、シングルクォートを二重化してリテラル化します。LIKE のメタ文字（`%`、`_`）もエスケープするため、プレフィックスはワイルドカードとして解釈されません。ONTAP のリクエストパスは、呼び出し側の名前を percent-encode し、`..` セグメントと制御文字を `_ontap_request` の入口で拒否します。パスの検証を各アクションに任せず 1 箇所に置いているのは、同じ関数を 110 以上のアクションが通るためです。
8. **有効期限とスイープ**: ブロックには既定 24 時間の有効期限が付き、期限を過ぎたものは定期実行のスイープが解除します。ブロック時に 1 時間〜7 日、または「無期限」を明示的に選べます。API 経由の上限は既定 30 日（`maxBlockTtlHours`、0 で上限なし）で、これは安全な数字というより道具の切り替え点です — deny ルールは 1 SVM にしか効かないため、それより長く締め出す必要がある主体はディレクトリ側で無効化すべきです。上限超過は拒否し、クランプはしません。ONTAP の name-mapping と export-policy のルールにはタイムスタンプがないため、期限はポータル側の台帳（DynamoDB）で管理し、スイープはその台帳にある行だけを対象にします。外部で設定されたブロックは「ポータル管理外」として解除しません。運用上の意味は [封じ込めの境界](./arp-ai-isolation-demo-guide.md) を参照してください。

## Lambda を直接呼ばれた場合の扱い

監査証跡の主体（`createdBy` / `createdVia`）は、呼び出しが AppSync 経由かどうかで決まります。リゾルバ `arp-dispatch.js` が Cognito の identity から `userId` と `invokedVia: "appsync"` を注入し、Lambda は両方が揃っている場合だけユーザーに帰属させ、それ以外は `unattributed` / `direct-invoke` として記録します。

**`lambda:InvokeFunction` を持つ主体は、この 2 つのフィールドを自分で詰めて任意の名前に帰属させられます。** 関数の内部からこれを見分ける方法はありません。

### スタック側で防げない理由

同一アカウント内では、**アイデンティティベースのポリシーとリソースベースのポリシーのどちらかが許可していれば呼び出しは成立します**。そして Lambda の権限 API（`AddPermission`）が書けるのは Allow ステートメントだけです。つまりこのスタックにリソースポリシーを足しても、既に `lambda:InvokeFunction` を持つ主体から権限を取り上げることはできません。増やすことしかできません。

実際の防止レイヤーは次の 2 つで、いずれもこのスタックの外にあります。

1. **アイデンティティベースのポリシー** — 誰に `lambda:InvokeFunction` を与えるか
2. **SCP または Permissions Boundary** — 組織レベルで、想定した経路以外からの呼び出しを禁止する

### SCP の例

ポータルの ARP 関数を、AppSync のデータソースロールと封じ込めスイープの EventBridge ルール以外から呼べないようにする例です。`aws:PrincipalArn` の値は自環境のものに置き換えてください。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyDirectInvokeOfPortalContainment",
      "Effect": "Deny",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:<region>:<account-id>:function:*ArpResponseFunction*",
      "Condition": {
        "ArnNotLike": {
          "aws:PrincipalArn": [
            "arn:aws:iam::<account-id>:role/*AppSync*DataSource*",
            "arn:aws:iam::<account-id>:role/*ContainmentBlockSweep*"
          ]
        }
      }
    }
  ]
}
```

> **運用上の注意**: これを適用すると `scripts/portal-probes/` のライブ検証プローブも動かなくなります。プローブを使う環境では、実行に使うロールを `ArnNotLike` の除外リストに加えてください。

### 代わりにスタックが行うこと

防げない代わりに、**黙って起きないようにしています**。状態を変える封じ込めアクションが AppSync の identity を伴わずに届いた場合、EMF メトリクス `UnattributedContainmentActions` を発行し、CloudWatch アラーム（`<stack>-containment-unattributed-action`）が 1 件目で発火します。封じ込めがまだ有効なうちに気づけることが目的です。

台帳の行にも以前から `direct-invoke` は記録されていましたが、それは後から行を読んだ人にしか見えませんでした。

`scripts/portal-probes/` を実行すると、このアラームは意図的に発火します。プローブは実際に「ポータル外からの状態変更」を行っているため、除外するとアラームが監視したい事象そのものの形をした穴になります。

## フロントエンドの挙動

UI は非管理者ユーザーから管理機能を隠しません。代わりに、グレーアウト表示 + 「storage-admin 必要」バッジで表示します。これにより「何ができるか」が可視化され（ユーザーは可能な操作を把握）、一方で不正な実行は防止されます（AppSync が呼び出しを拒否）。

Data Protection の `ArpResponseActions` コンポーネントは、封じ込めフォームを常に描画します。ARP が検知していないユーザーをブロックしたい場面もあるためです。脅威レベルで変わるのはフォーム上部の警告バナーであり、アクションの可用性ではありません。各アクションは実行前に確認を求め、Lambda 側も `confirm: true` を伴わない呼び出しを拒否します。

---

## 関連ドキュメント

- [PoC → 本番移行ガイド](./portal-poc-to-production.md) — 本番向けの認証設定（MFA、グループ、SAML フェデレーション）
- [スケーリングガイド](./portal-scaling-guide.md) — 認証のスケール特性（Cognito 100 万ユーザー、レート制限）
- [アクセシビリティ](./portal-accessibility.md) — ARIA ロールと認可状態の対応
- [実装ガイド](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) — Generic Dispatch の認可スキーマ
- [コンプライアンスガイド](./portal-compliance-guide.md) — アクセス制御を監査する手順
- [Identity 実測結果](./portal-identity-verification-results.md) — 実環境で測った Layer 2 の強度、presigned URL の identity、S3 AP 経由で作られるパーミッション
