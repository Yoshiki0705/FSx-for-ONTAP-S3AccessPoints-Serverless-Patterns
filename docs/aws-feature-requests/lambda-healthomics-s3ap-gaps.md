# 機能要望: Lambda セルフマネージドコードストレージ / AWS HealthOmics と FSx for ONTAP S3 Access Points の統合

> 🌐 言語: **日本語** | [English](./lambda-healthomics-s3ap-gaps.en.md)

**提出者**: 藤原 慶樹 (AWS Community Builder)
**日付**: 2026-08-02
**プロジェクト**: [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
**コンテキスト**: 2026-07 の 2 リリース（Lambda セルフマネージドコードストレージ / AWS HealthOmics 東京リージョン対応）を本プロジェクトのワークフローへ組み込む可否評価
**ステータス**: **✅ 2026-08-02 に AWS Support へ提出済み**（サービス単位で 2 ケース: Lambda（FR-5 + FR-7）/ HealthOmics（FR-6））。ケース番号は本リポジトリには記載しません（`.private/` で追跡）。
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
| 標準 S3 バケット経由での組み込み | ✅ 可能 | ✅ 可能 |
| CloudFormation（`AWS::Lambda::Function`）対応 | ✅ `Code.S3ObjectStorageMode` あり | — |
| AWS SAM（`AWS::Serverless::Function`）対応 | ⚠️ **未確認** — SAM リソースリファレンスに該当プロパティの記載を確認できず | — |
| 本プロジェクトへの適用推奨度 | △ 条件付き（FR-7 の解決待ち） | ○ 新パターンとして成立 |

---

## FR-5: Lambda セルフマネージドコードストレージで FSx for ONTAP S3 AP を参照可能にする

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

## FR-6: AWS HealthOmics の入出力に FSx for ONTAP S3 AP を指定可能にする

### 現状

HealthOmics のワークフロー実行は、入力・出力の双方で Amazon S3 URI を前提としています。

[HealthOmics run inputs](https://docs.aws.amazon.com/omics/latest/dev/workflows-run-inputs.html) によれば、ワークフロー定義が入力ファイルを指定している場合、HealthOmics は実行専用の scratch ボリュームへファイルを**ステージング**し、それらは読み取り専用となります。入力パラメータは単一オブジェクトのキー、末尾スラッシュによるプレフィックス、Nextflow では glob パターンとして解釈されます。

[Start a run in HealthOmics](https://docs.aws.amazon.com/omics/latest/dev/starting-a-run.html) によれば、出力先は `s3://bucket/prefix/object` 形式の Amazon S3 ロケーションを必須設定として指定します。またサービスロールには Amazon S3 と KMS に対する権限が必要とされています。

*上記は AWS 公式ドキュメントの内容をライセンス上の制約に配慮して要約したものです。*

加えて、[Using access points with AWS services（FSx for ONTAP ユーザーガイド）](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html) が統合例として挙げているサービスは Athena、Lambda、AWS Glue、Amazon Bedrock Knowledge Bases、Amazon EMR Serverless、CloudFront、AWS Transfer Family であり、**AWS HealthOmics は含まれていません**。

以上から、FSx for ONTAP S3 AP を HealthOmics の入力元・出力先として使うことは現時点で未サポートと判断します。技術的な懸念点は 2 つです:

1. **ステージング（コピー）が設計に組み込まれている** — 入力は scratch ボリュームへコピーされるため、仮に S3 AP URI を受け付けたとしても「データを動かさない」という価値の一部は得られません。ただしコピー先が実行専用の一時領域である点は、恒久的な二重保管とは性質が異なります。
2. **暗号化モデルの差異** — HealthOmics は S3 と KMS に対する権限を前提としますが、FSx for ONTAP S3 AP は SSE-FSX が唯一のサーバーサイド暗号化モードです（[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)）。サービスロールの権限設計に差異が生じます。

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

## FR-7: AWS SAM で `S3ObjectStorageMode` を指定可能にする

### 現状

`S3ObjectStorageMode` は [`AWS::Lambda::Function` の `Code` プロパティ](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-lambda-function-code.html)に `COPY | REFERENCE` の許可値を持つプロパティとして文書化されています。一方 `AWS::Serverless::Function` / `AWS::Serverless::LayerVersion` は `CodeUri` / `ContentUri`（ローカルパスまたは S3 URI）のみを公開しており、SAM リソースリファレンスに該当プロパティの記載を確認できませんでした。

> **検証状況の更新（2026-08）**: 当初この項目は公開ドキュメントのみに基づく推定でした。その後 AWS サポートが実機で再現し、SAM が当該プロパティを警告なく破棄することを確認しています。詳細は下記「AWS サポートによる確認結果」を参照してください。

### AWS サポートによる確認結果（2026-08）

AWS サポートが検証環境で再現し、以下を確認しました。当初の「ドキュメントに記載が見つからない」という推定から、**実機で確認された挙動**に格上げされています。

| 確認事項 | 結果 |
|---------|------|
| `AWS::Serverless::Function` の `CodeUri` に `S3ObjectStorageMode: REFERENCE` を指定 | `sam validate` / `sam deploy` は**エラーなく成功する** |
| 実際に作成される関数のモード | SAM 変換時にプロパティが**警告なく破棄**され、既定の `COPY` モードで作成される |
| SAM の `S3Location` 型が受け付けるプロパティ | `Bucket` / `Key` / `Version` のみ。それ以外は変換時に破棄される（`S3ObjectStorageMode` 固有の問題ではない） |
| Lambda 開発者ガイドが挙げる利用手段 | コンソール / AWS CLI / CloudFormation。**AWS SAM は記載されていない** |
| `update-function-code` のドリフト | 確認済み。`S3ObjectStorageMode` は毎回指定が必要で、省略すると `COPY` に戻る |

> ⚠️ **実務上の意味**: `sam deploy` が成功しても `REFERENCE` モードは適用されていないため、**デプロイ結果からは適用漏れに気づけません**。`REFERENCE` モードを前提にする場合は、デプロイ後に実際のモードを確認する手順が必要です。

Inactive 状態の結合（Lambda がソースオブジェクトを定期的に再読み込みし、アクセスできなくなると関数を Inactive に遷移させる）についても確認が取れました。ただし AWS サポートからは「**これが FSx for ONTAP S3 AP 非対応の理由であるという確認は取れていない**」と明示されているため、本ドキュメントでも原因として断定しません。

AWS サポート側では、Lambda サービスチームへの機能リクエスト、SAM チームへのバグ報告（`AWS::Serverless::Function` / `AWS::Serverless::LayerVersion` への `S3ObjectStorageMode` 追加）、および未知のプロパティを警告なく破棄せずバリデーションエラーとすべき旨のフィードバックが起票されています。公開追跡先（GitHub issue 等）の有無は照会中です。

### 本プロジェクトへの影響

本リポジトリの全パターンは SAM（`AWS::Serverless::Function` + ローカル `CodeUri`）でパッケージングされ、`sam build` / `sam deploy` が成果物のアップロードを管理しています。`S3ObjectStorageMode` を SAM で指定できない場合、`REFERENCE` モードを採用するには以下のいずれかが必要です:

- 全テンプレートを `AWS::Lambda::Function` へ書き換える（SAM の簡潔さと `Policies` 短縮記法を失う）
- `sam deploy` 後に `update-function-code` を追加実行する（`S3ObjectStorageMode` は毎回明示が必要なため、CloudFormation の状態管理と乖離するリスクがある）

どちらもリポジトリ全体のパッケージング規約の変更となり、37 テンプレートに影響します。そのため本プロジェクトでは FR-7 の解決を待つ判断としました。

### 要望する挙動

`AWS::Serverless::Function` および `AWS::Serverless::LayerVersion` で `S3ObjectStorageMode`（または同等の SAM 側プロパティ）をサポートし、`sam deploy` が管理する成果物バケットに対して `REFERENCE` モードを選択できるようにする。加えて、`sam deploy` の成果物バケットでバージョニングを自動有効化するか、未有効時に明確なエラーを返すことを期待します。

### 本プロジェクトでの回避策

なし（`COPY` モードのまま運用）。

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

既提出の FR-1〜FR-4 との統合優先順位では、**FR-2（イベント通知） > FR-6 > FR-1 > FR-7 > FR-3 > FR-4 ≈ FR-5** と考えています。FR-4（Versioning）と FR-5 が連動する点は、FR-4 のビジネスケースを補強する材料としてご参照ください。

---

## ビジネスケース

- **リージョン整合が揃った意味**: FSx for ONTAP S3 AP と HealthOmics が同一リージョン（ap-northeast-1）で利用可能になったため、日本のライフサイエンス導入先にとって「ゲノムデータは国内のファイルシステムに置き、解析も国内で実行する」構成が初めて成立しました。データ所在地要件が厳しい研究機関・製薬企業にとって、この整合は導入判断の前提条件です。残る障壁がデータ経路のみであることは、FR-6 の投資対効果が高いことを意味します。
- **コピーステップの累積コスト**: 本プロジェクトの既提出 FR で述べたとおり、PoC では通常 2〜3 個の標準 S3 バケットが必要になります。HealthOmics を加えると、入力ステージング用と出力受け取り用でさらに増えます。バケット数の増加はコストよりもガバナンス上の負荷（アクセス制御・保持ポリシー・監査ログの管理対象の増加）として顕在化します。
- **既存パターンの前提が変わる**: 37 テンプレートという規模は、パッケージング規約の変更コストが個別パターン単位では収まらないことを示します。FR-7 が解決すれば規約変更は 1 回で済み、解決しなければ採用を見送るという二者択一になります。

> **コストに関する補足**: 本節の数値はリポジトリ内のテンプレート実数（37 テンプレートが SharedLayer を定義）に基づく静的な集計です。特定導入先環境での実測値や本番規模の見積りではありません。

---

## AWS Support 提出用テキスト

以下は AWS Support ケース（Technical Support → Service: 該当サービス → Category: General guidance / Feature request）へそのまま貼り付ける想定の本文です。ケースは **サービス単位で分割**して起票します（FR-5・FR-7 は Lambda、FR-6 は HealthOmics）。FSx for ONTAP S3 AP 側の対応が必要な要望であることを本文で明示し、可能であれば Amazon FSx サービスチームへの共有を依頼します。

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
Subject: Feature request - HealthOmics: accept FSx for ONTAP S3 Access Points as run input and output

Category: General guidance / Feature request
Service: AWS HealthOmics
Region: ap-northeast-1

## Summary

Please allow AWS HealthOmics private workflow runs to use an Amazon FSx for
NetApp ONTAP S3 Access Point as the run input location and, with higher
priority, as the run output location (--output-uri).

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

## Points we would like clarified

- SSE-FSX is the only server-side encryption mode on FSx for ONTAP S3 Access
  Points, whereas the HealthOmics service role is documented as requiring
  Amazon S3 and KMS permissions. If this encryption model difference is the
  blocker, we would like to understand that so we can document it accurately.
- If S3 Access Points in general (not only FSx-backed ones) are unsupported as
  run input/output, please confirm - that would be useful for customers using
  standard S3 access points as well.

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

- [ ] ケースを **サービス単位**で分割して起票（Lambda / HealthOmics）
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
