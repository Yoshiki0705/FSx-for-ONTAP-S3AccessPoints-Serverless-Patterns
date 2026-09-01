# Getting Started — FSx for ONTAP File Portal

🌐 **Language / 言語**: 日本語 | [English](GETTING-STARTED.en.md)

> 30 分で動作確認可能。DemoMode なら FSx for ONTAP なしで始められます。

## 前提条件

| 項目 | 必須 | バージョン | 確認コマンド |
|------|:---:|---------|----------|
| AWS アカウント | ✅ | — | Free Tier で可。IAM ユーザーまたは SSO で認証済み |
| Node.js | ✅ | 20.x 以上 | `node --version` |
| npm | ✅ | 10.x 以上 | `npm --version` |
| AWS CLI | ✅ | 2.x | `aws --version` |
| Amplify CLI | ✅ | 最新版 | `npx ampx --version` |
| FSx for ONTAP | — | ONTAP 9.15+ | DemoMode なら不要。admin 機能に必要 |
| Docker | — | 24.x 以上 | `docker --version`（Nextcloud 利用時のみ） |

> **検証環境**: 本ガイドは Node.js 20.18.x / Amplify Gen2 1.x / Python 3.12 (Lambda) / ONTAP 9.18.1P3D1 / ap-northeast-1 で検証しています。

## クイックスタート（DemoMode — FSx for ONTAP なし）

```bash
# 1. リポジトリをクローン
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/solutions/amplify-portal

# 2. 依存関係インストール
npm install

# 3. 設定ファイル作成（DemoMode: VPC/ONTAP は空のまま）
cp amplify/portal-config.example.ts amplify/portal-config.ts

# 4. 起動（sandbox + dev server が同時に起動）
npm start
```

ブラウザで `http://localhost:5173` を開き、Cognito でユーザー登録 → サインイン。
ファイルブラウズ・AI 処理・アップロードは DemoMode で動作します。
admin/data-protection 機能は「ONTAP 接続が必要」と表示されます。

> **エンドユーザー向け**: デプロイ完了後、ポータルを使い始めるユーザーには
> [ユーザーガイド](../../../docs/ja/portal-user-guide.md)（[EN](../../../docs/en/portal-user-guide.md)）または
> スマホ利用者向けの [スマートフォン操作ガイド](../../../docs/ja/portal-mobile-guide.md)（[EN](../../../docs/en/portal-mobile-guide.md)）を案内してください。
> どちらもデプロイ手順の知識は不要で、日常操作だけをカバーしています。
> **この文書自体は渡さないでください。** 渡すもの一式と問い合わせ対応は
> [引き渡しと問い合わせ対応ガイド](portal-handover-guide.md) にあります。

### スマートフォン実機での確認

**`npm run dev -- --host` で LAN の IP を開く方法では、サインインできない。** ポータルは
Amplify の SRP 認証で `crypto.subtle` を、共有リンクとアップロードリンクのコピーで
`navigator.clipboard` を使う。どちらもブラウザが **secure context** に限定している API で、
`http://localhost` は例外扱いだが `http://192.168.x.x` は該当しない。

HTTPS で配信する方法を選ぶ。

| 方法 | コマンド | 向き |
|------|---------|------|
| Amplify Hosting にデプロイ | ブランチを接続（[Hosting ガイド](../../../docs/ja/amplify-hosting-production-guide.md)） | 本番に近い形で確認したいとき |
| ローカルをトンネル経由で公開 | `npm run phone` | 手元の変更をすぐ実機で見たいとき。URL は一時的 |

> Cognito はホスト名を固定していないため、どちらでもサインインできる（トンネル経由で実際に確認済み）。
> トンネルの URL は実行ごとに変わるので、共有せず自分の端末からの確認にとどめる。

#### 一度だけの準備

| 用意するもの | コマンド | なぜ必要か |
|---|---|---|
| `cloudflared` | `brew install cloudflared`（macOS）／[その他 OS](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) | HTTPS のトンネルを張る。アカウント登録は不要 |
| `amplify_outputs.json` | `npx ampx sandbox` を一度実行 | `src/main.tsx` が静的 import しているので、無いと開発サーバがそもそも起動しない。sandbox が生成し、gitignore されている（環境ごとに 1 つ） |
| `amplify/portal-config.ts` | 自動（無ければ example から複製される） | DemoMode なら値は空のままでよい |

`amplify_outputs.json` が要る点が、クローン直後に手順どおり進めても実機で真っ白になる主因である。

#### 毎回のコマンド

```bash
cd solutions/amplify-portal
npm run phone
```

開発サーバとトンネルの起動、**トンネルが実際にアプリへ到達しているかの検証**までを 1 コマンドで行う。
実際の出力:

```text
▶ Preflight
  ✔ node v26.4.0
  ✔ node_modules
  ✔ amplify/portal-config.ts
  ✔ amplify_outputs.json
  ✔ cloudflared 2026.7.3

▶ Dev server
  … starting vite on port 5173
  ✔ serving on http://localhost:5173 (pid 43373)

▶ Tunnel
  … waiting for cloudflared to publish a hostname
  ✔ https://threaded-opening-actress-courses.trycloudflare.com

▶ Verify the tunnel reaches the app
  … waiting for DNS to publish threaded-opening-actress-courses.trycloudflare.com . ✔
  … fetching
  ✔ HTTP 200 and the page is the portal

════════════════════════════════════════════════════════
  Open on the phone:

    https://threaded-opening-actress-courses.trycloudflare.com

════════════════════════════════════════════════════════
```

最後に出た URL を実機のブラウザで開く。`Ctrl+C` で開発サーバとトンネルの両方が止まる
（**すでに別のターミナルで動かしていた開発サーバは止めない**）。

主なオプション:

```bash
npm run phone -- --port 4173                       # 別のポートで配信する
npm run phone -- --url https://xxx.ngrok-free.app  # 自分で張ったトンネルを検証だけする
npm run phone -- --help
```

`brew install qrencode` を入れておくと、URL の QR コードを端末で読める形で出力する。

#### スクリプトが検証していること

「起動したのに実機で見えない」の原因はどれも同じ見え方をするので、切り分けを自動化してある。

| 検出する状態 | 出るメッセージ | 対処 |
|---|---|---|
| `amplify_outputs.json` が無い | `amplify_outputs.json is missing` | `npx ampx sandbox` を一度実行する |
| Vite がトンネルのホスト名を拒否 | `Vite refused the tunnel hostname` + 該当ホスト名 | `vite.config.ts` の `server.allowedHosts` に追加（下記） |
| トンネルは生きているが配信元に届かない | `could not reach http://localhost:5173 (HTTP 502)` | 開発サーバが落ちているか、別のポートで動いている |
| この PC だけ名前解決できない | `this machine cannot resolve …, but public DNS can` | トンネル自体は正常。実機は別のリゾルバなので開ける。PC を直すなら DNS キャッシュを消す |

最後の 1 件は再現しにくいが実際に踏む。cloudflared はホスト名を**まだ引けない時点で**表示するため
（cloudflared 自身も "it may take some time to be reachable" と出す）、そこで手元から引くと
**NXDOMAIN が家庭用ルータのリゾルバにキャッシュされ**、公開 DNS には載っているのに作成した
PC からだけ数分間開けなくなる。スクリプトは先に公開リゾルバ（1.1.1.1）へ問い合わせ、
レコードが載ってから初めてローカルの名前解決を行うことでこれを避けている。

#### Vite のホスト名拒否について

**Vite はトンネルのホスト名を既定で拒否する。** リクエストの `Host` ヘッダに見知らぬ名前が
来ると Vite は

```
Blocked request. This host ("...trycloudflare.com") is not allowed.
```

を返す。DNS リバインディングで開発サーバのソースを読まれるのを防ぐための挙動である。
`vite.config.ts` の `server.allowedHosts` に上記トンネルのドメインを登録済みなので、
**cloudflared / ngrok / localtunnel はそのまま通る**。それ以外のトンネルを使う場合は同じ配列に
追加する。`true`（全ホスト許可）にはしていない。トンネルを使っていないときも保護がなくなるため。

#### スクリプトを使わない場合

`npm run phone` は次の 2 つをまとめたものなので、個別に動かしても同じ状態にはなる。
ただし上表の検証は自分で行うことになる。

```bash
# ターミナル 1: 開発サーバ（sandbox も同時に起動）
npm start

# ターミナル 2: トンネル。出力された https://… を実機のブラウザで開く
cloudflared tunnel --url http://localhost:5173
```

確認する内容は[ユーザーガイドの「4. スマートフォンで使う」](../../../docs/ja/portal-user-guide.md)、
レイアウトの仕様は[セクション構成ガイドの「モバイル対応」](./portal-tabs-guide.md)にある。

## フルセットアップ（FSx for ONTAP 接続あり）

### Step 1: 前提条件の確認

```bash
# FSx for ONTAP のファイルシステム ID を指定して自動検出
./scripts/setup-prerequisites.sh --fs-id fs-0123456789abcdef0
```

出力される値をメモしてください（VPC ID, サブネット, SG, 管理 IP, SVM 名）。

### Step 2: VPC Endpoint の確認（必須）

VPC 内の Lambda が AWS サービスにアクセスするには、以下の VPC Endpoint が必要です:

| Endpoint | タイプ | 用途 |
|----------|--------|------|
| `com.amazonaws.<region>.s3` | Gateway | S3 API (Object Lock, ファイル操作) |
| `com.amazonaws.<region>.secretsmanager` | Interface | ONTAP クレデンシャル取得 |

```bash
# S3 Gateway Endpoint の確認（通常はデフォルト VPC に存在）
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<vpc-id>" "Name=service-name,Values=com.amazonaws.<region>.s3" \
  --query "VpcEndpoints[0].{Id:VpcEndpointId,RouteTables:RouteTableIds}"

# Lambda サブネットのルートテーブルが含まれているか確認
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<subnet-id>" \
  --query "RouteTables[0].RouteTableId"

# 含まれていない場合は追加
aws ec2 modify-vpc-endpoint --vpc-endpoint-id <vpce-id> --add-route-table-ids <rtb-id>

# Secrets Manager Interface Endpoint がない場合は作成
aws ec2 create-vpc-endpoint \
  --vpc-id <vpc-id> \
  --service-name com.amazonaws.<region>.secretsmanager \
  --vpc-endpoint-type Interface \
  --subnet-ids <subnet-id> \
  --security-group-ids <sg-id>
```

> **Security note**: S3 Gateway Endpoint のルートテーブルに Lambda のサブネットが含まれていないと、S3 API 呼び出し（Object Lock 確認等）がタイムアウトします。

### Step 3: Secrets Manager にクレデンシャルを登録

```bash
aws secretsmanager create-secret \
  --name fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"YOUR_PASSWORD_HERE"}'
```

> fsxadmin のパスワードは FSx for ONTAP 作成時に設定したもの。
> 変更: `aws fsx update-file-system --file-system-id <id> --ontap-configuration '{"FsxAdminPassword":"NewPassword"}'`

### Step 4: portal-config.ts を編集

```bash
cp amplify/portal-config.example.ts amplify/portal-config.ts
```

Step 1 で取得した値を入力:

```typescript
export const config: PortalConfig = {
  region: "ap-northeast-1",  // FSx for ONTAP のリージョン
  s3ApAlias: "your-s3ap-alias-xxx-s3alias",  // FSx Console > S3 Access Points タブ

  // VPC (admin/data-protection 機能に必須)
  vpcId: "vpc-0123456789abcdef0",
  vpcSubnetIds: ["subnet-0123456789abcdef0"],
  vpcSecurityGroupIds: ["sg-0123456789abcdef0"],
  // vpcId を設定する場合は必須。vpcSubnetIds に紐づくルートテーブルを指定します。
  // 未設定のまま vpcId を設定すると synth が失敗します（理由は後述）。
  vpcRouteTableIds: ["rtb-0123456789abcdef0"],
  allowNoBlockExpiry: false,

  // ONTAP 接続
  ontapMgmtIp: "172.30.x.x",  // management LIF IP
  ontapSecretName: "fsx-ontap-fsxadmin-credentials",
  ontapSvmName: "svm1",
  ontapVolumeName: "vol1",

  // ... 他はデフォルトのまま
};
```

#### `vpcRouteTableIds` について

DynamoDB ゲートウェイエンドポイントを作成するための設定です。VPC 内の Lambda が封じ込めブロックの台帳（DynamoDB）に到達するために必要です。

Lambda の ENI にはパブリック IP が付かないため、デフォルトルートが Internet Gateway 向きのサブネットでは外向き通信ができません。Secrets Manager はインターフェイスエンドポイントで到達できますが、DynamoDB には経路がありません。ゲートウェイエンドポイントは時間課金・データ処理課金がありません。

**未設定のまま `vpcId` を設定した場合、synth が失敗します。** ドキュメントに書くだけでは不十分だからです。エンドポイントがないと、デプロイは成功したように見える一方で**ブロックの有効期限処理がまったく動きません**。ブロックはクラスターに適用されるものの台帳への書き込みが失敗し、定期スイープはそのブロックを見つけられません。レスポンスは `expiryTracked: false` を返すので無言では壊れませんが、気づくのは個々の操作のレスポンスを読んだ人だけで、「ブロックは自動で解除される」と思っている運用者には届きません。

有効期限なしで運用すると決めている場合は `allowNoBlockExpiry: true` を設定してください。

サブネットに関連付けられているルートテーブルを確認する:

```bash
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<subnet-id>" \
  --query "RouteTables[].RouteTableId" --output text
```

明示的な関連付けがないサブネットは、VPC のメインルートテーブルを使います:

```bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=<vpc-id>" "Name=association.main,Values=true" \
  --query "RouteTables[].RouteTableId" --output text
```

### Step 5: 起動

```bash
npm start
```

初回は CloudFormation スタックを作成するため 3〜5 分かかります。`Deployment completed` と
`http://localhost:5173` が表示されたら完了です。

### Step 6: アカウントを作り、ロールを付与する

既定で閉じているものが 2 つあり、どちらもポータルを使う前に必要です。いずれも
「誰に何を許すか」の判断なので、インフラのコードが代わりに決めるべきものではありません。

**自己サインアップは無効**（`signIn.selfSignUpEnabled: false`）。サインイン画面は公開されて
いるため、登録を開けておくと到達できる人は誰でもアカウントを作れます。自分の分を作ります:

```bash
POOL=$(python3 -c "import json;print(json.load(open('amplify_outputs.json'))['auth']['user_pool_id'])")
aws cognito-idp admin-create-user \
  --user-pool-id "$POOL" --username <your-email> \
  --user-attributes Name=email,Value=<your-email> Name=email_verified,Value=true
```

**ロールは強制されます**（`enforceRoles: true`）。ロールを持たない利用者は閲覧・プレビュー・
ダウンロード・検索はできて、アップロードと削除ができません。自分に付与します:

```bash
make portal-grant-roles ARGS='--apply --assign <your-email>=storage-admin,internal'
```

ロール（`storage-admin`）と scope（`internal`）を同時に付与しています。スクリプトは
**scope を指定しない付与を拒否します**——scope の不在は「internal」を意味するので、
省略によってそこに到達すべきではないからです。`--apply` を付けずに実行すると dry run です。

付与後は**サインアウトとサインイン**が必要です。グループは ID トークンに載るので、付与前に
開いたセッションには反映されません。「付与したのに変わらない」という報告のほとんどがこれです。

> ロールが無いと、サイドバーに「リソース管理」「分析」が出ず、アップロードも失敗します。
> 非表示は意図したものです（認可エラーしか返さないメニューは、無いメニューより悪い）。
> **画面から分かりにくいのは書き込みが同じ理由で拒否されること**で、だからこの Step は
> 動作確認より前にあります。
>
> ロールを誰にも付与しないデモ用途では `enforceRoles: false` にします。その場合は
> サインイン済みの利用者全員が書き込みと削除をできます。

### Step 7: 動作確認

**まずコマンドラインから確認してください。** ONTAP のパネルにデータが出るまでに 6 段の前提が揃う必要があり、どれが欠けているかは画面から判別できません（理由は下記）。

```bash
# リポジトリルートから
make ontap-preflight FS_ID=<fs-id> LAMBDA=<ResourceMgmtFunction の名前>
```

すべての段を通過したら UI を開きます。

1. **ファイルブラウズ**: Browse > All Files にフォルダが表示される
2. **SMB 共有**: Admin > Resources > SMB 共有 に共有一覧が表示される
3. **Lock パネル**: Data Protection > Lock でタブが表示される
4. **ARP/AI**: Data Protection > ARP/AI でボリュームの保護状態が表示される

`LAMBDA=` を省くと、6 段目——ONTAP が資格情報を受け付けるか——は合格ではなく **SKIP** になります。管理 LIF はプライベートなので手元のマシンからは到達できず、デプロイ済みの関数に呼ばせる必要があります。関数名の取得:

```bash
aws lambda list-functions \
  --query "Functions[?contains(FunctionName, 'ResourceMgmtFunction')].FunctionName" \
  --output text
```

> **画面から逆算しないほうがよい理由**: 6 段目だけが失敗している状態——Secrets Manager のパスワードと ONTAP 側のパスワードが食い違っていた——で、ポータルは「ONTAP 接続が必要です」と VPC とセキュリティグループについての案内を表示しました。ボリュームは存在し、リクエストはクラスターに届いていました。現在はパネルが原因を 5 分類しますが、**デプロイ直後は UI を開くより preflight を走らせるほうが速いです**。詳細は [ONTAP 接続ガイド](ONTAP-CONNECTION-GUIDE.md#最初に実行する-make-ontap-preflight)。
## 手作業のままにしている設定と、その理由

再現性のため、原則としてすべて IaC 側に置いています。以下は**意図的に外に出している**ものです。

| 設定 | 置き場所 | 手作業のままにする理由 |
|------|---------|--------------------|
| `storage-admin` への所属 | `admin-add-user-to-group` | 誰に管理権限を渡すかは環境ごとの判断。グループの作成自体は IaC 済み |
| ONTAP の認証情報 | Secrets Manager（Step 3） | パスワードをリポジトリにも CloudFormation テンプレートにも入れないため |
| S3 Object Lock 用バケット | 別途作成（`s3ObjectLockBucket`） | ポータルのスタックに含めると、Object Lock で保護されたオブジェクトが残っている間スタックを削除できなくなる。ライフサイクルを分離しておく |
| VPC Endpoint のルートテーブル関連付け | `modify-vpc-endpoint`（Step 2） | Endpoint は他のスタックと共有されることがあり、ポータル側から関連付けを変更すると影響範囲が読めない |

> `storage-admin` の**グループ作成**は以前ここに無く、IaC にもありませんでした。長く動かしている環境には手作業で作られたものが残っているため動き、新規デプロイでは管理セクションが消える、という差が出ていました。現在は `defineAuth` が作成し、`make drift` が「認可が参照するグループを `defineAuth` が宣言しているか」を検査します。

## このポータルの前提と位置づけ

**対象**: NAS 上に非構造化データを持ち、そのデータの保護・活用を進めたい方。

| あなたの環境 | このポータルの使い方 |
|-----------|-------------------|
| オンプレ NAS からの移行を検討中 | FSx for ONTAP + S3 AP で、ブラウザアクセス・AI 処理・データ保護を実現 |
| 既に FSx for ONTAP を利用中 | S3 AP を有効化し、既存データに本ポータルの全機能を追加 |
| NAS + Box/SharePoint/Google Drive 併用 | SaaS はそのまま。NAS データへの AI 処理・監査・保護を追加 |
| Nextcloud を運用中 | External Storage で S3 AP を追加接続（セットアップガイドあり） |

NAS のみの環境では単独利用、SaaS 併用環境では追加レイヤーとして、それぞれの状況に合わせて使えます。

**業界別の利用例**:
- **金融**: トレーディングログの異常検知 + FISC 7年監査証跡
- **製造**: CAD/EDA ファイルの AI 品質検査
- **医療**: DICOM 画像の AI 診断支援 + HIPAA 保持管理
- **メディア**: 映像素材の AI メタデータ自動タグ付け
- **法務**: 契約書 PDF の AI 分類 + 期限管理可視化
- **研究**: ゲノム/シミュレーション結果のブラウザ検索

### NFS/SMB ファイルサーバーへの Web 体験の追加

NFS/SMB ファイルサーバーの高スループット・低レイテンシ・マルチプロトコル対応はそのまま活かしつつ、以下のような Web 体験を**データ移動なし**で追加します:

| 追加される体験 | 本ポータルでの実現 |
|---|---|
| ブラウザからのアクセス（VPN 不要） | S3 AP + Cognito 認証（Internet-origin） |
| 自然言語ファイル検索 | Bedrock Knowledge Base セマンティック検索 |
| 共有リンク（期限付き） | Presigned URL + QR コード |
| バージョン管理・ワンクリック復元 | Snapshot UI + FlexClone |
| 監査証跡を UI で確認 | CloudTrail + Athena セルフサービス |
| AI 自動分類・タグ付け | Bedrock + Step Functions ワンクリック |
| ランサムウェア対策の可視化 | ARP/AI ダッシュボード |

既存の NFS/SMB ワークフローには影響しません。S3 AP は同じボリュームへの追加アクセスパスです。

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `ONTAP connection not configured` | VPC/ONTAP 設定が空 | portal-config.ts に VPC + ONTAP 値を設定 |
| `Execution timed out` (admin 操作) | Secrets Manager VPC Endpoint がない | VPC に `com.amazonaws.<region>.secretsmanager` Interface Endpoint を追加 |
| `Unknown action: xxx` | Lambda コードが古い | sandbox を Ctrl+C → `npm start` で再起動 |
| S3 Object Lock 「未設定」 | S3 Gateway Endpoint のルートテーブルに Lambda サブネットが含まれていない | `aws ec2 modify-vpc-endpoint --add-route-table-ids <rtb-id>` |
| リソース管理とデータ保護が「読み込み中」のまま。ファイル操作は動く | デプロイ済み Lambda に VPC 設定が入っておらず、ONTAP 管理 LIF に到達できない。関数のタイムアウトまで待つので、エラーではなく無限の読み込みに見える | `make portal-preflight` で確認。`no VpcConfig` と出たら sandbox を再デプロイする。デプロイが auth スタックで失敗している場合は「同じアカウントに sandbox が複数あるとき」を参照 |
| サインインが「ユーザー名またはパスワードが違います」で通らない | 出力ファイルが別の sandbox のプールを指している | `make portal-preflight` でプールの所属を確認し、そのプールにアカウントを作り直す |
| `CDK Assembly Error` | cdk-nag が走っている（通常は CI-only） | `.amplify/artifacts` を削除して再起動 |
| 画面が固まる / ファンが回り続ける | 下記「画面が固まったときの切り分け」を参照 | まずタブを閉じる。閉じれば原因はブラウザ側 |

### 画面が固まったときの切り分け

「重い」には**バックエンド待ち**と**ブラウザのタブ側**の 2 種類があり、対処が逆になります。
先に見分けてください。

| 見え方 | どちら | 対処 |
|---|---|---|
| 「読み込み中」が出たまま。ページのスクロールや他メニューのクリックは効く | バックエンド待ち | 待つ。30 秒以上なら Lambda のタイムアウトかネットワーク（VPC Endpoint）を疑う |
| スクロールもクリックも反応しない。PC のファンが回り、ブラウザが 1 コア分の CPU を使い続ける | ブラウザのタブ側 | **リロードせずタブを閉じる**。開き直せば復帰する |
| 特定の画面だけ固まり、他の画面は軽い | その画面の描画量 | 一覧が大きい場合は絞り込みを使う。ファイル一覧は「さらに読み込む」で分割して読む |

**リロードで直らないときにタブを閉じる理由**: リロードはページ内のスクリプトを作り直すため、
描画ループが原因の場合は同じ状態が再現します。タブを閉じるとその描画プロセスごと破棄され
ます。ブラウザの拡張機能やブックマークレット、開発者ツールに貼ったスクリプトを使っていた
場合は、それが原因である可能性が高いので、無効にしてから開き直してください。

**CPU の確認方法**: macOS はアクティビティモニタ、Windows はタスクマネージャーで
`Google Chrome Helper (Renderer)` 相当のプロセスを見ます。1 つだけが 100% 付近に張り付いて
いる場合、サーバー側ではなくそのタブの中で処理が回っています。Chrome なら Shift+Esc の
ブラウザ内タスクマネージャーでタブ単位に確認できます。

**それでも直らない場合に集めていただきたい情報**: 固まった画面の名前、直前に行った操作、
ブラウザとバージョン、開発者ツールの Console に出ているエラー。これがあると原因の切り分けが
できます。Console の内容にファイル名やユーザー名が含まれることがあるため、共有前に確認して
ください。

## 同じアカウントに sandbox が複数あるとき

sandbox は `--identifier` ごとに独立したスタックになりますが、**共有しているものが 3 つ**
あります。いずれも失敗が「エラー」ではなく「動いているように見えて動かない」形で出るため、
先に把握してください。

### 1. `amplify_outputs.json` は 1 つしかない

ブラウザが読む接続情報はこのファイル 1 つで、`ampx sandbox` を実行するたびに**最後に走った
sandbox の内容で上書き**されます。別の sandbox をデプロイした直後は、画面は普通に開き、
サインイン画面も出ますが、**払い出したアカウントが存在しないプールに対して認証**しようと
します。表示されるのは「ユーザー名またはパスワードが違います」だけです。

払い出す前に、いま出力がどの sandbox を指しているか確認します。

```bash
make portal-preflight
```

`pool ap-northeast-1_XXXX ... belongs to sandbox 'demo'` と出た場合、アカウントは**その
プールに**作る必要があります。

### 2. 既存の Cognito User Pool は CloudFormation から更新できない

一度作られた User Pool は、プロパティを 1 つ変えるだけでも Cognito が更新を拒否します
（`Invalid AttributeDataType input` → `AttributeDataType` を明示すると
`Required custom attributes are not supported currently`）。更新時に Cognito は `Schema` を
「追加する属性」として読むため、既存と同じスキーマを送ることが構造的に無効になります。

影響は認証まわりの変更が入った**あと**に出ます。しばらく触っていなかった sandbox は、
以降どのデプロイも auth スタックで失敗し、スタック単位でロールバックされるので**認証と無関係
な変更（Lambda の VPC 設定など）も適用されません**。

回避策はありません。Amplify 公式の手順（`defineAuth` を外してデプロイし戻す）はプール内の
全ユーザーを削除します。**新しい identifier で作り直すのが唯一の道**で、新規作成なら最初から
現在の構成で作られるため問題は起きません。

### 3. DynamoDB ゲートウェイエンドポイントは VPC に 1 つだけ

ゲートウェイエンドポイントの実体はルートテーブルのルートで、ルートテーブルは 1 つの
プレフィックスリストにつき 1 ルートしか持てません。同じルートテーブルを指した 2 つ目の
sandbox は、他のリソースが 2 分ほど正常に作られたあとで次のように失敗し、スタックごと
ロールバックします。

```
route table rtb-xxxx already has a route with destination-prefix-list-id pl-xxxx
```

既にルートがある VPC にデプロイする場合は、そのルートを再利用すると宣言します。

```bash
AMPLIFY_PORTAL_DDB_GW_ENDPOINT_EXISTS=1 npx ampx sandbox --once --identifier demo
```

関数が必要とするのはルートであって所有権ではないので、既存のルートで同じように動きます。
現状は次で確認できます（`make portal-preflight` も同じ判定をします）。

```bash
aws ec2 describe-route-tables --route-table-ids <rtb-id> \
  --query "RouteTables[].Routes[?DestinationPrefixListId!=null]"
```

### URL を渡す前の確認

`make portal-preflight` は次の 3 つを、設定ファイルではなく**デプロイ済みの実物**を読んで
突き合わせます。

1. 出力ファイルが指すプールが存在し、どの sandbox のものか
2. ONTAP を呼ぶ関数が VPC の中にあるか（無い場合、管理 LIF は private アドレスなので到達
   できず、UI は「読み込み中」で止まったままになります）
3. DynamoDB のルートの有無が設定の宣言と一致しているか

**ページが HTTP 200 を返すことは、誰かがサインインできる証明にはなりません。** 200 が示すの
は静的ファイルが配信されたことだけで、認証はブラウザから Cognito への別の通信です。渡す前に
確認するのは上の 1 番、つまりプールの同一性です。

## 本番移行チェックリスト

DemoMode/sandbox で検証後、本番に持っていく際の確認項目:

| # | 項目 | 対応 |
|---|------|------|
| 1 | IAM 最小権限化 | `resources: ["*"]` を具体的な ARN に制限。portal-config.ts のコメント参照 |
| 2 | Lambda Security Group 分離 | FSx SG を共用せず、Lambda 専用 SG を作成。Outbound: TCP/443 (ONTAP mgmt LIF IP + VPC Endpoint) のみ |
| 3 | Cognito 本番設定 | MFA 必須化、パスワードポリシー強化、External IdP (SAML/OIDC) 連携 |
| 4 | ログ保持期間 | `LogRetentionInDays` を規制要件に合わせて設定 (FISC: 2557日/7年, SOX: 1825日/5年) |
| 5 | CloudTrail 有効化 | S3 AP ARN に対する Data Event + Management Event を有効化 |
| 6 | Amplify Hosting | `amplify deploy` で本番 CloudFront + カスタムドメイン |
| 7 | WAF 追加 | AppSync に AWS WAF を追加（レート制限、IP フィルタ） |
| 8 | Bedrock data residency | 使用モデルの推論リージョンを確認。ap-northeast-1 の Nova/Claude は同リージョンで推論（cross-region 送信なし） |
| 9 | cdk-nag 有効化 | CI で `CDK_NAG=1` を設定し、新たな違反を検出 |
| 10 | Provisioned Concurrency | VPC Lambda の Cold Start を 1-2 秒に短縮 (オプション) |
| 11 | GraphQL Introspection 無効化 | AppSync Console → Settings → Introspection: OFF（スキーマ情報漏洩防止） |
| 12 | CloudWatch アラーム | VPC Lambda p99 レイテンシ > 5s のアラームを設定。Provisioned Concurrency 検討トリガーに |
| 13 | Free Tier 終了後のコスト見積 | AppSync: ~$4/100万リクエスト、Cognito: $0.0055/MAU、Lambda: $0.20/100万呼出。月額目安: $25-60 (利用頻度による) |

> **Security note**: 本番では Lambda の Security Group を FSx SG から分離してください。FSx SG は全ポート open（intra-VPC 通信用）ですが、Lambda は TCP/443 outbound のみで十分です。

> **Data residency note**: Amazon Bedrock の On-Demand モデル (Nova, Claude) は、呼び出し元と同じリージョンで推論を実行します。ap-northeast-1 から呼び出した場合、データは ap-northeast-1 内に留まります。Cross-Region Inference を使用する場合はデータが他リージョンに送信される可能性があるため、規制要件に応じて `bedrock:InferenceProfile` の ARN を制限してください。

## 環境削除

```bash
# sandbox 環境を完全削除（CloudFormation スタック + 全リソース）
npx ampx sandbox delete

# S3 Object Lock テストバケットも削除する場合
aws s3 rb s3://fsxn-portal-objectlock-demo --force
```

## 次のステップ

**動いたら、次は利用者に渡す作業です。** 渡すもの（URL / アカウント / 操作ガイド）と、
利用者から質問が来たときにどこを見るかは、[引き渡しと問い合わせ対応ガイド](portal-handover-guide.md)
にまとめてあります。この文書（Getting Started）は**利用者に渡さないでください**。読者が違います。

- **[引き渡しと問い合わせ対応ガイド](portal-handover-guide.md)** — 渡す 3 点、管理場所の一覧、利用者の言葉 → 確認するものの逆引き、定型返信
- [PoC → 本番移行ガイド](../../../docs/ja/portal-poc-to-production.md) — DemoMode から本番接続への移行チェックリスト
- [スケーリングガイド](../../../docs/ja/portal-scaling-guide.md) — キャパシティプランニングとスループット管理
- [アクセシビリティ](../../../docs/en/portal-accessibility.md) — キーボードナビゲーション、ARIA、スクリーンリーダー対応
- [Admin Resource Management Demo Guide](../../../docs/en/admin-resource-management-demo.md) — 全管理機能の操作手順
- [AI Agent Demo Guide](./ai-agent-demo-guide.md) — AI エージェント機能の E2E デモ
- [DemoMode Guide](../../../docs/demo-mode-guide.md) — FSx for ONTAP なしでの検証方法
- [セクション構成ガイド](./portal-tabs-guide.md) — サイドバー 17 セクションの機能一覧、テーマ、モバイル対応
- [IMPLEMENTATION.md](./IMPLEMENTATION.md) — 設計意図と変更履歴
- [認可モデル](../../../docs/ja/portal-authorization-model.md) — Cognito グループによるアクセス制御
