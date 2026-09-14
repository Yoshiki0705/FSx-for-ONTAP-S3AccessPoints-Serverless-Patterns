# はじめての 1 回を、前提の確認から撤収まで通す順序

🌐 **Language / 言語**: 日本語 | [English](../en/start-here.md)

このリポジトリには 50 以上のパターンと 40 以上のドキュメントがあり、どれも独立してデプロイできます。そのぶん「どれから読むか」が決まっていません。このページはそれだけを決めます。**本文は持たず、各段で読むものと打つコマンドを指すだけ**です。既存のガイドを置き換えるものではありません。

所要時間の目安は、デモモードで **45 分**、既存の FSx for ONTAP に対して **2〜3 時間**（VPC Endpoint の作成待ちを含む）。

## FSx for ONTAP と決まっていない場合

ここから始めないでください。このリポジトリは**ストレージが FSx for ONTAP に決まったあと**の実装を扱います。手前の判断には別のリポジトリがあります。

| 状態 | 行き先 |
|---|---|
| ストレージの選択がまだ | [FSx for ONTAP Adoption Playbook — ファイルストレージ選択の決定木](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/decision-trees/file-storage-selection.md)（7 つの終端のうち 4 つは FSx for ONTAP 以外に落ちます） |
| 移行方式を決めたい | [同 — 移行方式の決定木](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/decision-trees/migration-method.md) |
| 既存の SaaS / オンプレ / 他クラウドから移す前提で見たい | [SaaS / クラウドストレージからの移行とデータ連携](saas-to-fsx-ontap-migration.md) |
| S3 Access Point 以外の方式と比べたい | [代替アーキテクチャ比較（S3 AP / EFS / NFS / DataSync）](../comparison-alternatives.md) |

決まっている場合は次へ進みます。

## 第 1 段 — 前提の確認

**環境が整っているかを、デプロイを始める前に判定します。**

```bash
make preflight                                                  # 資格情報、リージョン、ツール、Bedrock
make preflight PROFILE=production VPC=vpc-0123456789abcdef0     # 加えて VPC Endpoint 競合、ONTAP S3、secrets
```

プロファイルは 4 つ（`quick-start` / `production` / `demo` / `fpolicy`）。終了コードは **75 がツール不足、78 が環境の未準備**で、いずれも 1 とは区別されます。「何をインストールするか」と「何を直すか」は別の作業なので分けてあります。

FSx for ONTAP のファイルシステムを用意する前に試す場合は、この段を飛ばして [デモモードガイド](../demo-mode-guide.md) に進めます。DemoMode は通常の S3 バケットで代替します。

- 前提条件の一覧: [デプロイガイド — 前提条件](deployment-guide.md#前提条件)
- 手元の環境が満たしているかの確認手順: [同 — 既存リソース ID の取得方法](deployment-guide.md#パラメータマッピング)

## 第 2 段 — 自分の環境の値へのパラメータ差し替え

**ここが初見で最も時間を取る段です。** 値を推測せず、AWS から引いてください。

```bash
make discover-s3ap                       # アカウント内の S3 Access Point を FSx API から列挙
make discover-s3ap REGIONS=us-east-1     # 別リージョン
```

`make discover-s3ap` は手書きの一覧ではなく FSx API から引くので、削除済みや `MISCONFIGURED` の Access Point が設定ファイルの中で正しく見え続けることがありません。

| 用意するもの | 参照先 |
|---|---|
| パターンごとの設定ファイル | 各パターンの `samconfig.toml.example` をコピーして値を入れる |
| シナリオ別のパラメータ例 | [`cfn-params/`](../../cfn-params/)（5 シナリオ + README） |
| 環境別のパラメータ | [`params/`](../../params/) |
| ポータルの設定 | [`portal-config.example.ts`](../../solutions/amplify-portal/amplify/portal-config.example.ts) — **全項目に、値を調べる CLI コマンドと対応する `AMPLIFY_PORTAL_*` 環境変数が書いてあります** |
| VPC Endpoint が既存スタックと衝突しないか | [デプロイガイド — VPC Endpoint 競合マトリクス](deployment-guide.md#vpc-endpoint-競合マトリクス) |
| 既存の構成の値をどのパラメータに入れるか | [移行ガイド](saas-to-fsx-ontap-migration.md) |

> **S3 Access Point の IAM に関する補足**: Access Point をバケット形式（`arn:aws:s3:::<エイリアス>/*`）だけで指定したポリシーは**デプロイに成功し `CREATE_COMPLETE` を返したうえで、list・get・put のすべてを拒否します**。Access Point 形式（`arn:aws:s3:<リージョン>:<アカウント>:accesspoint/<名前>` と `…/object/*`）が必要です。既存のテンプレートは両形式を持っており、`make drift` が全 80 テンプレートを検査します。

## 第 3 段 — デプロイ

```bash
make build-uc1 && make deploy-uc1        # パターン番号を差し替える
```

- 手順の詳細: [デプロイガイド（段階手順）](../guides/deployment-guide.md)
- どのパターンを選ぶか: [パターン選択ガイド](../pattern-selection-guide.md)
- 検証済みのデプロイ経路と所要時間: [デプロイガイド — 検証済みデプロイパス](deployment-guide.md#検証済みデプロイパス)
- コスト: [コスト計算](../cost-calculator.md)。FSx for ONTAP、NAT Gateway、Interface VPC Endpoint が主な費用です

## 第 4 段 — 動いていることの確認

**`CREATE_COMPLETE` は「デプロイできた」であって「動く」ではありません。**

```bash
make smoke STACK=fsxn-s3ap-legal-compliance
make smoke STACK=... ARGS='--list-prefix reports/ --read-only'
```

スタック名から Access Point を解決し、一覧 → 読み取り → 書き込み → **読み戻し** → **一覧に現れるかの確認** → 削除を通します。後ろ 2 つを分けているのは、**書き込みが 200 を返すことと、次の読み手にそれが見えることが別の主張**だからです。ポータルの利用者が経験するのは後者です。

この分離は実測から来ています。ローカルのテストは、空から始まるモックに対してアップロードの往復を pass しました。その同じビルドの IAM ポリシーは Access Point に到達できないものでした。**緑のローカルスイートは到達性について何も述べません。**

- Step Functions の実行と結果確認: [デプロイガイド — 動作確認](../guides/deployment-guide.md#5-動作確認)
- ポータルを配る前の確認: `make portal-preflight`（**開けることはサインインできる証拠ではありません**）

## 第 5 段 — 撤収

**検証環境を残したままにしないでください。** 特に NAT Gateway と Interface VPC Endpoint は使っていなくても課金されます。

```bash
make propose-cleanup                                              # 何が立っていて幾らかかるか（削除しない）
aws cloudformation delete-stack --stack-name <スタック名>
make cleanup-stacks                                               # DELETE_FAILED の修復
make cleanup-retained ARGS='--stack-prefix fsxn-s3ap-uc1'         # 削除後に生き残ったもの（報告のみ）
make cleanup-retained ARGS='--stack-prefix fsxn-s3ap-uc1 --apply' # 実際に消す
```

スタックの削除が成功しても、**ロググループ（関数が初回呼び出しで作るのでテンプレートに存在しません）、削除保護つきのテーブル、`Retain` の User Pool** は残ります。`make cleanup-retained` はそれぞれについて「なぜ生き残ったか」と「消すと何が失われるか」を出し、既定では何も変更しません。`--apply` は、その prefix に一致するスタックがまだ存在する間は拒否されます。

**触らないもの**: FSx for ONTAP のボリューム / SVM / ファイルシステム、SnapLock と WORM のデータ、S3 バケットと Object Lock、Secrets Manager。保持ロックは残骸ではなく設定どおり動いている状態です [E-008]。

- 手順の全体: [ポータルのクリーンアップガイド](../../solutions/amplify-portal/docs/cleanup-guide.md)
- 削除できない条件: [デプロイガイド](deployment-guide.md) の「ロールバック・クリーンアップ」

> **不可逆操作に関する補足**: SnapLock ボリュームの作成、SnapLock 監査ログボリュームの作成、スナップショットのロック、S3 Object Lock の `COMPLIANCE` は、いずれも取り消せません。**監査ログボリュームはボリューム・SVM・ファイルシステムの削除を保持期間が満了するまでブロックし、最短は 6 か月です** [E-008]。検証環境こそ置いてはいけない場所です。詳細は [SnapLock の罠](../agent/pitfalls-snaplock.md)。

## 本番に持っていく前に

| 観点 | 参照先 |
|---|---|
| PoC から本番への段階 | [PoC から本番へ](portal-poc-to-production.md) |
| デプロイプロファイル | [デプロイプロファイル](../deployment-profiles.md) |
| 監査・コンプライアンス | [コンプライアンスガイド](portal-compliance-guide.md) |
| データ分類と Human Review の閾値 | [データ分類](../guides/data-classification.md) |
| 障害時に何が起きるか | [インシデント対応](../incident-response-playbook.md) |
| 設計上の考慮点 | [設計考慮事項](../design-considerations.md) |

## 関連ドキュメント

- [ドキュメント索引](../index.md) — 全ドキュメントの一覧
- [クイックスタート](../quick-start.md) — 最短経路だけを見たい場合
- [デモモードガイド](../demo-mode-guide.md) — FSx for ONTAP なしで試す
- [FSx for ONTAP の管理インターフェース](fsx-ontap-management-interfaces.md) — 到達可能な管理経路の整理
