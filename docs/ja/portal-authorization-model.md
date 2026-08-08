# ポータル認可モデル

🌐 **Language / 言語**: **日本語** | [English](../en/portal-authorization-model.md)

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

## 機能別認可マトリクス

### Browse セクション（認証済み全ユーザー）

| 機能 | 認可レベル | AppSync 操作 |
|------|-----------|-------------|
| ファイル一覧 | authenticated | `listFiles` query |
| ファイル DL（Presigned URL） | authenticated | `getPresignedUrl` query |
| ファイル UL（Storage Browser） | authenticated | Cognito Identity Pool S3 ポリシー |
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
