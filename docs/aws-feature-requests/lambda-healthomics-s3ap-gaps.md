# 機能要望: Lambda セルフマネージドコードストレージ / AWS HealthOmics と FSx for ONTAP S3 Access Points の統合

> 🌐 **Language / 言語**: 日本語 | [English](lambda-healthomics-s3ap-gaps.en.md)

**提出者**: リポジトリ管理者 (AWS Community Builder)
**日付**: 2026-08-02
**プロジェクト**: [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
**コンテキスト**: 2026-07 の 2 リリース（Lambda セルフマネージドコードストレージ / AWS HealthOmics 東京リージョン対応）を本プロジェクトのワークフローへ組み込む可否評価
**ステータス**: **✅ 2026-08-02 に AWS Support へ提出済み**（サービス単位で 2 ケース: Lambda（FR-5 + FR-7）/ HealthOmics（FR-6））。**2026-09-09 追記**: HealthOmics 側に **FR-8**（実行タスクへの顧客所有ファイルシステムのマウント）を追加し、**同日 AWS Support へ新規ケースとして提出済み**（HealthOmics キュー / 一般的なガイダンス）。現状確認の質問と、実現したいこと（第 1〜第 3 希望）を同一ケースに含めています。根拠と tier は evidence ledger の `E-014` にあります。**2026-09-15 に回答を受領**し、要望はサービスチームへ連携されました。回答はベンダーサポートからのもので公開の根拠には使えないため、tier は `open` のままです。ケース番号は本リポジトリには記載しません（`.private/` で追跡）。
**関連**: [FR-1〜FR-4（既提出）](./fsxn-s3ap-improvements.md) / [オブジェクトサイズ上限の実測検証](../s3ap-object-size-limits-verification.md)（別ケースとして提出済み）

---

## エグゼクティブサマリー

**結論: 2 つのリリースはいずれも、現時点で Amazon FSx for NetApp ONTAP の S3 Access Points（以下 FSx for ONTAP S3 AP）を直接のデータソース／コードソースとして利用できません。** ただし性質が異なります。

| リリース | FSx for ONTAP S3 AP 直接利用 | ブロッカーの性質 | 標準 S3 併用での組み込み |
|---------|:---:|---|:---:|
| Lambda セルフマネージドコードストレージ | ❌ | **構造的** — S3 バージョニング必須、FSx for ONTAP S3 AP は Object Versioning 非対応 | ✅ 可能 |
| AWS HealthOmics（東京リージョン） | ❌ | **設計上** — 入力は Amazon S3 URI 前提、実行ごとに scratch volume へステージング（= コピー） | ✅ 可能 |

いずれも標準 S3 バケットを中継すれば本プロジェクトに組み込めますが、その中継ステップは FSx for ONTAP S3 AP 統合の中核価値である「データをコピーせず 1 か所で扱う」を損ないます。これは既提出の FR-1〜FR-4 と同じ構造の課題であり、本ドキュメントでは **FR-5 / FR-6 / FR-7** として整理します。

> **補足**: HealthOmics の東京リージョン対応自体は本プロジェクトにとって前進です。既存の UC7（genomics-pipeline）は README で「リアルタイムのバリアントコーリングパイプライン（BWA/GATK 等）の実行が必要」なケースを *適さないケース* として明示していました。HealthOmics がプライマリリージョン（ap-northeast-1）で使えるようになったことで、この空白を埋める新パターンが成立します。

> **2026-09-09 追記（FR-8 の追加）**: 上表の判定は **S3 Access Points 経由**の経路についてのものです。HealthOmics にはもう 1 つの経路が考えられます —— 実行タスクが顧客所有のファイルシステムを NFS でマウントする形です。AWS Batch（EC2/ECS のジョブ定義で `volumes` と `mountPoints` を宣言、EKS なら CSI）や AWS Deadline Cloud のカスタマー管理フリート（ワーカーホストが利用者のものなので、storage profile の `SHARED` ロケーションとしてマウント済みの共有をモデル化できる）では、この経路で FSx for ONTAP を直接使えます。HealthOmics は実行環境がサービス管理であるため、**この経路自体が露出していません**。S3 AP 経路（FR-6）とは要求先の仕組みが違うので、**FR-8** として分けて整理します [E-014]。

---

## 対象リリースの内容確認

### リリース 1: AWS Lambda セルフマネージドコードストレージ（2026-07）

[AWS Lambda がセルフマネージド型のコードストレージを発表](https://aws.amazon.com/jp/about-aws/whats-new/2026/07/lambda-self-managed-code-storage/) および [Self-managed S3 code storage（Lambda デベロッパーガイド）](https://docs.aws.amazon.com/lambda/latest/dg/configuration-self-managed-storage.html) より要約:

| 項目 | 内容 |
|------|------|
| 機能 | `S3ObjectStorageMode: REFERENCE` を指定すると、Lambda が自アカウントの S3 バケット内 .zip を**コピーせず直接参照**する |
| 効果 | Lambda マネージドコードストレージのクォータを消費しない / 関数のアクティベーション時間短縮 |
| 併せて変更 | Lambda マネージドコードストレージのデフォルト上限を 75 GB → **300 GB**（リージョン・アカウントあたり）に引き上げ |
| 対象 | .zip アーカイブの**関数とレイヤー**の両方。コンテナイメージ関数は対象外 |
| 前提条件 | ① S3 **バージョニング有効化が必須**（Lambda がソースオブジェクトのバージョンを追跡するため）② `S3ObjectVersion` の指定 ③ バケットポリシーで `lambda.amazonaws.com` に `s3:GetObject` / `s3:GetObjectVersion` を許可 |
| 継続的な依存 | Lambda はコード再最適化のためソースオブジェクトに**定期的にアクセス**する。アクセスを失うと関数は `Inactive` に遷移する |
| 変わらない点 | .zip デプロイパッケージ上限 250 MB（解凍後）は不変 |
| 提供範囲 | 全商用リージョン |

*上記は AWS 公式ドキュメントの内容をライセンス上の制約に配慮して要約したものです。正確な文言はリンク先を参照してください。*

### リリース 2: AWS HealthOmics 東京・オハイオリージョン対応（2026-07-20）

[AWS HealthOmics がさらに 2 つの AWS リージョンで利用可能に](https://aws.amazon.com/jp/about-aws/whats-new/2026/07/healthomics-tokyo-ohio/) より要約:

| 項目 | 内容 |
|------|------|
| 追加リージョン | **アジアパシフィック (東京)**、米国東部 (オハイオ) |
| 対象機能 | プライベートワークフロー |
| ワークフロー言語 | Nextflow / WDL / CWL |
| 組み込み機能 | バージョン管理されたワークフロー開発のための Git 統合、Amazon ECR によるサードパーティコンテナレジストリ対応 |
| コンプライアンス | HIPAA 適格サービス |
| 対応リージョン（全体） | 米国東部（バージニア北部、オハイオ）、米国西部（オレゴン）、欧州（フランクフルト、アイルランド、ロンドン）、イスラエル（テルアビブ）、アジアパシフィック（ソウル、シンガポール、東京） |

*上記は AWS 公式アナウンスの内容をライセンス上の制約に配慮して要約したものです。*

> **リージョン整合性に関する補足**: 本プロジェクトの主デプロイ先は ap-northeast-1 です。FSx for ONTAP S3 AP は東京リージョンで提供されており（[対応リージョン一覧](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)）、HealthOmics も東京対応となったため、**両サービスを同一リージョンに配置する前提条件は満たされました**。残る障壁はリージョンではなくデータ経路です。

---

## 統合可否判定

| 判定軸 | Lambda セルフマネージドコードストレージ | AWS HealthOmics |
|--------|:---:|:---:|
| FSx for ONTAP S3 AP を直接ソースに指定 | ❌ 不可 | ❌ 不可 |
| 実行タスクへ顧客所有ファイルシステムを NFS マウント | — | ❌ 手段なし（FR-8） |
| 標準 S3 バケット経由での組み込み | ✅ 可能 | ✅ 可能 |
| CloudFormation（`AWS::Lambda::Function`）対応 | ✅ `Code.S3ObjectStorageMode` あり | — |
| AWS SAM（`AWS::Serverless::Function`）対応 | ⚠️ **未確認** — SAM リソースリファレンスに該当プロパティの記載を確認できず | — |
| 本プロジェクトへの適用推奨度 | △ 条件付き（FR-7 の解決待ち） | ○ 新パターンとして成立 |

---

## FR-5: Lambda セルフマネージドコードストレージでの FSx for ONTAP S3 AP 参照対応

### 現状

Lambda セルフマネージドコードストレージは S3 バージョニングの有効化を必須要件としています。[Self-managed S3 code storage](https://docs.aws.amazon.com/lambda/latest/dg/configuration-self-managed-storage.html) では、セットアップ手順の第 2 段階としてバケットのバージョニング有効化が挙げられ、その理由としてソースオブジェクトのどのバージョンを使うかを Lambda が追跡する必要があることが示されています。加えて `S3ObjectVersion` の指定が求められます。

一方、[Access point compatibility（FSx for ONTAP ユーザーガイド）](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) では以下が非対応として記載されています:

| 要素 | FSx for ONTAP S3 AP の状態 |
|------|---------------------------|
| Object Versioning | Limitations セクションに非対応として記載 |
| `ListObjectVersions` | Not supported |
| `GetBucketPolicy` / `PutBucketPolicy` | Not supported |

*上記は AWS 公式ドキュメントの内容をライセンス上の制約に配慮して要約したものです。*

したがって、FSx for ONTAP S3 AP をコードソースとして使うには **3 つの前提すべてが満たせません**:

1. バージョニングを有効化できない
2. 取得すべき `S3ObjectVersion` が存在しない
3. `lambda.amazonaws.com` サービスプリンシパルを許可するバケットポリシーを設定する経路がない（Access Point ポリシーは存在するが、ONTAP 側のファイルシステム identity（UNIX / Windows ユーザー）による二段階認可を AWS サービスプリンシパルがどう通過するかは未定義）

さらに、Lambda がコード再最適化のためソースオブジェクトへ定期アクセスし、アクセス喪失時に関数が `Inactive` になる挙動は、ファイルシステム側の可用性（ボリューム容量、AD 到達性など）が Lambda 関数の状態に直結することを意味します。これは要望を実現する際に慎重な設計が必要な点です。

### 本プロジェクトへの影響

本リポジトリでは **37 のテンプレート**が `AWS::Serverless::LayerVersion`（"SharedLayer"）を定義し、`shared/` 配下の共通 Python モジュールをレイヤーとして配布しています。多くはリポジトリルートを `ContentUri` としており、`sam deploy` ごとに新しいレイヤーバージョンが発行され、`COPY` モードでは Lambda マネージドストレージクォータを消費し続けます。

| 対象 | 数 | 影響 |
|------|---:|------|
| SharedLayer を持つテンプレート | 37 | レイヤーバージョンが累積し、デプロイ・再デプロイのたびにクォータを消費 |
| Lambda 関数（全パターン合計） | 100+ | いずれも .zip パッケージ。`REFERENCE` モードの対象になり得る |

デフォルト上限が 300 GB に引き上げられたことで当面の圧力は下がりましたが、複数リージョン・複数アカウントで全パターンを検証する Partner/SI のワークフローでは、クォータ管理が依然として運用項目として残ります。

**FSx for ONTAP 文脈での固有価値**: 本プロジェクトが対象とする EDA・ゲーム・DevOps 系パターン（`semiconductor-eda`、`gaming-build-pipeline`、`devops-cicd`）では、ビルドサーバーが成果物を NFS / SMB 経由で FSx for ONTAP へ書き出す運用が一般的です。デプロイパッケージが既にファイルシステム上に存在するなら、標準 S3 バケットへの再アップロードは冗長なコピーです。FSx for ONTAP S3 AP を直接参照できれば、「ビルド成果物の唯一の情報源はファイルシステム」という運用がそのまま Lambda デプロイに繋がります。

### 要望する挙動

`AWS::Lambda::Function` の `Code` プロパティおよび `create-function` / `update-function-code` / `publish-layer-version` において、`S3Bucket` に FSx for ONTAP S3 AP のエイリアスまたは ARN を指定できるようにする。実現方式として以下のいずれかを想定します:

- **オプション A**: FSx for ONTAP S3 AP で Object Versioning を（ONTAP Snapshot をバージョンとして射影する形などで）サポートし、`S3ObjectVersion` を取得可能にする。FR-4（既提出）と同一方向の要望です。
- **オプション B**: バージョニング非対応のソースに対して、`S3ObjectVersion` の代わりに ETag またはオブジェクトの最終更新時刻を変更検知に使う代替モードを Lambda 側に用意する。
- **オプション C**: Lambda がサービスプリンシパルではなく**関数の実行ロール相当の IAM プリンシパル**でソースを取得する経路を提供し、Access Point ポリシー + ファイルシステム identity の既存二段階認可モデルをそのまま利用できるようにする。

いずれの方式でも、Access Point ポリシーとファイルシステム identity による二段階認可（[Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html) に記載）を尊重する必要があります。

### 本プロジェクトでの回避策

標準 S3 バケット（バージョニング有効）をデプロイ成果物用に用意し、`S3ObjectStorageMode: REFERENCE` を指定する。ファイルシステム上のビルド成果物は S3 AP `GetObject` → 標準 S3 `PutObject` で中継する（= コピーステップが 1 つ増える）。現時点では FR-7 が未解決のため、本リポジトリの SAM ベースのパッケージングには未適用です。

---

## FR-6: AWS HealthOmics の入出力への FSx for ONTAP S3 AP 指定対応

### 現状

HealthOmics のワークフロー実行は、入力・出力の双方で Amazon S3 URI を前提としています。

[HealthOmics run inputs](https://docs.aws.amazon.com/omics/latest/dev/workflows-run-inputs.html) によれば、ワークフロー定義が入力ファイルを指定している場合、HealthOmics は実行専用の scratch ボリュームへファイルを**ステージング**し、それらは読み取り専用となります。入力パラメータは単一オブジェクトのキー、末尾スラッシュによるプレフィックス、Nextflow では glob パターンとして解釈されます。

[Start a run in HealthOmics](https://docs.aws.amazon.com/omics/latest/dev/starting-a-run.html) によれば、出力先は `s3://bucket/prefix/object` 形式の Amazon S3 ロケーションを必須設定として指定します。またサービスロールには Amazon S3 と KMS に対する権限が必要とされています。

*上記は AWS 公式ドキュメントの内容をライセンス上の制約に配慮して要約したものです。*

加えて、[Using access points with AWS services（FSx for ONTAP ユーザーガイド）](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html) が統合例として挙げているサービスは Athena、Lambda、AWS Glue、Amazon Bedrock Knowledge Bases、Amazon EMR Serverless、CloudFront、AWS Transfer Family であり、**AWS HealthOmics は含まれていません**。

以上から、FSx for ONTAP S3 AP を HealthOmics の入力元・出力先として使うことは現時点で未サポートと判断します。技術的な懸念点は 2 つです:

1. **ステージング（コピー）が設計に組み込まれている** — 入力は scratch ボリュームへコピーされるため、仮に S3 AP URI を受け付けたとしても「データを動かさない」という価値の一部は得られません。ただしコピー先が実行専用の一時領域である点は、恒久的な二重保管とは性質が異なります。
2. **暗号化モデルの差異** — HealthOmics は S3 と KMS に対する権限を前提としますが、FSx for ONTAP S3 AP は SSE-FSX が唯一のサーバーサイド暗号化モードです（[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)）。サービスロールの権限設計に差異が生じます。

### 適用範囲と、断定していないこと

**この制限は FSx for ONTAP S3 AP に固有ではないと考えています。** `StartRun` の
[`outputUri`](https://docs.aws.amazon.com/omics/latest/api/API_StartRun.html) は
[実行例](https://docs.aws.amazon.com/omics/latest/dev/starting-a-run.html)のとおり
`s3://<bucket>/<prefix>` の形で示されており、先頭のパスセグメントをバケット名として扱う契約です。
アクセスポイントの ARN や仮想ホスト形式の URL を渡す前提の記載は見つけられませんでした。
**標準の S3 Access Point でも同じかどうかは当方で試していないので `open` です。**

**上記「現状」で挙げた暗号化モデルの差異は、障害として確認したものではありません。** SSE-FSX で
実際に何が起きるかは、出力先として AP を指定できない以上、当方では確かめられません。本ドキュメントでも
障害として断定しません。

オブジェクトサイズ上限についても補足します。**単一 `PutObject` の上限が支配要因になるとは限りません。**
コピーバックを行うのは本プロジェクト側の Lambda なので、適用される上限は呼び出す S3 / FSx API のもの
です。HealthOmics 自身の書き込み方式は当方の観測範囲外で `open` です。

ドキュメント要望（FSx for ONTAP ユーザーガイドに HealthOmics の対応状況を明記すること）は
起票済みです（2026-08 起票）。

### 2026-09 再確認: VPC networking モードの登場と、到達性とマウントの差

2026-08-02 の提出時点には無かった機能が増えています。以下は 2026-09-09 に該当ページを全文で読んで確認した内容です。

- `StartRun` の `networkingMode` は `RESTRICTED | VPC` で、既定は `RESTRICTED`。`RESTRICTED` では同一リージョンの Amazon S3 と Amazon ECR にしか到達せず、他の AWS サービス・他リージョン・インターネットには到達しません。
- `VPC` モードでは、HealthOmics が顧客 VPC のサブネットに ENI（`Service=HealthOmics` / `eniType=CUSTOMER` のタグ付き）を作成し、実行トラフィックをそこへ通します。想定用途として「VPC 内の AWS リソースへの接続」「プライベートネットワーク上のオンプレミスリソースへのアクセス」が挙げられています。サブネットは 1 AZ あたり 1 つ、最大 16、セキュリティグループは最大 5。Configuration リソースが `ACTIVE` になるまで最大 15 分。
- 同じページが、**ワークフロー実行は HealthOmics が所有・管理する VPC の内部で動き、その VPC は顧客に見えない**こと、顧客 VPC への接続設定はその管理 VPC に影響しないことを明記しています。

**FR-6 の判定は変わりません。** `StartRun` API リファレンス（2026-09-09 全文確認）の `outputUri` は "An output S3 URI for the run. The S3 bucket must be in the same region as the workflow." と記載され、バケットを前提とする契約のままです。入力側も Amazon S3 URI の解釈（単一オブジェクトキー / 末尾スラッシュのプレフィックス / Nextflow の glob）として文書化されています。

変わったのは**到達性**です。VPC モードなら、ONTAP の NFS LIF や S3 AP の VPC エンドポイントに実行タスクからネットワーク的に到達しうる状態になります。

ただし**到達性はマウントではありません。** 未確立の点が 2 つあり、いずれも `open` として扱います。

1. `StartRun` のリクエストボディに、ファイルシステムやマウント先を指定するフィールドは存在しません（全フィールドを全文で確認）。実行ストレージはサービスが用意する一時ファイルシステムで、`DYNAMIC` は NFS プロトコル、`STATIC` は Lustre プロトコル（1,200 GiB または 2,400 GiB の倍数）。持ち込みファイルシステムのパラメータがありません。
2. ワークフロー定義のタスク内から `mount -t nfs` を発行できるか（タスクコンテナに `CAP_SYS_ADMIN` が付与されているか）は**当方で未検証**です。公開ドキュメントにも記載を見つけられていません。

この 2 点を根拠に「マウントできない」と断定はしません。**AWS に確認したうえで、無い場合は機能改善要望として扱う**という順序にします（下記 FR-8）[E-014]。

### 本プロジェクトへの影響

| パターン | 影響 |
|---------|------|
| UC7 `genomics-pipeline` | FASTQ/BAM/VCF は FSx for ONTAP 上にある。品質チェックとバリアント統計集計は Lambda で実装済みだが、**BWA/GATK 等の本格的なバリアントコーリングは対象外**と README に明記している。HealthOmics で埋められる空白だが、入力を標準 S3 へコピーする必要がある |
| `solutions/flexcache/life-sciences-research` | FlexClone による研究者ごとのデータセット分岐が強み。分岐したボリュームを HealthOmics へ直接入力できれば「クローン → 解析」が 1 ステップになるが、現状はクローン → S3 コピー → 解析の 3 ステップ |
| UC5 `healthcare-dicom` | HIPAA 適格サービスである HealthOmics との併用シナリオ（画像 + ゲノム）で、両者のデータ経路が分かれる |

ゲノムデータは 1 サンプルあたり FASTQ で数十 GB規模になり得ます。中継コピーは転送時間・一時ストレージコスト・そして**規制対象データの複製箇所が増えること自体のガバナンス負荷**を生みます。ライフサイエンス領域では「データの所在を単一に保つ」ことが監査要件と直結するため、このコピーステップは技術的な非効率以上の意味を持ちます。

> **ガバナンスに関する補足**: 本節はデータ保管場所の設計上の考慮点を述べたものであり、特定の規制（HIPAA、GxP 等）への準拠可否についての法的・コンプライアンス判断ではありません。適用要件の解釈は各組織の法務・コンプライアンス部門の判断に従ってください。

### 要望する挙動

- **入力**: `StartRun` の入力パラメータ（および `--parameters` JSON 内の S3 URI 値）で、FSx for ONTAP S3 AP のエイリアス／ARN／仮想ホスト形式 URI を受け付ける。ステージングは HealthOmics 側の既存挙動のまま（S3 AP から scratch ボリュームへ読み出す）で構いません。プレフィックス指定とサンプルシート方式の双方が動作することが重要です。
- **出力**: `--output-uri` に FSx for ONTAP S3 AP を指定可能にする。これにより解析結果が NFS / SMB 利用者にそのまま見える状態になります。SSE-FSX を暗号化モードとして自動的に受け入れ、オブジェクトサイズ上限に従う挙動を期待します。
- **ドキュメント**: 実現時は [Using access points with AWS services](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html) の統合サービス一覧に HealthOmics を追加してください。

出力側のみでも実現価値は高く、**出力 > 入力**の優先順位を提案します。入力は HealthOmics が読み取り専用ステージングを行う設計上、ファイルシステム直読の利点が相対的に小さいためです。

### 本プロジェクトでの回避策

Step Functions で以下を構成します（未実装、新パターン候補としてバックログ化）:

1. Discovery Lambda: S3 AP `ListObjectsV2` で FASTQ/BAM を検出
2. Stage Lambda: S3 AP `GetObject` → 標準 S3 バケット `PutObject`（マルチパート）
3. `omics:StartRun` → 完了待機
4. Writeback Lambda: HealthOmics 出力（標準 S3）→ S3 AP `PutObject` で FSx for ONTAP へ書き戻し

ステップ 2 と 4 が FR-6 で削除できるステップです。

---

## FR-7: AWS SAM での `S3ObjectStorageMode` 指定対応

### 現状

`S3ObjectStorageMode` は [`AWS::Lambda::Function` の `Code` プロパティ](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-lambda-function-code.html)に `COPY | REFERENCE` の許可値を持つプロパティとして文書化されています。一方 `AWS::Serverless::Function` / `AWS::Serverless::LayerVersion` は `CodeUri` / `ContentUri`（ローカルパスまたは S3 URI）のみを公開しており、SAM リソースリファレンスに該当プロパティの記載を確認できませんでした。

> **状況の更新（2026-09 再確認）**: **この要望は解決済みで、公開ドキュメントにも反映されています。**
> SAM の [`FunctionCode`](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-functioncode.html)
> に `StorageMode` プロパティが `COPY | REFERENCE` として記載され、`AWS::Lambda::Function` の
> `Code.S3ObjectStorageMode` へそのまま渡されると明記されています。

### プロパティ名が CloudFormation と SAM で違う

**同じ設定でも名前が違うので、CloudFormation の名前を SAM テンプレートに書いても効きません。**

| テンプレート | プロパティ | 出典 |
|---|---|---|
| `AWS::Lambda::Function` | `Code.S3ObjectStorageMode` | [Code プロパティ](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-lambda-function-code.html) |
| `AWS::Serverless::Function` | `CodeUri.StorageMode` | [FunctionCode](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-functioncode.html) |

```yaml
# AWS::Serverless::Function ではこちら
CodeUri:
  Bucket: amzn-s3-demo-bucket-name
  Key: mykey-name
  Version: 121212
  StorageMode: REFERENCE
```

**`REFERENCE` を使うにはバケットのバージョニングを有効にし、Lambda サービスプリンシパルに
オブジェクトへのアクセスを与える必要があります**（同ページに記載）。

> ⚠️ **古い SAM を使っている場合の注意**: プロパティを知らないバージョンの SAM では、
> **`sam validate` と `sam deploy` が成功しても設定が適用されません。** デプロイ結果からは
> 気づけないので、`REFERENCE` を前提にするなら適用後に実際のモードを確認する手順を入れてください。
> `update-function-code` でも毎回の指定が必要で、省略すると `COPY` に戻ります。

Inactive 状態への遷移（Lambda がソースオブジェクトを再読み込みし、アクセスできなくなると関数を
Inactive にする）については、**これが FSx for ONTAP S3 AP 非対応の理由かどうかを当方では
確かめられていないため `open` です。** 原因として断定しません。

### 上流での対応状況（2026-09 再確認）

FR-7 の要望内容は **upstream に実装・マージされ、公開ドキュメントにも反映されました。** 本項は `aws/serverless-application-model` と SAM のリファレンスを直接読んだ結果です。

| 項目 | 内容 |
|------|------|
| 該当 PR | [aws/serverless-application-model#3959](https://github.com/aws/serverless-application-model/pull/3959) `feat: pass S3ObjectStorageMode through from CodeUri and ContentUri`（2026-07-20 マージ、テストは [#3961](https://github.com/aws/serverless-application-model/pull/3961)） |
| **SAM 側のプロパティ名** | **`StorageMode`**（`CodeUri` / `ContentUri` の中）。CloudFormation 側の `S3ObjectStorageMode` とは名前が異なる |
| 変換後のマッピング | `CodeUri.StorageMode` → `Code.S3ObjectStorageMode` |
| リリース状況 | **リリース済み。** SAM の [`FunctionCode`](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-functioncode.html) に `StorageMode` が記載されています（2026-09 再確認）。2026-08 時点では `aws-sam-translator` 1.111.0 が当該コードより前で未反映でした |

```yaml
# 現行のリファレンスに記載のある形
CodeUri:
  Bucket: my-artifacts
  Key: app.zip
  StorageMode: REFERENCE     # ← SAM 側の名前。S3ObjectStorageMode ではない
```

> ⚠️ **名前の非対称性に注意**: `CodeUri` に CloudFormation 側の名前 `S3ObjectStorageMode` を書いた場合、リリース後も**引き続き無言で破棄されます**。受け付けられるのは `StorageMode` のみです。

**したがって現時点の結論は変わりません**（現行リリースでは SAM 経由で `REFERENCE` を指定できないため、上記のネイティブリソース方式が有効な回避策）。ただし理由は「SAM が未対応」ではなく「**実装済みだがリリース待ち、かつプロパティ名が `StorageMode`**」です。リリース後は本節と回避策の再評価が必要です。

### バリデーション欠落の起票

未知プロパティが無言で破棄される点は、本プロジェクトから公開 issue として起票しました: [aws/serverless-application-model#3970](https://github.com/aws/serverless-application-model/issues/3970)

AWS サポートの内部チケットは非公開で、代理起票もできないとの回答だったため、自前の検証結果に基づいて起票しています。ローカル検証（`aws-sam-translator` 1.111.0）で確認した挙動:

| `CodeUri` に指定した内容 | 変換結果 | 出力への反映 |
|------------------------|---------|------------|
| `S3ObjectStorageMode: REFERENCE` | 成功・警告なし | なし |
| `StorageMode: REFERENCE` | 成功・警告なし | なし（1.111.0 では未実装のため） |
| `TotallyMadeUpProperty: whatever` | 成功・警告なし | なし |

`sam validate` と `sam validate --lint` の**両方が valid を返します**。一方で SAM スキーマの `definitions.CodeUri` は `"additionalProperties": false` を宣言しており、スキーマ上は不正と定義されているのに変換時に強制されていない、という不整合が論点です。

### 本プロジェクトへの影響

本リポジトリの全パターンは SAM（`AWS::Serverless::Function` + ローカル `CodeUri`）でパッケージングされ、`sam build` / `sam deploy` が成果物のアップロードを管理しています。`S3ObjectStorageMode` を SAM で指定できない場合、`REFERENCE` モードを採用するには以下のいずれかが必要です:

- 全テンプレートを `AWS::Lambda::Function` へ書き換える（SAM の簡潔さと `Policies` 短縮記法を失う）
- `sam deploy` 後に `update-function-code` を追加実行する（`S3ObjectStorageMode` は毎回明示が必要なため、CloudFormation の状態管理と乖離するリスクがある）

どちらもリポジトリ全体のパッケージング規約の変更となり、37 テンプレートに影響します。そのため本プロジェクトでは FR-7 の解決を待つ判断としました。

### 要望する挙動

`AWS::Serverless::Function` および `AWS::Serverless::LayerVersion` で `S3ObjectStorageMode`（または同等の SAM 側プロパティ）をサポートし、`sam deploy` が管理する成果物バケットに対して `REFERENCE` モードを選択できるようにする。加えて、`sam deploy` の成果物バケットでバージョニングを自動有効化するか、未有効時に明確なエラーを返すことを期待します。

### 本プロジェクトでの回避策

`COPY` モードのまま運用します。現時点で `REFERENCE` モードを必要とするパターンが無いため、リポジトリ全体のパッケージング規約を変更する理由がありません。必要が生じた場合は、全テンプレートを書き換えるのではなく、上記の**サポートされる回避策**（ネイティブ `AWS::Lambda::Function`）を該当する関数にだけ適用します。

---

## FR-8: HealthOmics 実行タスクへの顧客所有ファイルシステムのマウント対応

**追加日**: 2026-09-09。FR-6（S3 AP 経路）とは要求先の仕組みが違うため別番号にしています。

### 現状

HealthOmics の実行ストレージは、サービスがワークフロー実行ごとに用意する一時ファイルシステムです（[Run storage types](https://docs.aws.amazon.com/omics/latest/dev/workflows-run-types.html)、2026-09-09 全文確認）。`DYNAMIC` は NFS プロトコル、`STATIC` は Lustre プロトコルで、`STATIC` の容量は 1,200 GiB または 2,400 GiB の倍数、スループットはプロビジョニング容量 1 TiB あたりベースライン 200 MB/s・バースト最大 1300 MB/s と記載されています。加えて各タスクには `/tmp` の一時領域（`scratchStorageMode`）が付きます。

[`StartRun` API リファレンス](https://docs.aws.amazon.com/omics/latest/api/API_StartRun.html)（2026-09-09 全リクエストフィールドを確認）には、**顧客所有のファイルシステムやマウント先を指定するフィールドがありません**。ストレージ関連のフィールドは `storageType` / `storageCapacity` / `scratchStorageMode` の 3 つで、いずれもサービス提供ストレージの選択とサイズ指定です。

[Connecting HealthOmics workflows to a VPC](https://docs.aws.amazon.com/omics/latest/dev/workflows-vpc-networking.html)（同日、全文確認）は、実行が HealthOmics 所有の管理 VPC 内で動き、その VPC は顧客に見えないと明記しています。`networkingMode: VPC` で顧客 VPC に ENI が張られるのは**到達性のため**で、ファイルシステムをタスクに接続する仕組みとしては説明されていません。

*上記は AWS 公式ドキュメントの内容をライセンス上の制約に配慮して要約したものです。*

### 断定していないこと

**「マウントできない」とは書きません。** 確認できているのは「ドキュメントに記載された手段が見つからない」ことで、これは不在の証明ではありません。未確立の点:

- `networkingMode: VPC` で到達可能になった NFS エクスポートを、タスク内から `mount -t nfs` でマウントできるか（タスクコンテナの `CAP_SYS_ADMIN` の有無）。**当方未検証**、tier は `open`。
- ワークフロー定義言語（WDL / Nextflow / CWL）側にマウントを宣言する手段があるか。記載を見つけられていません。

### 他サービスとの差（比較のための整理、優劣の判定ではない）

| サービス | 実行ホストの所有者 | FSx for ONTAP の NFS 直接マウント |
|---|---|:---:|
| AWS Batch（EC2 / ECS） | 利用者 | ✅ ジョブ定義の `volumes` / `mountPoints` で可能 |
| AWS Batch（EKS） | 利用者 | ✅ CSI ドライバ経由で可能 |
| AWS Deadline Cloud（カスタマー管理フリート） | 利用者 | ✅ ホスト側でマウントし storage profile の `SHARED` としてモデル化 |
| AWS HealthOmics（プライベートワークフロー） | サービス | ❌ 手段が露出していない（本 FR）[E-014] |

差はストレージ機能ではなく**実行ホストの所有者**です。HealthOmics は実行基盤の管理を引き受ける代わりに、Amazon S3 を境界と定めた設計になっています。これは用途の分岐点であり、どちらが優れているという話ではありません。

### 本プロジェクトへの影響

FR-6 の回避策（Stage / Writeback の 2 ステップ）は、マウント経路が使えれば不要になります。とくに UC7 `genomics-pipeline` と `solutions/flexcache/life-sciences-research` では、FlexClone で作った研究者ごとのボリュームをそのまま解析対象にできるため、「クローン → 解析」が 1 ステップになります。ゲノム 1 サンプルの FASTQ が数十 GB になる規模では、ステージングの所要時間がワークフロー全体の実行時間に対して支配的になり得ます（**本プロジェクトでは未計測**。時間比の主張はしません）。

### 要望する挙動

優先順位は **FR-6（出力）> FR-6（入力）> FR-8** と考えています。FR-8 は実現時の効果が最も大きい一方、サービス側の設計変更としては最も重いと理解しているためです。

- **第 1 希望**: 実行ストレージとして顧客所有のファイルシステム（FSx for ONTAP のボリューム）を指定できるようにする。`networkingMode: VPC` の Configuration リソースにファイルシステムとマウントパスを追加する形が、既存の仕組みへの追加として自然だと考えています。
- **第 2 希望**: 読み取り専用の入力ロケーションとしてのみマウントを認める。入力は既に読み取り専用としてステージングされる設計なので、意味論の差が小さいはずです。
- **第 3 希望（現状の明文化）**: 上記がいずれも対象外である場合、**ドキュメントに「実行ストレージはサービス管理であり、顧客所有ファイルシステムのマウントには対応しない」と明記**してください。現在は「記載が無い」状態なので、利用者側が VPC networking モードの説明を読んで到達性とマウントを混同し得ます。当方も一度そう読みかけました。

### 本プロジェクトでの回避策

FR-6 と同じです（Stage → `StartRun` → Writeback）。マウント経路が無い前提でパターンを設計します。

---

## 二次的所見

本評価の過程で判明した、AWS への要望ではない項目:

1. **オブジェクトサイズ上限が 5 GB → 50 GB に変更されていました（対応済み）** — 現行の [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) はアップロード時のオブジェクトサイズ上限を **50 GB**、ダウンロードはそれ以上も可能と記載しています。

   **変更時期**: Wayback Machine のアーカイブでは **2026-03-08 時点で 5 GB**、**2026-06-25 時点で 50 GB** でした。対応する What's New アナウンスは確認できておらず、ドキュメント更新のみで反映されたと見られます（FSx for ONTAP ユーザーガイドの `doc-history.html` は現在 `what-is-fsx-ontap.html` にリダイレクトされ、公式な変更履歴を辿れません）。同じリビジョンで Object Annotations 系の行と `GetBucketCors` も追加されています。

   **重要な区別**: 「50 GB」は**オブジェクトサイズの上限**であり、単一 `PutObject` の上限ではありません。単一 PUT は Amazon S3 API 共通の **5 GB** 上限のままです（[Uploading objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html)）。したがって 5 GB〜50 GB のオブジェクトは Multipart Upload が必須です。リポジトリ内の「PutObject 最大 5 GB」という記述は単一 PUT の意味では依然として正しく、誤っていたのは「5 GB を超えるオブジェクトは扱えない」という上限の記述でした。

   本セッションでこの区別に沿って以下を修正済みです: `AGENTS.md`、`README.md` ほか全 8 言語、`docs/s3ap-compatibility-notes.{md,en.md}`、`docs/s3ap-performance-considerations.{md,en.md}`、`docs/design-considerations{,-en}.md`、`docs/{ja,en}/deployment-guide.md`、`docs/guides/s3ap-fsxn-specification.md`、`docs/cdn-comparison.*.md`（7 言語）、`docs/comparison-alternatives.md`、`docs/partner-si-one-pager.{md,en.md}`、`docs/file-portal-amplify-gen2.{md,en.md}`、`docs/{ja,en}/storage-browser-demo-guide.md`、`docs/*/portal-quick-reference.md` および `portal-user-guide.md`（8 言語）、`docs/nextcloud-external-storage-s3ap.{md,en.md}`、`docs/aws-feature-requests/file-portal-service-gap.{md,en.md}`、`docs/aws-feature-requests/fsxn-s3ap-improvements.md`（提出済み記録のため訂正注記として追記）、`docs/design-output-writer-multipart.md`、業界パターンの README / デモガイド、`drafts/blog/article-file-portal-draft.{md,en.md}`。

   > **設計への影響に関する補足**: `design-output-writer-multipart.md` のマルチパート昇格しきい値は単一 `put_object` の 5 GB 境界に基づいており、**この設計判断は変更不要**です。変わったのはマルチパート経由で到達できる上限（5 GB → 50 GB）であり、結果として `put_stream` の有用性が増しています。
   >
   > **AWS ドキュメント間の不整合**: [AWS Transfer Family のユーザーガイド](https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html)は現在も「アップロード操作のファイルサイズは 5 GB に制限される」と記載しています。これは Transfer Family 側の固有制約である可能性があるため、本対応では Transfer Family 文脈の記述は変更していません。AWS Support への確認事項として FR ケースに含める価値があります。
2. **`native-s3ap-notifications-evidence.md` の英語版が欠落しています** — 同ファイルは冒頭で `native-s3ap-notifications-evidence.en.md` へリンクしていますが、当該ファイルは存在しません。JA/EN parity 上の未解決項目です。
3. **HealthOmics の東京対応は UC7 の空白を埋めます** — UC7 README が明示している「適さないケース」（リアルタイムバリアントコーリング）は、FR-6 の回避策アーキテクチャで対応可能になります。新パターンとして起票する価値があります。
4. **Lambda マネージドストレージ 300 GB 化は当面の緩和策として有効です** — 37 レイヤー構成の本リポジトリでも、単一リージョンでの通常運用ではクォータ超過の懸念は下がりました。`REFERENCE` モードは必須ではなく最適化として位置づけられます。

---

## 優先順位（導入先視点）

| 順位 | FR | 理由 |
|:---:|-----|------|
| 1 | **FR-6（HealthOmics 出力）** | ライフサイエンス領域で「データ所在の単一性」が監査要件に直結する。出力側だけでも NFS/SMB 利用者が解析結果を直接参照できるようになり、価値が大きい |
| 2 | **FR-7（SAM 対応）** | AWS 側の実装コストが相対的に小さく、`REFERENCE` モードの採用障壁を実質的に取り除く。FR-5 の前提でもある |
| 3 | **FR-6（HealthOmics 入力）** | ステージング設計のため直読の利点は出力側より小さいが、大容量 FASTQ の転送時間短縮に効く |
| 4 | **FR-5（Lambda コードソース）** | 構造的ブロッカー（Object Versioning）を含み、既提出の FR-4 に依存する。回避策のコストも他より低い |
| 5 | **FR-8（実行タスクへのマウント）** | 実現時の効果は最大（ステージングが消え、FlexClone から直接解析できる）だが、サービス側の設計変更としては最も重い。第 3 希望（現状の明文化）だけでも読者の誤読を防げる |

既提出の FR-1〜FR-4 との統合優先順位では、**FR-2（イベント通知） > FR-6 > FR-1 > FR-7 > FR-3 > FR-4 ≈ FR-5 > FR-8** と考えています。FR-4（Versioning）と FR-5 が連動する点は、FR-4 のビジネスケースを補強する材料としてご参照ください。

---

## ビジネスケース

- **リージョン整合が揃った意味**: FSx for ONTAP S3 AP と HealthOmics が同一リージョン（ap-northeast-1）で利用可能になったため、日本のライフサイエンス導入先にとって「ゲノムデータは国内のファイルシステムに置き、解析も国内で実行する」構成が初めて成立しました。データ所在地要件が厳しい研究機関・製薬企業にとって、この整合は導入判断の前提条件です。残る障壁がデータ経路のみであることは、FR-6 の投資対効果が高いことを意味します。
- **コピーステップの累積コスト**: 本プロジェクトの既提出 FR で述べたとおり、PoC では通常 2〜3 個の標準 S3 バケットが必要になります。HealthOmics を加えると、入力ステージング用と出力受け取り用でさらに増えます。バケット数の増加はコストよりもガバナンス上の負荷（アクセス制御・保持ポリシー・監査ログの管理対象の増加）として顕在化します。
- **既存パターンの前提が変わる**: 37 テンプレートという規模は、パッケージング規約の変更コストが個別パターン単位では収まらないことを示します。FR-7 が解決すれば規約変更は 1 回で済み、解決しなければ採用を見送るという二者択一になります。

> **コストに関する補足**: 本節の数値はリポジトリ内のテンプレート実数（37 テンプレートが SharedLayer を定義）に基づく静的な集計です。特定導入先環境での実測値や本番規模の見積りではありません。

---

## AWS Support 提出用テキスト

以下は AWS Support ケース（Technical Support → Service: 該当サービス → Category: General guidance / Feature request）へそのまま貼り付ける想定の本文です。ケースは **サービス単位で分割**して起票します（FR-5・FR-7 は Lambda、FR-6・FR-8 は HealthOmics）。FR-8 は FR-6 と同じ HealthOmics のキューなので、ケースを増やさず同一ケースの Request 3 として扱います。FSx for ONTAP S3 AP 側の対応が必要な要望であることを本文で明示し、可能であれば Amazon FSx サービスチームへの共有を依頼します。

<details>
<summary><b>ケース 1: AWS Lambda（FR-5 + FR-7）</b></summary>

```
Subject: Feature request - Self-managed S3 code storage: support FSx for ONTAP S3 Access Points and AWS SAM

Category: General guidance / Feature request
Service: AWS Lambda
Region: ap-northeast-1

## Summary

Two related feature requests regarding the self-managed S3 code storage feature
announced in July 2026:

(1) Allow an Amazon FSx for NetApp ONTAP S3 Access Point to be used as the code
    source (S3Bucket) for functions and layers.
(2) Expose S3ObjectStorageMode through AWS SAM (AWS::Serverless::Function and
    AWS::Serverless::LayerVersion).

## Our use case

We maintain a public reference library of ~40 serverless patterns built on
FSx for ONTAP S3 Access Points (37 of the templates publish a shared Lambda
layer). The patterns target industries where build artifacts are already
produced onto a NAS share - semiconductor EDA, game build pipelines, and
DevOps CI/CD. In those environments the build server writes deployment
artifacts to the FSx for ONTAP file system over NFS or SMB.

## Request 1: FSx for ONTAP S3 Access Point as a code source

Today this is not possible. Per the Lambda developer guide, self-managed S3
code storage requires S3 versioning to be enabled on the bucket and requires
an S3ObjectVersion value. Per the FSx for ONTAP user guide, Object Versioning
and ListObjectVersions are not supported on access points attached to
FSx for ONTAP volumes, and GetBucketPolicy / PutBucketPolicy are not
supported either - so the documented bucket policy granting
lambda.amazonaws.com cannot be applied.

The customer impact is an extra copy step: artifacts that already exist on the
file system must be re-uploaded to a standard S3 bucket before Lambda can
reference them. This weakens the core value of the FSx for ONTAP S3 Access
Point integration, which is that data stays in one place.

We would welcome any of the following approaches:

  Option A - Support Object Versioning on FSx for ONTAP S3 Access Points
             (for example by projecting ONTAP Snapshots as object versions)
             so that S3ObjectVersion becomes available. This overlaps with a
             feature request we previously filed against FSx for ONTAP.
  Option B - Provide an alternative change-detection mode in Lambda that uses
             ETag or last-modified time instead of S3ObjectVersion, for code
             sources that do not support versioning.
  Option C - Retrieve the source object using an IAM principal (rather than
             the Lambda service principal) so that the existing two-layer
             authorization model of FSx for ONTAP S3 Access Points - access
             point policy plus file system identity - can be used as-is.

We would also appreciate guidance on the Inactive-state behaviour in this
context: because Lambda periodically re-reads the source object and moves the
function to Inactive if access is lost, a file-system-backed code source would
couple file system availability to function state. If that coupling is the
reason this is not supported, knowing that would help us document the
constraint accurately for customers.

## Request 2: AWS SAM support for S3ObjectStorageMode

S3ObjectStorageMode is documented on the Code property of
AWS::Lambda::Function, but we could not find an equivalent property on
AWS::Serverless::Function or AWS::Serverless::LayerVersion in the SAM
resource reference. The launch announcement lists AWS SAM as a supported
way to use the feature, so we may have missed it - if there is an intended
path, please point us to it.

If it is genuinely not yet supported: all of our patterns are SAM-based, so
adopting REFERENCE mode currently requires either rewriting 37 templates to
AWS::Lambda::Function (losing the SAM Policies shorthand) or running
update-function-code after sam deploy (which drifts from CloudFormation state,
since S3ObjectStorageMode must be specified on every call). Both are
repo-wide changes, so we have deferred adoption.

It would also help if sam deploy either enabled versioning on its managed
artifact bucket automatically, or returned a clear error when REFERENCE mode
is requested against a non-versioned bucket.

## What we are NOT asking for

We are not requesting a quota increase. The default increase from 75 GB to
300 GB per Region already relieved our immediate pressure. These requests are
about removing a copy step and about IaC parity.

## References

- Self-managed S3 code storage (Lambda Developer Guide)
  https://docs.aws.amazon.com/lambda/latest/dg/configuration-self-managed-storage.html
- AWS::Lambda::Function Code (CloudFormation Template Reference)
  https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-lambda-function-code.html
- Access point compatibility (FSx for ONTAP User Guide)
  https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html
- Accessing your data via Amazon S3 access points (FSx for ONTAP User Guide)
  https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html
- Public reference library (context for this request)
  https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns

If helpful, please share Request 1 with the Amazon FSx service team, since the
enabling change (Object Versioning on access points) sits on that side.
```

</details>

<details>
<summary><b>ケース 2: AWS HealthOmics（FR-6）</b></summary>

```
Subject: Feature request - HealthOmics: accept FSx for ONTAP S3 Access Points as run input/output, and clarify whether a customer-owned file system can be mounted

Category: General guidance / Feature request
Service: AWS HealthOmics
Region: ap-northeast-1

## Summary

Please allow AWS HealthOmics private workflow runs to use an Amazon FSx for
NetApp ONTAP S3 Access Point as the run input location and, with higher
priority, as the run output location (--output-uri).

Added 2026-09-09: a third, related request about mounting an FSx for ONTAP
volume into a run over NFS (Request 3 below). It is a separate mechanism from
the S3 Access Point path, so please treat it as a distinct item even though it
is in the same case.

## Why this matters now

HealthOmics private workflows became available in Asia Pacific (Tokyo) in July
2026. S3 Access Points for FSx for ONTAP are also available in Tokyo. For
Japanese life sciences customers this means that, for the first time, genomics
data can stay on an in-Region file system while analysis also runs in-Region.
The region alignment is now satisfied; the remaining barrier is the data path.

## Our use case

We maintain a public reference library of serverless patterns on FSx for ONTAP
S3 Access Points. One pattern (UC7, genomics-pipeline) performs FASTQ/BAM/VCF
quality checks and variant statistics aggregation on data that lives on
FSx for ONTAP. Its README explicitly lists real variant calling pipelines
(BWA/GATK and similar) as out of scope - which is exactly what HealthOmics
private workflows provide. A second pattern uses ONTAP FlexClone to give each
researcher an independent, space-efficient branch of a reference dataset.

The natural workflow is: clone the dataset on the file system, run the
bioinformatics pipeline against it, and write results back so that researchers
see them over NFS/SMB next to the source data.

## Current state

Run inputs must be Amazon S3 URIs, and HealthOmics stages input files to a
read-only scratch volume dedicated to the run. The run output location is a
required setting and must be an Amazon S3 location in s3://bucket/prefix form.
AWS HealthOmics is not listed among the integrated services in "Using access
points with AWS services" in the FSx for ONTAP user guide (which currently
lists Athena, Lambda, AWS Glue, Amazon Bedrock Knowledge Bases, Amazon EMR
Serverless, CloudFront, and AWS Transfer Family).

As a result, our workflow needs two extra Lambda steps: copy inputs from the
access point to a standard S3 bucket, and copy HealthOmics outputs from the
standard S3 bucket back to the access point.

## Requested behaviour

1. Output (higher priority): accept an FSx for ONTAP S3 Access Point alias,
   ARN, or virtual-hosted-style URI for --output-uri. Results would then be
   immediately visible to NFS and SMB users alongside the source data.

2. Input: accept an FSx for ONTAP S3 Access Point in run input parameters,
   including both the prefix form (trailing slash) and the sample sheet
   pattern. Retaining the existing staging behaviour - reading from the access
   point into the scratch volume - is fine for our use case.

3. Documentation: if implemented, please add HealthOmics to the integrated
   services list in the FSx for ONTAP user guide.

## Request 3 (added 2026-09-09): mounting a customer-owned file system

Separately from the S3 Access Point path above, we would like to ask about
attaching an FSx for ONTAP volume to a run over NFS.

We read the following in full on 2026-09-09 and could not find a documented
mechanism:

- Run storage is a temporary file system that the service provisions per run
  (DYNAMIC uses NFS, STATIC uses Lustre with capacities of 1,200 GiB or
  multiples of 2,400 GiB).
- The StartRun request body has no field for a customer-owned file system or a
  mount path. The storage-related fields are storageType, storageCapacity and
  scratchStorageMode, all of which select and size service-provided storage.
- Runs execute inside a HealthOmics-owned VPC that is not visible to customers.

We are NOT asserting that this is impossible - only that we could not find it
documented. Two points we would like confirmed:

  (a) With networkingMode: VPC, an NFS export in our VPC becomes reachable
      from the run. Is there a supported way to mount it into a task, either
      through the Configuration resource or in the workflow definition?
  (b) If not, can a task issue mount -t nfs itself (that is, does the task
      container have CAP_SYS_ADMIN)? We have not tested this.

If neither is supported, we would like to request, in order of preference:

  1. Allow a customer-owned file system to be specified as run storage - for
     example as an addition to the Configuration resource used by
     networkingMode: VPC, alongside a mount path.
  2. Allow it read-only, as an input location. Inputs are already staged
     read-only, so the semantic gap looks small.
  3. At minimum, state in the documentation that run storage is
     service-managed and that mounting a customer-owned file system is not
     supported. Today it is absent rather than stated, and the VPC networking
     page can be read as implying a mount path is possible because it lists
     "connect to AWS resources within your VPC" as a use case. We initially
     read it that way ourselves.

For context on why this matters here: AWS Batch (volumes / mountPoints on
EC2/ECS, or a CSI driver on EKS) and AWS Deadline Cloud customer-managed
fleets both let us mount the FSx for ONTAP file system directly, because the
host belongs to us. This is not a complaint about HealthOmics being managed -
we understand that is the trade-off - but it does mean the same genomics data
takes two different paths depending on which compute service runs it.

## Points we would like clarified

- SSE-FSX is the only server-side encryption mode on FSx for ONTAP S3 Access
  Points, whereas the HealthOmics service role is documented as requiring
  Amazon S3 and KMS permissions. If this encryption model difference is the
  blocker, we would like to understand that so we can document it accurately.
- If S3 Access Points in general (not only FSx-backed ones) are unsupported as
  run input/output, please confirm - that would be useful for customers using
  standard S3 access points as well.
- Whether networkingMode: VPC changes anything about which URI forms outputUri
  accepts. Our reading is that it does not (it affects reachability, not the
  bucket-name contract), and we would like to confirm that reading.

## Business impact

A single FASTQ sample can be tens of GB. The intermediate copy costs transfer
time and temporary storage, but the larger concern our customers raise is
governance: each additional copy of regulated data is another location to
access-control, apply retention to, and audit. In life sciences, keeping a
single authoritative copy is tied directly to audit requirements, so removing
the copy step has value beyond efficiency.

(To be clear, this is a statement about storage architecture, not a compliance
or legal assessment of any particular regulation.)

## References

- HealthOmics run inputs
  https://docs.aws.amazon.com/omics/latest/dev/workflows-run-inputs.html
- Start a run in HealthOmics
  https://docs.aws.amazon.com/omics/latest/dev/starting-a-run.html
- StartRun (HealthOmics API Reference)
  https://docs.aws.amazon.com/omics/latest/api/API_StartRun.html
- Run storage types in HealthOmics workflows
  https://docs.aws.amazon.com/omics/latest/dev/workflows-run-types.html
- Connecting HealthOmics workflows to a VPC
  https://docs.aws.amazon.com/omics/latest/dev/workflows-vpc-networking.html
- Using access points with AWS services (FSx for ONTAP User Guide)
  https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html
- Access point compatibility (FSx for ONTAP User Guide)
  https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html
- AWS HealthOmics is now available in two additional AWS Regions
  https://aws.amazon.com/about-aws/whats-new/2026/07/healthomics-tokyo-ohio/
- Public reference library (context for this request)
  https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns

If helpful, please share this with the Amazon FSx service team as well, since
the integration touches both services.
```

</details>

### 提出時のチェックリスト

- [ ] ケースを **サービス単位**で分割して起票（Lambda / HealthOmics。FR-8 は HealthOmics ケースの Request 3）
- [ ] Region を ap-northeast-1 と明記
- [ ] Category は Technical Support → General guidance（Feature request 相当）
- [ ] 「クォータ引き上げ要望ではない」ことを明示（Lambda ケース）
- [ ] 参照ドキュメントの URL を本文に含める
- [ ] 関連サービスチーム（Amazon FSx）への共有依頼を末尾に記載
- [ ] ケース番号・担当者名は本リポジトリにコミットしない（`.private/` で追跡）
- [ ] 提出後、本ドキュメントの **ステータス** 行を更新

---

## 参考文献

すべて AWS 公式ドキュメントまたは AWS 公式アナウンスです（2026-08-02 アクセス）:

1. [AWS Lambda がセルフマネージド型のコードストレージを発表 — What's New](https://aws.amazon.com/jp/about-aws/whats-new/2026/07/lambda-self-managed-code-storage/)
2. [Self-managed S3 code storage — AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/configuration-self-managed-storage.html)
3. [AWS::Lambda::Function Code — CloudFormation Template Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-lambda-function-code.html)
4. [AWS HealthOmics がさらに 2 つの AWS リージョンで利用可能に — What's New](https://aws.amazon.com/jp/about-aws/whats-new/2026/07/healthomics-tokyo-ohio/)
5. [HealthOmics run inputs — AWS HealthOmics Developer Guide](https://docs.aws.amazon.com/omics/latest/dev/workflows-run-inputs.html)
6. [Start a run in HealthOmics — AWS HealthOmics Developer Guide](https://docs.aws.amazon.com/omics/latest/dev/starting-a-run.html)
7. [Access point compatibility — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
8. [Accessing your data via Amazon S3 access points — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
9. [Using access points with AWS services — FSx for ONTAP User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)

FR-8 の追加にあたって参照したもの（いずれも 2026-09-09 に全文確認）:

10. [StartRun — AWS HealthOmics API Reference](https://docs.aws.amazon.com/omics/latest/api/API_StartRun.html)
11. [Run storage types in HealthOmics workflows — AWS HealthOmics Developer Guide](https://docs.aws.amazon.com/omics/latest/dev/workflows-run-types.html)
12. [Connecting HealthOmics workflows to a VPC — AWS HealthOmics Developer Guide](https://docs.aws.amazon.com/omics/latest/dev/workflows-vpc-networking.html)

---

## Appendix: 回避策アーキテクチャ

### FR-6 回避策（HealthOmics 併用パターン）

```
┌──────────────────────────────┐
│ FSx for ONTAP volume         │
│  FASTQ / BAM / VCF           │
│  (NFS/SMB でシーケンサーが書込) │
└──────────┬───────────────────┘
           │ S3 AP: ListObjectsV2 / GetObject  ✅ 対応済
           ▼
┌──────────────────────────────┐
│ Stage Lambda                 │
│  S3 AP → 標準 S3 へコピー      │  ◀── FR-6 で削除できるステップ
└──────────┬───────────────────┘
           ▼
┌──────────────────────────────┐
│ 標準 S3 バケット（入力用）      │
└──────────┬───────────────────┘
           │ omics:StartRun --parameters
           ▼
┌──────────────────────────────┐
│ AWS HealthOmics              │
│  Nextflow / WDL / CWL        │
│  （東京リージョンで実行可能）    │
└──────────┬───────────────────┘
           │ --output-uri（標準 S3 必須）
           ▼
┌──────────────────────────────┐
│ 標準 S3 バケット（出力用）      │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ Writeback Lambda             │
│  標準 S3 → S3 AP へ書き戻し    │  ◀── FR-6 で削除できるステップ
└──────────┬───────────────────┘
           ▼
    NFS/SMB 利用者が解析結果を
    ソースデータの隣で参照できる
```

FR-6 の出力側だけが実現した場合、Writeback Lambda（下側のコピー）が不要になります。入力側も実現すれば Stage Lambda も不要になり、`StartRun` を呼ぶだけの構成になります。

### FR-5 回避策（Lambda コードストレージ）

```
┌──────────────────────────────┐
│ FSx for ONTAP volume         │
│  ビルド成果物 .zip             │
│  (NFS/SMB でビルドサーバが書込) │
└──────────┬───────────────────┘
           │ S3 AP: GetObject  ✅ 対応済
           ▼
┌──────────────────────────────┐
│ 標準 S3 バケット               │
│  バージョニング有効（必須）      │  ◀── FR-5 で不要になる中継
└──────────┬───────────────────┘
           │ S3ObjectStorageMode: REFERENCE
           │ + S3ObjectVersion
           ▼
┌──────────────────────────────┐
│ Lambda 関数 / レイヤー         │
└──────────────────────────────┘
```
