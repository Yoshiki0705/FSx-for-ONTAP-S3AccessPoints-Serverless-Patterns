# S3 Access Points for FSx for ONTAP — 二段階認可モデル

🌐 **Language / 言語**: 日本語 | [English](s3ap-authorization-model.en.md)

## 概要

Amazon FSx for NetApp ONTAP の S3 Access Point は **二段階認可モデル**を採用しています。S3 API 経由のリクエストがデータに届くには、AWS 側の認可（Layer 1）とファイルシステム側の認可（Layer 2）の**両方**を通る必要があります。

**2 つの層は独立しています。層をまたいだ引き算は起きません。** Layer 1 で許可された操作が Layer 2 で拒否されることも、その逆もあります。

> **設計原則**: S3 API はファイルシステムのセマンティクスを除去しません。S3 Access Point を経由しても、ボリューム上のファイルアクセス権限は引き続き適用されます。

**層ごとに、絞り込みを担うものが違います。** ここを取り違えると、絞ったつもりが絞れていない設計になります。

| 層 | 何を評価するか | この層で絞り込みを担うもの |
|---|---|---|
| **Layer 1: AWS 側の IAM 認可** | 呼び出し元のプリンシパルと `s3:` のアクション | **明示的な拒否**（`Deny`） |
| **Layer 2: ファイルシステム側の権限** | AP に固定した ID（UNIX / Windows ユーザー）が持つファイル権限 | **mode bits / ACL** |

> **Evidence**: 本ドキュメントの実測値はすべて `ap-northeast-1` / ONTAP `9.18.1P3D1` のものです。所見ごとに同一セッションのコントロールを取っています。
> - **2026-08-17 / 08-18**: Layer 1 の評価順序、条件キー、`NotPrincipal`、ポリシーサイズ、Layer 2 の対測定、監査の主体。手順と全結果は [S3 Access Point の権限設計 — 評価順序と、絞り込みを担う 2 つの層](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/domains/security-governance/notes/access-point-authorization-layers.md) にあります。
> - **2026-08-18 / 08-19（本リポジトリで追加測定）**: NTFS ボリュームでの Layer 1 評価、AP ポリシーが受理するアクション 20 件、SLAG が拒否を引き起こす原因、AD 参加 SVM での監査主体、UNIX identity の AP への IAM プリンシパル適用。

## 認可フロー

```
┌─────────────────────────────────────────────────────────────┐
│                    S3 API Request                            │
│            (GetObject / PutObject / ListObjectsV2)          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: AWS-side Authorization                            │
│                                                             │
│  上から順に評価され、決まった時点で終わる:                      │
│  1. 既定は暗黙的な拒否                                        │
│  2. 明示的な拒否が 1 つでもあれば拒否で確定 ← 絞る位置はここ     │
│  3. Organizations の RCP / SCP                              │
│  4. identity-based と AP ポリシー                            │
│     - 同一アカウント: 結合（どちらかが許可すれば通る）           │
│     - 別アカウント:   両方が許可する必要がある                  │
│  5. VPC エンドポイントポリシー（VPC 経由の場合）                │
└─────────────────────────┬───────────────────────────────────┘
                          │ (通過)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: File-system-side Authorization                    │
│                                                             │
│  Access Point に固定した 1 つのファイルシステム ID で認可:      │
│  • UNIX identity   → UNIX セキュリティスタイルのボリューム      │
│    - mode bits または NFSv4 ACL で制御                       │
│  • Windows identity → NTFS スタイルのボリューム                │
│    - Windows ACL で制御                                      │
│                                                             │
│  → 呼び出し元が誰であったかは、この層では区別されない            │
└─────────────────────────────────────────────────────────────┘
```

## Layer 1: AWS-side Authorization

### 評価されるポリシー

| ポリシータイプ | 説明 | 設定場所 |
|--------------|------|---------|
| IAM identity-based policy | 呼び出し元（Lambda Role 等）の権限 | IAM Console |
| S3 Access Point resource policy | AP 自体のリソースポリシー。**バケットポリシーではありません**（裏に S3 バケットが無いため `put-bucket-policy` の対象が存在しません） | `s3control put-access-point-policy` |
| VPC endpoint policy | VPC 制限 AP の場合のエンドポイントポリシー | VPC Console |
| Service Control Policies | Organizations レベルの制御 | AWS Organizations |

**この評価はボリュームのセキュリティスタイルに依存しません。** UNIX スタイルと NTFS スタイルの両方で同じ 12 試行を行い、差は観測されませんでした（NTFS 側は非 AD の SVM に WINDOWS identity の AP を立てて測定）。

### `Allow` を狭く書くことは、絞り込みではない

**同一アカウント内では、identity-based ポリシーと AP ポリシーは結合して評価されます。どちらかが許可すれば通ります。** つまり AP ポリシーは「追加で許可する場所」であって、「ここまでに絞る場所」ではありません。

| ポリシー | 呼び出し元 | 操作 | 結果 |
|---|---|---|---|
| なし | IAM ユーザー | `GetObject` / `ListObjectsV2` | 成功（identity-based だけで許可が成立） |
| ロールのみ `Allow` | IAM ユーザー（**AP ポリシー未記載**） | `GetObject` | **成功** |
| 同上 | ロール | `PutObject`（**`Action` 未記載**） | **成功**（`Action` も結合で決まる） |

**AP ポリシーを付けていないことは、`AccessDenied` の原因になりません。** 同一アカウントでの AP ポリシー省略が正常に動作することは、本リポジトリでも別途実測しています（[AD 参加 SVM の S3 AP 前提条件](ja/ad-joined-svm-s3ap-prerequisites.md#ap-リソースポリシーが必要なケース)）。

> **出典の食い違いについて**: AWS の [Managing access point access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html) は「呼び出し元の identity-based ポリシーが必要な権限を与えており、**かつ** AP のリソースポリシーもその操作を許可する必要がある」と読める書き方をしています。一方、同ページの次段落は「関連するすべてのポリシーを評価する」とだけ述べ、[IAM のポリシー評価ロジック](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic_policy-eval-basics.html)は同一アカウントのリクエストを identity-based と resource-based の**結合**で判定すると明記しています。**実測は結合側と一致します。**

### Layer 1 で絞る — 明示的な拒否

絞る位置は評価ステップ 2 です。明示的な拒否は最初に評価され、当たった時点で以降を見ません。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowPipelineRoleReadOnly",
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::123456789012:role/ProcessingLambdaRole"},
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap/object/*"
      ]
    },
    {
      "Sid": "DenyAnyPrincipalOutsideTheAllowList",
      "Effect": "Deny",
      "Principal": "*",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap/object/*"
      ],
      "Condition": {
        "StringNotEquals": {
          "aws:PrincipalArn": "arn:aws:iam::123456789012:role/ProcessingLambdaRole"
        }
      }
    }
  ]
}
```

**`Deny` の側が本体です。** 上半分だけにすると、前節の表のとおり他の主体がそのまま通ります。実測では、指定ロールは成功し、指定していない管理者権限の IAM ユーザーは `AccessDenied` になりました。

> **セキュリティに関する補足**: `Deny` の `Action` に `s3:*` を書き、`Resource` を AP の ARN にすると、`s3:PutAccessPointPolicy` と `s3:DeleteAccessPointPolicy` も同じ ARN を対象とするため、**ポリシーの管理操作まで拒否してロックアウトする恐れがあります。** 上の例はデータ操作に限定しています。**このロックアウトは実測していません**（復旧に AP の作り直しが必要になる可能性があるため、意図的に試していません）。

### `NotPrincipal` で例外を作らない

**`Deny` + `NotPrincipal` は、例外に指定した主体まで拒否しました。** 何を列挙すれば例外が成立するかの実測結果です。

| `NotPrincipal` に列挙したもの | IAM ユーザー | `AssumeRole` したロール |
|---|---|---|
| 主体の ARN のみ | **拒否** | 拒否 |
| 主体の ARN + **アカウント ARN** | 成功 | 拒否 |
| ロール ARN + アカウント ARN | 拒否 | **拒否** |
| ロール ARN + セッション ARN + アカウント ARN | 拒否 | 成功 |

2 点が読み取れます。**アカウント ARN（`arn:aws:iam::<account>:root`）の併記が必要**で、**ロールの場合はロール ARN と assumed-role セッション ARN の両方が必要**です。セッション名は `AssumeRole` 時に決まり、**`NotPrincipal` はワイルドカードを受け付けません。** つまり「このロールの、任意のセッション」を表現できません。

**ロールを対象にする設計では `NotPrincipal` は使えません。** `Condition` の `StringNotEquals` + `aws:PrincipalArn` を使ってください。`aws:PrincipalArn` は assumed-role セッションに対してロールの ARN に解決されるため、セッション名に依存しません（3 つの異なるセッション名で確認）。

### 条件キーの実測結果

| 条件キー | 何を絞れるか | 実測 |
|---|---|---|
| `aws:PrincipalArn` | 呼び出し元の ARN。セッション名に依存しません | Allow / Deny 両側を確認 |
| `aws:SourceVpce` | 経由した VPC エンドポイント | Allow / Deny 両側を確認 |
| `aws:PrincipalOrgID` | 組織のメンバーシップ | Allow / Deny 両側を確認（別組織のアカウントのプリンシパルで実測） |
| `s3:prefix` | `ListBucket` の対象範囲。`ListBucket` にしか効きません | Allow / Deny 両側を確認 |
| `aws:SecureTransport` | 通信の暗号化 | **Deny 分岐に到達しませんでした**（下記） |

**`aws:SecureTransport` を「平文通信を止めている根拠」として書かないでください。** 署名なし / 署名付きの HTTP リクエストはいずれも HTTP 307 で HTTPS にリダイレクトされ、**認可の評価に到達する前に経路が変わります。** AWS のドキュメントもアクセスポイントは HTTPS のみを受け付け、HTTP にはリダイレクトを返すと明記しています。多層防御として書く分には無害ですが、`false` になる経路がこの AP には存在しません。

### 正規化後で判定されるポリシーサイズの上限

| 適用したポリシー（整形なし JSON） | 結果 |
|---|---|
| 24,620 バイト | 成功 |
| 24,861 バイト | `MalformedPolicy: Normalized policy document exceeds the maximum allowed size` |

**ドキュメント上の上限は 20 KB ですが、判定は正規化後の文書に対して行われます。** 手元の JSON のバイト数を予算として使えません。境界はポリシーの書き方で動きます。`CreateAndAttachS3AccessPoint` の `S3AccessPoint.Policy` がフィールドとして受け付ける 200,000 文字とも一致しません。**上限に近づく設計は避け、AP を分けてください。**

### AP ポリシーで使えないアクション

**20 アクションを 1 つずつ単独で適用して判定しました。**

| 判定 | アクション |
|---|---|
| **拒否** | `s3:GetBucketLocation` / `s3:PutBucketPolicy` / `s3:DeleteBucketPolicy` / `s3:GetBucketVersioning` / `s3:PutBucketVersioning` / `s3:PutBucketNotification` / `s3:PutAccessPointPolicy` |
| 受理 | `s3:ListBucket` / `s3:GetBucketPolicy` / `s3:ListBucketVersions` / `s3:GetBucketNotification` / `s3:ListBucketMultipartUploads` / `s3:AbortMultipartUpload` / `s3:ListMultipartUploadParts` / `s3:GetObjectVersion` / `s3:GetObject` / `s3:DeleteObject` / `s3:PutObjectTagging` / `s3:GetObjectTagging` / `s3:GetObjectAttributes` / `s3:*` |

**エラー本文はどのアクションが無効かを名指ししません。** 返るのは `Policy has invalid action` だけです。**複数のアクションを 1 つのポリシーに入れて拒否されたとき、どれが原因かはこの本文からは分かりません。** 切り分けるには 1 つずつ適用してください。

> **本リポジトリの旧記述を訂正しました。** 以前ここには「拒否されるのは `s3:GetBucketLocation` と
> `s3:ListBucketMultipartUploads` の 2 つ」と書いていましたが、**`s3:ListBucketMultipartUploads` は
> 受理されます**（単独適用で 3/3）。旧記述の出典である
> [実測記録](../solutions/edge/media-ivs-vod-publishing/direct-recording-experiment.md) は
> 両者を同一ポリシーに入れて拒否を観測しており、上記のとおり本文が原因を名指ししないため、
> 拒否を両方に帰属させたものと説明できます。`s3:PutBucketPolicy` の拒否は 3/3 で再現しました。

`s3:GetBucketLocation` は **identity-based ポリシーでは使用できます**（本リポジトリの多くのテンプレートが使用しています）。制約は AP のリソースポリシーに限られます。

**なお `s3:ListObjectsV2` と `s3:HeadBucket` も拒否されますが、理由が別系統です。** これらは IAM のアクション名として存在しません（`ListObjectsV2` と `HeadBucket` に対応する IAM アクションはいずれも `s3:ListBucket`）。**操作が非対応という意味ではありません。**

### IAM ポリシーの ARN 形式

S3 Access Points for FSx for ONTAP では、通常の S3 バケット ARN とは異なる形式を使用します:

```json
{
  "Effect": "Allow",
  "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
  "Resource": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap"
},
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject"],
  "Resource": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap/object/*"
}
```

> **注意**: S3 AP エイリアス（`xxx-ext-s3alias`）を `arn:aws:s3:::` 形式で使用すると IAM では認識されません。必ず `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式を使用してください。AWS の [Troubleshooting access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/troubleshooting-access-points-for-fsxn.html) も、バケット ARN 形式が使われている場合は AP の ARN に修正するよう記述しています。

### クロスアカウントデータアクセスの成立

**「同一アカウント所有が必須」は AP を作る側の制約で、AP を使う側の制約ではありません。**

| 論点 | 実際 |
|---|---|
| 別アカウントのボリュームに AP を作る | できません（ファイルシステムと AP は同一アカウント所有） |
| **別アカウント（別組織）のプリンシパルが AP 経由でデータを読む** | **できます。** AP ポリシーで許可すれば通ります（実測） |

**ここを混同すると設計の選択肢を 1 つ落とします。** データを別アカウントに配るためにコピーを作る判断に流れがちですが、AP ポリシーで相手アカウントを許可すればコピーは不要です。裏返すと、**意図しない共有も AP ポリシー 1 つで起きます。** 組織の外に出したくない場合は `aws:PrincipalOrgID` の `Deny` を置くのが、実測で確認できた止め方です。設計パターンは [クロスアカウント S3 AP](multi-account/cross-account-s3ap.md) にあります。

## Layer 2: File-system-side Authorization

### ファイルシステム ID の役割

S3 Access Point 作成時に指定するファイルシステム ID が、すべての S3 API リクエストの認可に使用されます:

- **読み取り専用ユーザー** を関連付けた場合 → 読み取りリクエストのみ認可、書き込みはブロック
- **読み書きユーザー** を関連付けた場合 → 読み取り・書き込みの両方が認可

**AP ポリシーを一切変えずに、Layer 2 だけで許可と拒否が切り替わります。** 同一の呼び出し元・同一の AP・AP ポリシー無しの状態で、ボリュームルートの所有者と mode bits だけを変えた対の実測です。

| ボリュームルートの `uid` / `gid` / mode bits | AP に固定した UNIX ユーザー | `PutObject` |
|---|---|---|
| `0` / `0` / `755` | uid 7101 のユーザー | **`AccessDenied`** |
| `7101` / `7100` / `755` | 同じユーザー | **成功** |

**この `AccessDenied` は Layer 1 ではなく Layer 2 から返っています。** Layer 1 だけを見ていると、原因をポリシーの中に探し続けることになります。

**Layer 2 由来の `AccessDenied` は、エラー本文が素の `Access Denied` になります。** Layer 1 の明示的な拒否に当たった場合は `with an explicit deny in a resource-based policy` が付くので、本文で層を弁別できます。

### AP に固定する ID に必要な SVM 名前解決

**AWS 側に作るものではありません。** ONTAP の SVM が名前解決できるユーザーである必要があります。

| ID の種類 | 何が必要か | 実測 |
|---|---|---|
| `UNIX` | SVM が名前解決できる UNIX ユーザー | **LDAP も NIS も不要です。** `nsswitch` が `files` のみ・`ldap.enabled=false`・`nis.enabled=false` の SVM で、ローカル UNIX ユーザーにより AP が `AVAILABLE` になり読み書きが通りました |
| `WINDOWS` | SVM が名前解決できる Windows ユーザー | **AD 参加は必須ではありません。** workgroup モードの CIFS サーバーに作ったローカル Windows ユーザーで読み書きが通りました |

AWS の [Troubleshooting access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/troubleshooting-access-points-for-fsxn.html) は、`UnixUser` について ns-switch の `files` ソースで足りることを明記しています。一方 `WindowsUser` については「参加済みの Active Directory ドメイン」の場合だけを記述しており、**上記の workgroup モードの実測はそれより広い結果です。**

> **設計に関する補足**: 「LDAP や AD を用意しないと S3 AP は使えない」ことはありません。一方で**ローカルユーザーは SVM ごとに独立します。** 複数 SVM で同じ ID を使い回す運用や、ID の棚卸しが要件になる場合は、ディレクトリサービスに寄せる判断が別に必要です。

`WindowsUser.Name` に **AD ドメイン接頭辞を付けないでください**（`Admin` は可、`DOMAIN\Admin` は不可。`CIFSSRV\Admin` のような **CIFS サーバー名**の接頭辞は実測で正常動作）。付けると AP の作成は通り `AVAILABLE` になりますが、`HeadBucket` を含むすべてのデータ操作が **503 ServiceUnavailable** を返します（`AccessDenied` ではありません）。詳細は [AD 参加 SVM の S3 AP 前提条件](ja/ad-joined-svm-s3ap-prerequisites.md) にあります。

### セキュリティスタイルとの対応

| ボリュームのセキュリティスタイル | 使用する ID タイプ | 権限制御方式 |
|-------------------------------|-------------------|-------------|
| UNIX | UNIX identity（ユーザー名） | mode-bits / NFSv4 ACLs |
| NTFS | Windows identity（ユーザー名のみ。ドメイン接頭辞なし） | Windows ACLs |

### `FileSystemIdentity` は作成後に変更できない

**変更 API がありません。** Amazon FSx がこのアタッチメントに対して公開している操作は `CreateAndAttachS3AccessPoint`、`DescribeS3AccessPointAttachments`、`DetachAndDeleteS3AccessPoint` の 3 つで、更新の操作が存在しません。

| パラメータ | 作成後に変更 |
|---|---|
| `FileSystemIdentity.Type`（`UNIX` / `WINDOWS`） | **できません** |
| `UnixUser.Name` / `WindowsUser.Name` | **できません** |
| `OntapConfiguration.VolumeId` | **できません**（別ボリュームに向けられません） |
| `S3AccessPoint.VpcConfiguration`（`NetworkOrigin`） | **できません** |
| `S3AccessPoint.Policy` | できます（S3 側の API で） |

**作り直しの範囲は AP 1 つ分**で、ボリュームとデータには影響しません。ただし**エイリアスは変わります**（`<name>-<ランダム>-ext-s3alias` 形式）。エイリアスを設定に埋め込んでいる利用側があると、そこも直すことになります。

**これは権限設計に効きます。** 「あとで読み取り専用の ID に差し替える」ができないため、**用途ごとに AP を分ける**のが実際の運用になります。

### 重要な動作特性

1. **NFS/SMB アクセスへの影響なし**: S3 Access Point をアタッチしても、NFS/SMB 経由の既存アクセスは一切変更されません。AP ポリシーの制限は AP 経由のリクエストにのみ適用されます。

2. **Block Public Access**: FSx for ONTAP にアタッチされた S3 AP は常に Block Public Access が有効であり、変更できません。

3. **MISCONFIGURED 状態**: 次の 2 つの原因で遷移します。Amazon FSx が定期的にチェックし、問題解決時に自動的に `AVAILABLE` に戻ります。
   - ファイルシステム ID が名前解決できなくなった（名前サービスからユーザーが削除された、または名前サービスに到達できない）
   - **アタッチ先ボリュームが offline になった、または unmount された（junction path を失った）**

## Least-Privilege 設計ガイドライン

最小権限の原則を適用するには、**両方のレイヤー**でアクセスを制限する必要があります。**そして層ごとに、担保できることが違います。**

| 担保したいこと | 使う手段 | 理由 |
|---|---|---|
| 特定の主体だけが使える | Layer 1 の**明示的な拒否** + `Condition aws:PrincipalArn` | `Allow` を狭くしても、identity-based と結合して通ります |
| 特定の経路からだけ使える | Layer 1 の明示的な拒否 + `aws:SourceVpce` / `aws:PrincipalOrgID` | 同上 |
| 特定のプレフィックスだけ触れる | Layer 1 の明示的な拒否 + `NotResource`（オブジェクト） + `s3:prefix`（一覧） | `s3:prefix` は `ListBucket` にしか効きません |
| **絶対に書き込めない** | Layer 2 の**書き込み権限を持たない ID を AP に固定** | ポリシー 1 行の変更で書けるようになる状態を避けられます |

**「読み取り専用の AP を作った」は、それだけでは成立しません。** AP ポリシーの `Allow` を `s3:GetObject` だけにしても、管理者権限を持つ主体は同じ AP でそのまま書けます。読み取り専用を担保するなら、**明示的な拒否を書く**か、**書き込み権限を持たない ID を AP に固定する**かのどちらかです。後者は `FileSystemIdentity` が変更できないため、**AP を作る前に決めておく必要があります。**

### Layer 2 での制限例

- 処理対象ディレクトリのみに読み取り権限を持つ専用ユーザーを作成
- root (UID 0) の使用を避ける（全ファイルへのアクセスが許可されるため）
- NTFS 環境では、必要最小限のグループメンバーシップを持つサービスアカウントを使用

## 監査ログに記録される主体

**S3 AP 経由のアクセスは ONTAP のファイルアクセス監査に記録されますが、記録される主体は AP に固定した ID であり、呼び出し元の IAM プリンシパルではありません。** Layer 1 と Layer 2 で主体が分離していることが、そのまま監査の限界になります。

| 論点 | 実際 |
|---|---|
| 呼び出し元の IAM プリンシパル | **分かりません。** 残るのは AP に固定した ID の SID だけで、`SubjectUserName` / `SubjectDomainName` は `Not Present`（名前未解決）。**特定には AWS CloudTrail 側との突き合わせが必要です** |
| **AD 参加 SVM なら名前が解決されるか** | **されません。** DC に到達でき、AP に固定した ID が**実在のドメインアカウント**であっても `Not Present` のままでした（下記） |
| `SubjectIP` による送信元追跡 | **できません。** AWS のサービス側アドレスで、**6 リクエストで 5 個の異なる値**になりました（同一オブジェクトへの連続 2 件でも別値）。**呼び出し元 IP による監査要件はこの経路では満たせません** |
| グループで認可を分ければ監査も主体別に分かれるか | 分かれません。**AP に紐づく 1 つの ID として記録されます** |
| SVM で監査を有効化すれば全ボリュームで記録されるか | **UNIX 実効スタイルで mode bits のみのボリュームは 0 件**でした（同一セッションの NTFS コントロールは 2 件）。mode bits は監査情報を持たず、記録には SACL が必要です |
| `SubjectUserIsLocal` でローカルユーザーか判定できるか | **ローカルユーザーに対して `false` が記録されました。** ただしドメインユーザーに対する `false` は正しい値です（下記） |

### AD 参加 SVM でも `SubjectUserName` は解決されない

**AWS Managed AD に参加させた SVM（`ms_dc` の状態が `ok`）で、WINDOWS タイプ AP の ID に実在のドメインアカウントを指定して測りました。** NTFS ボリュームに監査 ACE を付け、S3 AP 経由の `PutObject` / `GetObject` を実行した結果です。

| フィールド | 記録された値 |
|---|---|
| `Source` | `HTTP`（大半） / `S3`（1 件） |
| `EventID` | `4656`（Create Object） / `4663`（Read Object） |
| `SubjectUserSid` | ドメイン SID（`S-1-5-21-…-1112`） |
| `SubjectUserName` | **`Not Present`** |
| `SubjectDomainName` | **`Not Present`** |
| `SubjectUserIsLocal` | `false`（ドメインユーザーなので**正しい**） |
| `SubjectIP` | 5 個の異なる AWS パブリックアドレス |
| `SubjectUnix Uid` / `Gid` | `65535` / `65535` |

**AD 参加は名前解決の条件ではありません。** workgroup モードのローカルユーザーで観測された `Not Present` は、AD 参加環境にも一般化します。**呼び出し元の特定には CloudTrail との突き合わせが必要**という結論は変わりません。

**`SubjectUserIsLocal` は「常に誤り」ではありません。** ローカルユーザーに `false` が記録されたのは誤りですが、ドメインユーザーに対する `false` は実態と一致します。**この値でローカルか否かを判定しないでください**、が正確な言い方です。

> **管理操作の監査には主体が残ります。** 同じログに含まれる `EventID 4719`（監査ポリシー変更）だけは `SubjectUserName` に実際の管理ユーザー名が入り、`SubjectIP` も実クライアントのプライベート IP でした。**主体が失われるのはデータ操作の監査です。**

> **ガバナンスに関する補足**: **AP を用途別ではなく共用で 1 つ作る設計は、AP ポリシーで呼び出し元を分けられても、ファイルアクセス監査では全員が同じ主体として記録されます。** ファイル単位の操作を主体別に追跡する要件がある場合は、**AP の分割が監査の粒度を決めます。** 本リポジトリのポータルがチーム単位で AP を分けているのはこの理由です。

### UNIX ボリュームへの SLAG における unix→win マッピングの必須化

UNIX ボリュームに監査 ACE を付ける経路として SLAG（storage-level access guard）がありますが、**付けた直後にアクセスが拒否されます。** 5 つの状態で測りました（プローブは NFSv3。同一の拒否は S3 AP 経路でも観測しています）。

| # | SLAG | CIFS サーバー | DC 到達 | unix→win マッピング | 許可 ACE | 結果 |
|---|---|---|---|---|---|---|
| A | なし | なし | — | なし | — | 成功 |
| B | 監査のみ | なし | — | なし | なし | **拒否** |
| B' | 監査のみ | あり | **成功** | なし | なし | **拒否** |
| C | 監査 + 許可 | あり | 成功 | なし | `Everyone` / `full_control` | **拒否** |
| D | 監査 + 許可 | あり | 成功 | **`root` → `<NetBIOS>\Admin`** | あり | **成功に復帰** |

**原因は unix→win の name mapping です。** SLAG は Windows セキュリティ記述子なので、評価にはアクセス元 UNIX ID に対応する Windows 資格情報が必要になります。このマッピングが失敗すると、**SLAG の ACE の内容に関わらず拒否されます。** ONTAP は EMS `secd.nfsAuth.noNameMap` で理由を名指しします（`Successfully authenticated with DC` の直後に `Could not find Windows name 'root'` / `No default Windows user defined`）。

3 点が設計に効きます。

- **S3 AP 固有ではありません。NFS も同時に拒否されます。** ボリューム全体が止まります
- **DC への到達性だけでは足りません**（B'）。対応する Windows アカウントが実在する必要があります
- **許可 ACE を足しても解消しません**（C）。「DACL が空だから」では説明できません

**マッピングを与えれば SLAG を残したまま復帰します**（D）。ただし複数 SVM でこれを維持する運用コストと、ID の対応付けを設計に持ち込む判断が別に発生します。**ファイル単位の監査が要件なら、ボリュームのセキュリティスタイルを設計段階で決めるほうが単純です。**

> **測定範囲**: 復帰（D）は **NFS で確認**しました。拒否側は S3 AP と NFS の両方で観測していますが、S3 AP 経路での復帰は未測定です（対照に使った SVM に ONTAP ネイティブ S3 サーバーがあり、[AP を作成できない](#副産物-ontap-ネイティブ-s3-サーバーによる-ap-作成のブロック)ため）。

## 本プロジェクトでの適用

本リポジトリの各パターンでは、以下の設計を採用しています:

| コンポーネント | Layer 1 設計 | Layer 2 設計 |
|--------------|-------------|-------------|
| Discovery Lambda | 専用ロールの identity-based ポリシーを ListBucket + GetObject に限定 | 対象ボリュームの読み取り権限を持つ UNIX ユーザー |
| Processing Lambda | 同様に GetObject のみ（入力読み取り） | 同上 |
| Output Lambda (FSXN_S3AP mode) | PutObject 追加 | 出力ディレクトリへの書き込み権限を持つユーザー |

**この表の Layer 1 列は「そのロールに与える権限」の話です。** 各 Lambda に専用ロールを付与しているため、そのロールの経路は絞られます。**AP そのものへの経路を絞るものではありません。** 他の主体を止めたい場合は明示的な拒否を書きます。

## トラブルシューティング

**まず落ちた層を切り分けてください。** 同じ `AccessDenied` が両方の層から返るため、層を決めずに調べると原因のない場所を探すことになります。

| 手がかり | 落ちている層 | 最初に見るもの |
|---|---|---|
| エラー本文に `with an explicit deny in a resource-based policy` | Layer 1（明示的な拒否） | AP ポリシーの `Deny` 文とその `Condition` |
| 絞ったつもりの主体が通ってしまう | Layer 1（結合） | **`Allow` しか書いていないこと。** 明示的な拒否を足す |
| 別アカウントから `AccessDenied` | Layer 1（クロスアカウント） | AP ポリシーと、**相手側の identity-based ポリシーの両方** |
| 組織内なのに全員 `AccessDenied` | Layer 1（RCP / SCP） | RCP / SCP。AP ポリシーを直しても変わりません |
| `HeadBucket` は成功するがデータ操作が落ちる | **Layer 2** | AP の ID のファイル権限。AD 参加 SVM ならドメインコントローラーへの到達性 |
| IAM で許可しているのに落ちる | **Layer 2** | 同上 |

| 症状 | 可能性のある原因 | 確認ポイント |
|------|----------------|------------|
| IAM で許可しているのに AccessDenied | ファイルシステム ID の権限不足 | S3 AP に紐づく UNIX/Windows ID のファイル/ディレクトリ権限を確認 |
| ListBucket は成功するが GetObject で AccessDenied | ファイル ACL / export policy / security style の不一致 | 対象ファイルの実効権限を `ls -la` (UNIX) or `icacls` (NTFS) で確認 |
| PutObject が失敗する | ディレクトリ書き込み権限不足 | 親ディレクトリの書き込み権限を確認。ファイルシステム ID が read-only の場合は書き込み不可 |
| `AccessDenied` on ListObjectsV2 / GetObject | IAM ポリシーの Resource ARN がバケット形式 | `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式か確認 |
| VPC 内 Lambda からタイムアウト | Internet Origin AP に S3 Gateway EP 経由でアクセス | Lambda を VPC 外に配置、または NAT Gateway 経由に変更 |
| MISCONFIGURED 状態 | ファイルシステム ID が解決不能、またはボリュームが offline / unmount | ID が SVM で名前解決できるか、およびボリュームの junction path を確認 |
| 特定ディレクトリのみ AccessDenied | ONTAP export policy の制限 | SVM の export policy rules を確認（NFS export と S3 AP は別経路だが同じ volume permission） |
| `Policy has invalid action` on put-access-point-policy | AP ポリシーで使えないアクションを含めた（[一覧](#ap-ポリシーで使えないアクション)）。**本文はどのアクションが原因かを名指ししません** | 1 つずつ適用して切り分ける。バケット設定系と AP 管理系は identity-based 側へ移す |
| ポリシー変更が反映されない | 反映に数秒かかる | 適用の 6 秒後には前の判定が返り、10〜12 秒後に安定しました。**適用直後の 1 回だけを見ると違う結論になります** |

### 確認コマンド例

> **注意**: 以下のコマンドはすべて読み取り専用（read-only）のトラブルシューティング用です。環境に変更を加えるものではありません。

```bash
# === AWS CLI ===

# 1. S3 AP resource policy の確認
#    ポリシーが無い場合は NoSuchAccessPointPolicy が返る（それが正常な状態もある）
aws s3control get-access-point-policy \
  --account-id <ACCOUNT_ID> \
  --name <AP_NAME>

# 2. IAM Policy Simulator で権限確認
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<ACCOUNT_ID>:role/<LAMBDA_ROLE> \
  --action-names s3:GetObject s3:ListBucket \
  --resource-arns "arn:aws:s3:<REGION>:<ACCOUNT_ID>:accesspoint/<AP_NAME>/object/*"

# 3. CloudTrail で AccessDenied イベント確認（呼び出し元の特定はこちら）
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetObject \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ) \
  --query 'Events[?contains(CloudTrailEvent, `AccessDenied`)]'

# 4. S3 AP に紐づく filesystem identity 確認
aws fsx describe-s3-access-point-attachments \
  --query 'S3AccessPointAttachments[*].{Name:Name,Identity:OntapConfiguration.FileSystemIdentity}'

# === ONTAP CLI ===

# 5. ONTAP 側: 対象パスの ACL / permission 確認 (UNIX)
# SSH or ONTAP CLI 経由
vserver security file-directory show -vserver <SVM_NAME> -path <PATH>

# 6. ONTAP 側: AP に固定した ID が名前解決できるか確認
vserver services access-check authentication show-creds \
  -vserver <SVM_NAME> -unix-user-name <USER> -show-partial-unix-creds true

# 7. ONTAP 側: ネイティブ S3 サービスの有無（あると AP を作成できない）
#    REST: GET /api/protocols/s3/services?svm.name=<SVM_NAME>
vserver object-store-server show -vserver <SVM_NAME>

# === VPC / Network ===

# 8. VPC Endpoint policy 確認
aws ec2 describe-vpc-endpoints \
  --filters Name=service-name,Values=com.amazonaws.<REGION>.s3 \
  --query 'VpcEndpoints[*].{Id:VpcEndpointId,Policy:PolicyDocument}'
```

## よくある誤解

| 誤解 | 実際 |
|---|---|
| FSx for ONTAP S3 AP にバケットポリシーを設定する | 裏にバケットが無いので設定できません。アクセスポイントポリシーです |
| AP ポリシーの `Allow` に書いた範囲しか通らない | 同一アカウントでは結合で評価されます。絞るには明示的な拒否が必要です |
| `Allow` の `Action` に書いていない操作はできない | できます。`Action` も結合で決まります |
| AP ポリシーを付けないと誰もアクセスできない | 呼び出し元の identity-based ポリシーが許可していればアクセスできます |
| 同一アカウント所有が必須なので別アカウントからは読めない | **読めます。** 制約は AP を作る側です |
| `NotPrincipal` で例外を作れる | アカウント ARN の併記が必須で、ロールはセッション ARN も必要です。セッション名を固定できない用途では使えません |
| `aws:SecureTransport` で平文を止めている | その分岐に到達しません。HTTP は認可評価の前にリダイレクトされます |
| 手元の JSON が 20 KB 以内なら通る | 判定は正規化後です。**実測では 24,861 バイトで拒否されました** |
| あとで AP のファイルシステム ID を差し替えればよい | 変更 API がありません。AP の作り直しになり、**エイリアスが変わります** |
| AP ポリシーに `s3:` のアクションが無ければファイルには触れられない | 触れられます。**2 層は独立です** |
| UNIX ID には LDAP、Windows ID には AD 参加が必要 | どちらも必須ではありません。ローカル UNIX ユーザー、および workgroup モードのローカル Windows ユーザーで実測しました |
| 監査ログを見れば呼び出し元の IAM プリンシパルが分かる | 分かりません。残るのは AP の ID の SID だけです。**CloudTrail との突き合わせが必要です** |
| 監査ログの `SubjectIP` で呼び出し元を追える | 追えません。AWS のサービス側アドレスで、6 リクエストで 5 個の異なる値になりました |
| SVM で監査を有効化すれば全ボリュームで記録される | UNIX スタイルで mode bits だけのボリュームは **0 件**でした。監査 ACE が必要です |
| AD 参加 SVM なら監査ログに主体の名前が出る | 出ません。**実在のドメインアカウントでも `Not Present`** のままです |
| UNIX ボリュームに SLAG を足せば監査できる | アクセスが拒否されます。**unix→win マッピングが必須になります** |
| Layer 1 の評価はボリュームのセキュリティスタイルで変わる | 変わりません。UNIX / NTFS の両方で同じ結果でした |
| ONTAP ネイティブ S3 を使っている SVM にも AP を作れる | 作れません。`FAILED` になります |

## 副産物: ONTAP ネイティブ S3 サーバーによる AP 作成のブロック

**SVM に ONTAP ネイティブの S3 サービスがあると、その SVM のボリュームに S3 AP を作成できません。** AP の `Lifecycle` が `FAILED` になり、理由が明示されます。

```
Amazon FSx is unable to create an S3 access point because of an existing
ONTAP object storage server on SVM svm-0123456789abcdef0
```

ONTAP の S3 バケットは `fg_oss_*` という名前の FlexGroup として現れるので、**AP を作る前に対象 SVM でこのボリュームと `/protocols/s3/services` を確認してください。** 回避するには別の SVM を使います。

## この記述の限界

- **`Deny` に `s3:*` を書いた場合のロックアウトは実測していません。** 復旧に AP の作り直しが必要になる可能性があるため、意図的に試していません。
- **SLAG を外した状態への復帰は NFS で確認しました。** S3 AP 経路での復帰は未測定です（理由は当該節に記載）。
- **クロスアカウントの実測は 1 組のアカウント間で 1 回です。**
- **AD 参加 SVM での監査測定に使ったドメインアカウントは 1 種類**（ディレクトリの管理者アカウント）です。通常のドメインユーザーでは未測定です。
- 監査の測定は `file_operations` イベント・XML 形式の 1 構成です。他のイベント種別やログ形式では記録されるフィールドが異なります。
- 実測は 1 リージョン（`ap-northeast-1`）・ONTAP `9.18.1P3D1`・1 ファイルシステムでの結果です。

## 参考リンク

- [S3 Access Point の権限設計 — 評価順序と、絞り込みを担う 2 つの層](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/domains/security-governance/notes/access-point-authorization-layers.md) — **本ドキュメントの実測の出典。ポリシー設定例 6 パターンと全測定結果**
- [S3 Access Point 経由のリクエストはどう判定されるか](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/decision-trees/access-point-authorization.md) — 評価順序と、症状から落ちた段への逆引き
- [AD 参加 SVM の S3 AP 前提条件](ja/ad-joined-svm-s3ap-prerequisites.md) — AD DC 到達性、`HeadBucket` が偽陽性になる理由
- [クロスアカウント S3 AP](multi-account/cross-account-s3ap.md) — クロスアカウントアクセスの設計パターン
- [Managing access point access — Amazon FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- [Troubleshooting access points — Amazon FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/troubleshooting-access-points-for-fsxn.html)
- [AWS: How AWS enforcement code logic evaluates requests](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic_policy-eval-denyallow.html)
- [AWS: Policy evaluation for requests within a single account](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic_policy-eval-basics.html)
- [Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
