# ファイルポータルの identity と可視範囲 — 実測結果

🌐 **Language / 言語**: 日本語 | [English](../en/portal-identity-verification-results.md)

> ファイルポータルにサインインした利用者が、FSx for ONTAP 上のどのファイルに届くのかを実環境で測った記録です。ポータルの Cognito 認証（Layer 1）と、S3 Access Point に固定した File System Identity が評価される NAS のパーミッション（Layer 2）の関係を、identity だけを変えた対照実験で確定させています。
>
> 組織外のメンバーをポータル利用者として登録する設計を決める前に読む文書です。手順ではなく**測って分かった事実**を置いてあります。

## 測定環境

| 項目 | 値 |
|------|-----|
| 測定日 | 2026-08-26 |
| リージョン | `ap-northeast-1` |
| ONTAP | NetApp Release 9.18.1P3D1 |
| ファイルシステム | FSx for ONTAP、スループット 128 MBps |
| ボリューム | 専用の検証ボリューム 1 本（UNIX セキュリティスタイル、10 GiB）、および既存の NTFS ボリューム |
| S3 Access Point | Internet-origin、**AP ポリシーは付けていない** |
| IAM 呼び出し元 | 全列で同一の 1 プリンシパル |

**対照実験の作り方**: Layer 1 を固定しています。呼び出し元の IAM プリンシパルは全列で同一で、どの Access Point にも AP ポリシーを付けていません。したがって列の間に現れた差は Layer 2、つまり **Access Point に固定した UNIX / Windows ユーザーがボリュームのパーミッションに対して評価された結果**だけです。

検証ボリュームのレイアウト:

| パス | 所有者 | mode | 意図 |
|------|--------|------|------|
| `/` | uid 5002 : gid 5000 | 0755 | ルート |
| `shared/` | uid 5002 : gid 5000 | 0755 | 所有者は書ける。他は読めるだけ |
| `shared/preexisting.txt` | uid 5002 : gid 5000 | 0644 | 事前に NFS 側で作成 |
| `private_other/` | uid 2026 : gid 2026 | 0700 | 無関係な uid の領域 |
| `private_other/other.txt` | uid 2026 : gid 2026 | 0600 | 同上 |

Access Point は 3 本。固定した UNIX ユーザーだけが違います。

| 列 | File System Identity |
|----|---------------------|
| root | `UNIX` / `root`（uid 0） |
| portal_ro | `UNIX` / ローカル UNIX ユーザー uid 5001、gid 5000 |
| portal_rw | `UNIX` / ローカル UNIX ユーザー uid 5002、gid 5000 |

> **`FileSystemIdentity.UnixUser` は `Name` しか受け付けません。** `Uid` フィールドは存在しません（`aws fsx create-and-attach-s3-access-point --generate-cli-skeleton` で確認）。したがって非 root の identity を使うには、**名前付きのローカル UNIX ユーザーが SVM 上に実在する必要があり**、その作成経路は ONTAP REST API か ONTAP CLI だけです。FSx の API では作れません。

---

## 実測 1: Layer 2 はポータルのデータ経路を実際に止める

| 操作 | root (uid 0) | portal_ro (5001) | portal_rw (5002) |
|------|-------------|------------------|------------------|
| `HeadBucket` | ok | **ok** | **ok** |
| `ListObjectsV2` `/`（フォルダ名） | ok | **ok** | **ok** |
| `ListObjectsV2` `shared/` | ok 4 件 | ok 4 件 | ok 4 件 |
| `GetObject` `shared/preexisting.txt` | ok 37 B | ok 37 B | ok 37 B |
| `ListObjectsV2` `private_other/` | ok 1 件 | AccessDenied 403 | AccessDenied 403 |
| `GetObject` `private_other/other.txt` | ok 22 B | AccessDenied 403 | AccessDenied 403 |
| `PutObject` `shared/` | ok | **AccessDenied 403** | ok |
| `PutObject` `private_other/` | ok | AccessDenied 403 | AccessDenied 403 |
| `DeleteObject` `shared/` | ok | **AccessDenied 403** | ok |

**読み取り専用の identity を固定すれば、書き込みは Layer 2 で止まります。** AP ポリシーを 1 バイトも書かずに、読み・書き・削除の可否が identity ごとに分かれました。これは運用上の申し送りではなく、機構による担保です。

**`root`（uid 0）は何も止めません。** 無関係な uid が所有する 0700 のディレクトリも含めて全部通りました。[デプロイ Runbook](./portal-deployment-runbook.md) の既定は `UnixUser: root` なので、**その既定のままではポータルはボリューム全体に届きます**。

**`HeadBucket` は全列で成功しました。** 全データ操作が拒否される列でも成功します。到達確認に `HeadBucket` を使うと、実際には 1 バイトも読めない構成を「正常」と報告します。

**削除の判定はディレクトリの write ビットに依存します。** そのため列ごとに別の削除対象を用意しました。1 つの対象を共有すると、先行列の成功で対象が消え、後続列の結果が `NoSuchKey` になって「拒否された」ように見えます。

**フォルダ名は境界を越えて見えます。** `private_other/` の中身は `portal_ro` と `portal_rw` から読めませんが、**親が 0755 なので名前は 3 列すべてから見えました**。つまりポータル側のパスプレフィックス境界は Layer 2 と冗長ではありません。片方だけでは、他チームのフォルダ名が一覧に出ます。

---

## 実測 2: presigned URL は署名した Access Point の identity で実行される

AWS の資格情報を一切持たない `curl` で取得しました。

| ケース | root AP で署名 | portal_ro AP で署名 |
|--------|---------------|--------------------|
| `GET private_other/other.txt` | **http 200** | http 403 |
| `GET shared/preexisting.txt` | http 200 | http 200 |
| `PUT shared/presigned_w.txt` | **http 200** | http 403 |

**presigned URL は、署名に使った Access Point の identity を運びます。** URL を受け取った側は AWS の資格情報を持っていませんが、root AP で署名された URL は 0700 のディレクトリの中身を読めました。`PUT` も成功し、ボリューム上に uid 0 所有で着地しました。

これがポータルの実装に直接効きます。`functions/presigned-url/index.py` は `S3_AP_ALIAS`（既定の Access Point）だけを読み、`GROUP_AP_MAPPING` を参照しません。**グループが制限的な Access Point にマップされている利用者でも、ダウンロード URL は既定の Access Point の identity で署名されます。** 既定が `UnixUser: root` の構成では、分離が迂回されます。壊れて 404 になるのではなく、通ってしまう側の失敗です。

> 署名者は Lambda の実行ロールではなく IAM ユーザーで代替しました。Layer 2 は Access Point の identity で決まり IAM プリンシパルでは決まらないため、測定対象には影響しません。Layer 1 の差は、Lambda ロールが `accesspoint/*` にスコープされている点だけで、どちらのエイリアスも含まれます。

---

## 実測 3: NFS と併用したときの所有者と mode

S3 Access Point 経由で作ったオブジェクトを、同じボリュームを NFS でマウントしたクライアントから見ました。

| 作った経路 | NFS 側の種別 | 所有者 | mode |
|-----------|------------|--------|------|
| root AP で `PutObject` | ファイル | uid 0 : gid 1 | 0644 |
| portal_rw AP で `PutObject` | ファイル | uid 5002 : gid 5000 | 0644 |
| root AP で署名した presigned `PUT` | ファイル | uid 0 : gid 1 | 0644 |
| root AP で末尾 `/` のゼロバイトキー | **ディレクトリ** | uid 0 : gid 1 | **0777** |
| portal_rw AP で末尾 `/` のゼロバイトキー | **ディレクトリ** | uid 5002 : gid 5000 | **0777** |
| 比較: NFS 側で作成 | ファイル | 作成した uid | 作成時の umask どおり |

**ファイルは Access Point の identity 所有で、mode 0644 になります。** NFS / SMB の利用者には、その identity が作ったファイルとして見えます。誰がポータルにサインインしていたかは NAS 側からは分かりません。

**末尾が `/` のゼロバイトキーは ONTAP の実ディレクトリになり、mode は 0777 でした。** 5 回作って 5 回とも 0777 です（2 つの identity × 2 回 + 1 回）。S3 の疑似フォルダではなく本物のディレクトリで、**そのボリュームの NFS / SMB 利用者全員が書き込みと削除をできます**。ポータルの「フォルダ作成」はこのゼロバイトキーを書くので、**ポータルで作ったフォルダは NAS 側から誰でも書ける状態になります**。

逆方向も測りました。NFS 側で uid 2026 / gid 2026 / mode 0640 で作ったファイルは、root AP からは読めましたが（29 B）、`portal_ro` と `portal_rw` の AP からは AccessDenied 403 でした。**Layer 2 は両方向に効きます。**

---

## 実測 4: WINDOWS タイプの identity

### 4-1. Access Point の作成が SVM の既存 S3 サーバーに阻まれる

AD 参加済みの SVM に WINDOWS タイプの Access Point を 3 本作ろうとして、3 本とも `FAILED` になりました。理由は `LifecycleTransitionReason` に入っています。

```
Amazon FSx is unable to create an S3 access point because of an existing
ONTAP object storage server on SVM <svm-id>. Please delete the existing
s3 server and retry.
```

**ONTAP のネイティブ S3 サーバー（オブジェクトストアサーバー）が構成されている SVM には、FSx の S3 Access Point を作れません。** これは Access Point を設計する前に確認すべき前提条件です。既存の S3 サーバーを消す判断は、その SVM を使っている側にしかできません。

### 4-2. ドメイン接頭辞を付けると壊れる — ただし症状が想定と違う

同一の NTFS ボリューム上に、`WindowsUser.Name` だけが違う Access Point を 2 本作りました。両方とも `AVAILABLE` に到達し、接頭辞付きの値もそのまま格納されました。

| 操作 | `WindowsUser` = `administrator` | `WindowsUser` = `EXAMPLE\administrator` |
|------|-------------------------------|----------------------------------------|
| `HeadBucket` | ok | **503** |
| `ListObjectsV2` | ok 12 件 | ServiceUnavailable 503 |
| `GetObject` | ok 12 B | ServiceUnavailable 503 |
| `PutObject` | ok | ServiceUnavailable 503 |

3 点が確定しました。

1. **ドメイン接頭辞は API 層では受理されます。** Access Point は `AVAILABLE` になり、`describe` にも接頭辞付きの値が残ります。作成が成功したことは、動くことの証拠になりません。
2. **失敗は `503 ServiceUnavailable` で、`AccessDenied` ではありません。** 403 を探していると原因の層を見誤ります。
3. **`HeadBucket` もここでは失敗します。** この故障形態に限っては `HeadBucket` は偽陽性になりません。実測 1 の「`HeadBucket` は常に通る」は Layer 2 のパーミッション拒否に対しての話で、identity の解決そのものが壊れている場合とは別です。

### 4-3. AD DC が検出されていない SVM でもデータ操作は通った

ドメインに参加しているが**ドメインコントローラが 1 台も検出されていない** SVM 上の Access Point（`WindowsUser` = `administrator`、NTFS ボリューム）で、`HeadBucket` / `ListObjectsV2` / `GetObject` / `PutObject` / `DeleteObject` がすべて成功しました。ドメイン参加していない workgroup モードの SVM 上の Access Point でも同じ結果でした。

DC が 0 件であることは ONTAP の CLI 経由で確認しています（後述）。

後から**この SVM には `administrator` と同名のローカル SMB ユーザーが実在する**ことを確認しました（`/api/protocols/cifs/local-users` の `name` は `<CIFS サーバー名>\Administrator` 形式）。そして 4-4 で、**新規に作ったローカル SMB ユーザーを固定した Access Point が DC 不在のまま正常に動く**ことを測っています。

したがって「ローカルに解決される identity は DC を必要としない」という読みが立ちます。**ただしドメインアカウントを固定した場合の DC 要否は依然として未確定です。** この環境のドメインには到達可能な DC が無いため、「ドメイン名だから失敗した」と「DC が無いから失敗した」を分離できません。

### 4-4. NTFS ACL は identity 単位で判別する

UNIX の mode bits と対称な対照実験です。専用の NTFS ボリューム 1 本、IAM 呼び出し元は同一、AP ポリシーは無し。ボリュームルートから `Everyone / full_control` が継承されている状態のまま、**明示的な deny ACE だけで差を作りました**。

| パス | 明示 ACE |
|------|---------|
| `shared/` | 読み取り専用にする identity に対して書き込み系権限を deny |
| `private_other/` | 非特権の 2 つの identity に対して `full_control` を deny |

固定した identity だけが違う Access Point 4 本の結果です。4 列目は、ローカルユーザー名に **CIFS サーバー名の接頭辞**を付けた形です。

| 操作 | administrator | portalro | portalrw | `<CIFS サーバー>\portalro` |
|------|--------------|----------|----------|--------------------------|
| `HeadBucket` | ok | ok | ok | ok |
| `ListObjectsV2` `/` | ok | ok | ok | ok |
| `ListObjectsV2` `shared/` | ok 6 件 | ok 6 件 | ok 6 件 | ok 6 件 |
| `GetObject` `shared/preexisting.txt` | ok 37 B | ok 37 B | ok 37 B | ok 37 B |
| `ListObjectsV2` `private_other/` | ok 2 件 | AccessDenied 403 | AccessDenied 403 | AccessDenied 403 |
| `GetObject` `private_other/other.txt` | ok 42 B | AccessDenied 403 | AccessDenied 403 | AccessDenied 403 |
| `PutObject` `shared/` | ok | **AccessDenied 403** | ok | **AccessDenied 403** |
| `PutObject` `private_other/` | ok | AccessDenied 403 | AccessDenied 403 | AccessDenied 403 |
| `DeleteObject` `shared/` | ok | **AccessDenied 403** | ok | **AccessDenied 403** |

**NTFS ACL は UNIX の mode bits と同じ強度で識別します。** 読み取り専用にした identity は書き込みと削除が `AccessDenied 403` で止まり、deny を置いたディレクトリは一覧も取得もできません。**組織外ユーザー向けに読み取り専用の identity を固定する設計は、NTFS ボリュームでも機構による担保になります。**

**CIFS サーバー名の接頭辞を付けた形は、付けない形と完全に同じ挙動でした。** これが 4-2 の見方を変えます。**壊れるのは「バックスラッシュを含む形」ではありません。** ローカルアカウントの名前空間を指す接頭辞は動き、ドメインを指す接頭辞は 503 になりました。区別は接頭辞の有無ではなく**どの名前空間に解決させるか**です。

書き込まれたオブジェクトの所有者も確認しました。

| 書き込んだ経路 | 所有者 |
|--------------|--------|
| 非特権のローカル SMB ユーザーを固定した AP | そのユーザー |
| 特権アカウントを固定した AP | `BUILTIN\Administrators`（Windows の通常の正規化） |

親ディレクトリの ACE はファイルへ継承されました。**UNIX 側と同じく、NAS からは「AP に固定した identity が作ったファイル」に見え、どの利用者がポータルにサインインしていたかは分かりません。**

> **NTFS 側にも 0777 相当があります。** 新規ボリュームのルートは `Everyone / full_control` を持ち、Access Point 経由で作ったディレクトリはそれを継承しました。UNIX 側でディレクトリが 0777 になるのと同じ帰結で、**既定のままでは NAS 側の全員が書けます**。

---

## 副産物として確定したこと

### ONTAP は誤ったパスワードでもロックアウト中でも「User is not authorized」を返す

意図的に誤ったパスワードを 1 回だけ送る対照を置いて確認しました。

| 送ったもの | 応答 |
|-----------|------|
| 誤ったパスワード | HTTP 401、`code 6691623`、`"User is not authorized."` |
| 保管されている正しい資格情報（アカウントがロック中） | HTTP 401、`code 6691623`、`"User is not authorized."` |

**本文が同一なので、このメッセージから原因を読み取ってはいけません。** パスワード誤り・ユーザー不在・アカウントのロックアウトがすべて同じ文字列になります。層の切り分けには使えません。

このメッセージの曖昧さで実際に誤診しました。後述のロックアウト中に呼んだエンドポイントを「`fsxadmin` には認可されていないエンドポイント」として記録しかけましたが、**ロックアウトを解除したあと同じエンドポイントを同じ資格情報で呼ぶと、すべて `http=200` で応答しました**。

| エンドポイント | ロック中 | 解除後 |
|--------------|---------|--------|
| `/api/protocols/cifs/local-users` | 401 / 6691623 | 200 |
| `/api/private/cli/vserver/cifs/users-and-groups/local-user` | 401 / 6691623 | 200 |
| `/api/private/cli/vserver/cifs/users-and-groups/local-group` | 401 / 6691623 | 200 |
| `/api/protocols/file-security/permissions/{svm}/{path}` | 401 / 6691623 | 200 |
| `/api/storage/volumes` | 401 / 6691623 | 200 |

**エンドポイント単位の権限制限は存在しませんでした。** ポータルの `getFilePermissions` が依存する `file-security/permissions` も `fsxadmin` から呼べます。

**教訓として残す価値があるのはこの誤診の形です。** 直前まで別のエンドポイントが成功していたため、新しく現れた失敗を「そのエンドポイントの性質」として読みました。実際にはアカウント側の状態変化でした。**成功するはずのエンドポイントを同一セッションに control として置いていれば、1 回で切り分けられました。**

### `discovered_servers` は空のときフィールドごと省略される

AD DC 到達性の判定に使われるフィールドの挙動を、フィールド名検証を対照にして確定させました。

| 要求した `fields=` | 応答 |
|------------------|------|
| 存在しないフィールド名 | `code 262197`「`fields` の値として不正」 |
| `discovered_servers` | **エラーにならない**が、応答にフィールドが無い |
| `discovered_servers`（一覧 GET） | 6 レコード全部にフィールドが無い |

エラーにならないのでフィールド名は有効です。したがって **ONTAP 9.18.1P3D1 は `discovered_servers` を空のときに省略し、`[]` を返しません**。実際の DC 数が 0 件であることは `/api/private/cli/vserver/cifs/domain/discovered-servers` が `num_records: 0` を返すことで別途確認しました。

この結果、`shared/ad_health_check.py` の「空リスト = DC 到達不能」の分岐には到達しません。DC が 0 件の SVM でも `discovered is None` の枝に落ち、`dc_reachable=None` → `is_healthy=True` として楽観的に続行します。**検出するために作られた障害を検出できていません。**

---

## 既存ドキュメントとコードの修正が必要な点

| 対象 | 現状の記述 / 実装 | 実測 |
|------|-----------------|------|
| `docs/agent/pitfalls-ad-smb.md` | `WindowsUser.Name` はユーザー名のみ。`DOMAIN\user` の形にすると data-plane が `AccessDenied` | 症状は `503 ServiceUnavailable` で `HeadBucket` も失敗する。かつ**バックスラッシュ自体が禁止ではない** — CIFS サーバー名を接頭辞にした形は正常に動く。区別は解決させる名前空間 |
| `docs/agent/pitfalls-ad-smb.md` | AD 参加 SVM は全データ操作で DC 到達性が必要、`HeadBucket` は偽陽性 | ローカルに解決される identity は DC 0 件でも全操作が成功する。この前提はドメインアカウントを固定した場合に限定して書くべき |
| `shared/ad_health_check.py` | `discovered_servers == []` を DC 到達不能と判定 | 空のときフィールドが省略されるため、この分岐は到達しない |
| ONTAP 接続の診断手順 | `6691623` の扱いが定まっていない | パスワード誤り・ユーザー不在・ロックアウトで同一文字列。ロックは `lockout-duration = 0` で自然回復しない |
| `functions/presigned-url/index.py` | `S3_AP_ALIAS` 固定、プレフィックス検査なし | 既定 AP の identity で署名され、分離を迂回できる |
| `functions/list-files/index.py` の一覧 | ルート一覧で `CommonPrefixes` を境界で絞っていない | Layer 2 でもフォルダ名は見えるので、両方に穴がある |
| `docs/ja/portal-deployment-runbook.md` | 既定が `UnixUser: root` | root は NAS のパーミッションを一切受けない |
| ポータルの認可モデル文書 | ポータル利用者と ONTAP identity の関係の記述が無い | Access Point 単位で identity が決まる。利用者単位ではない |

---

## 未確認事項

**測っていないことを測ったことにしないための一覧です。**

- **ドメインアカウントを identity にした場合の DC 到達性の要否。** ローカル解決の identity が DC 不在で動くことは 4-4 で確定しましたが、この環境のドメインには到達可能な DC が無いため、「ドメイン名だから失敗した」と「DC が無いから失敗した」を分離できていません。**到達可能な DC がある環境での再測定が必要です。**
- **`0777` / `Everyone` の既定を変える手段の有無。** UNIX 側の 0777、NTFS 側の `Everyone / full_control` はいずれも再現を確定しましたが、Access Point 側やボリューム側の設定で変えられるかは調べていません。
- **ONTAP の失敗ログインカウンタが成功でリセットされるか。** ロックアウトの閾値と回復不能性は確定しましたが、5 回に到達した経路の特定には至っていません。
- **他の ONTAP リリースでの挙動。** すべて 9.18.1P3D1 の単一クラスタでの測定です。

## 測定中に起きたこと — `fsxadmin` がロックアウトした

測定の途中で、それまで成功していた ONTAP REST が 401 を返すようになりました。切り分けと復旧の記録です。

| 確認したこと | 結果 |
|------------|------|
| 保管されている資格情報の更新日 | 測定日より 1 週間前。測定中に変わっていない |
| リクエストが Basic 認証を運んでいるか | 運んでいる。`WWW-Authenticate: Basic realm="ONTAP"` を受信 |
| クラスタ管理 LIF / SVM 管理 LIF | 両方 401 |
| 20 分後の再試行 | 401 のまま |
| 復旧手段 | `aws fsx update-file-system` で `FsxAdminPassword` をリセット → 即座に 200 に戻った |

復旧後にアカウント設定を読んで、**自然回復しない理由が確定しました。**

| `security login role config`（role = `fsxadmin`） | 値 |
|---|---|
| `max-failed-login-attempts` | **5** |
| `lockout-duration` | **0** |
| `delay-after-failed-login` | 4 |
| `passwd-expiry-warn-time` | `unlimited` |
| `passwd-minlength` | 8 |
| `disallowed-reuse` | 6 |

**`lockout-duration = 0` なので、5 回の失敗で到達したロックは待っても解けません。** 管理者の介入（パスワードのリセット、またはアカウントのロック解除）が必要です。`passwd-expiry-warn-time` が `unlimited` であることから、パスワードの期限切れは原因ではありません。

**この環境で確定したのは閾値と回復不能性で、5 回に到達した経路そのものは特定できていません。** 測定中にこのクラスタへ意図的に誤った資格情報を送ったのは 1 回だけで、その後も成功が続いていました。したがってカウンタには測定前からの失敗が積まれていた可能性があります（ONTAP の失敗カウンタが成功でリセットされるかどうかは確認していません）。

**運用上の教訓は閾値の低さと回復不能性の組み合わせです。** 資格情報の切り分けのために誤った値を送る診断は、**5 回という予算を共有リソースから借りて行う操作**であり、`lockout-duration = 0` の環境では借りたら返ってきません。診断の対照実験は必要ですが、その対象は使い捨てのアカウントであるべきです。

FSx の API はこのロックアウトの影響を受けないため、ボリュームと Access Point の作成・削除は継続できました。ONTAP REST を必要とする作業（ローカル UNIX ユーザーの操作など）だけが止まります。

---

## 再現手順

1. UNIX セキュリティスタイルのボリュームを 1 本作る。
2. ONTAP REST で、ローカル UNIX グループ 1 つとローカル UNIX ユーザー 2 つを作る。`FileSystemIdentity` は名前しか受け付けないので、この手順は省略できない。
3. NFS でマウントし、上の「検証ボリュームのレイアウト」どおりに所有者と mode を設定する。
   - **読み取り専用にしたい identity の primary group を、書き込み可のディレクトリの group に一致させないこと。** 一致させると group の write ビットで書けてしまい、「読み取り専用」を測っていないことになる。
4. identity だけが違う Access Point を 3 本作る。AP ポリシーは付けない。
5. 読み取り操作を全列について実行してから、書き込み操作を全列について実行する。
   - **交互に実行しないこと。** 先行列の `PutObject` の成功が後続列のオブジェクト数に混入し、identity の差に見える。
6. 削除の対象は列ごとに別に用意する。
7. presigned URL は、制限的な AP と permissive な AP の両方で同じキーに対して発行し、AWS の資格情報を持たないクライアントで取得する。

NTFS 側を測る場合は 1〜3 を次に差し替えます。

1. NTFS セキュリティスタイルのボリュームを 1 本作り、ローカル SMB ユーザーを 2 つ作る（`<CIFS サーバー名>\<ユーザー名>` 形式）。
2. 特権アカウントを固定した Access Point を先に 1 本作り、**その AP 経由でディレクトリとファイルを作る**。新規ボリュームには共有が無く、Windows クライアントから書き込めないため。
3. `file-security/permissions` の ACL エンドポイントに **明示的な deny ACE** を追加して差を作る。ルートから継承される `Everyone / full_control` を外そうとすると、継承の切断に別の権限が要る。
   - ACE の適用は非同期でジョブが返る。**応答を成功の証拠にせず、読み直して ACE が載ったことを確認する。**

## 関連ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [ポータル認可モデル](./portal-authorization-model.md) | Cognito グループによる機能単位の認可 |
| [マルチテナント設計](./multi-tenant-design.md) | グループごとに Access Point を分ける構成 |
| [デプロイ Runbook](./portal-deployment-runbook.md) | Access Point 作成と設定の手順 |
| [S3 Access Point 認可モデル](../s3ap-authorization-model.md) | 二層認可の詳細 |
| [設計上の考慮点](../design-considerations.md) | Layer 1 / Layer 2 の分離と `FileSystemIdentity` の不変性 |
