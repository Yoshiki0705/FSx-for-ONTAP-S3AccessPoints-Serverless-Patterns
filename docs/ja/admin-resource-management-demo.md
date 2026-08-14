# 管理者向けリソース管理 — デモガイド

🌐 **Language / 言語**: **日本語** | [English](../en/admin-resource-management-demo.md)

[English](../en/admin-resource-management-demo.md) | **日本語**

> FSx for ONTAP（fs-0123456789abcdef1、ONTAP 9.17.1）に対して 2026-07-26 に E2E 検証済み

## 概要

**Admin > Resources** セクションは、ONTAP System Manager 相当のストレージ管理をファイルポータルの Web UI から提供します。すべての操作は VPC 内 Lambda 経由で ONTAP REST API を呼び出して実行されます。

**アーキテクチャ**: ブラウザ → AppSync（Cognito 認証）→ Lambda（VPC）→ ONTAP REST API（管理 LIF）

## 前提条件

| 項目 | 値 |
|------|-----|
| Cognito グループ | `storage-admin`（すべての管理操作に必須） |
| Lambda の VPC | FSx for ONTAP ファイルシステムと同一 VPC |
| シークレット | `fsx-ontap-fsxadmin-credentials`（username/password の JSON） |
| ONTAP バージョン | 9.13.1 以降（ARP/AI は 9.16 以降） |

## クイックスタート（デプロイ）

```bash
cd solutions/amplify-portal

# 1. 設定ファイルをコピーして編集（gitignore 済み）
cp amplify/portal-config.example.ts amplify/portal-config.ts
# portal-config.ts に自身の値を設定:
#   ontapMgmtIp, ontapSecretName, ontapSvmName, ontapVolumeName
#   vpcId, vpcSubnetIds, vpcSecurityGroupIds

# 2. バックエンドとフロントエンドを一括起動
npm start
# 別々に起動する場合:
#   ターミナル 1: npx ampx sandbox
#   ターミナル 2: npm run dev
```

### 設定値の調べ方

```bash
# ファイルシステムの管理 IP と VPC 情報
FS_ID="fs-xxxxxxxxxxxxxxxxx"
aws fsx describe-file-systems --file-system-ids $FS_ID \
  --query "FileSystems[0].{VpcId:VpcId,SubnetIds:SubnetIds,MgmtIP:OntapConfiguration.Endpoints.Management.IpAddresses[0]}"

# FSx の ENI からセキュリティグループを取得
aws ec2 describe-network-interfaces \
  --filters "Name=description,Values=*FSx*${FS_ID}*" \
  --query "NetworkInterfaces[0].Groups[0].GroupId" --output text

# SVM 名
aws fsx describe-storage-virtual-machines \
  --filters "Name=file-system-id,Values=$FS_ID" \
  --query "StorageVirtualMachines[].Name" --output text
```

## パネル一覧

### Storage カテゴリ

| パネル | 説明 | ONTAP REST エンドポイント |
|-------|------|---------------------------|
| **Volumes** | ボリュームの作成・リサイズ・削除、容量の可視化 | `/storage/volumes` |
| **FlexClone** | ゼロコピークローンの作成・一覧・スプリット | `/storage/volumes`（clone フィールド） |
| **Qtrees** | ボリューム内のディレクトリ構造管理 | `/storage/qtrees` |
| **Quotas** | ユーザー / ツリー / グループ単位の容量・ファイル数制限 | `/storage/quota/rules`, `/storage/quota/reports` |
| **Storage Efficiency** | 重複排除・圧縮・削減率のダッシュボード | `/storage/volumes?fields=efficiency,space` |

### Access Control カテゴリ

| パネル | 説明 | ONTAP REST エンドポイント |
|-------|------|---------------------------|
| **Export Policies** | NFS アクセスルール（クライアント、ro/rw、superuser） | `/protocols/nfs/export-policies` |
| **SMB Shares** | CIFS/SMB 共有フォルダーの管理 | `/protocols/cifs/shares` |
| **Local Users** | SMB ローカルユーザー / グループの作成・一覧・削除・メンバー管理 | `/protocols/cifs/local-users`, `/protocols/cifs/local-groups` |
| **Name Mapping** | Windows ↔ UNIX/S3 のユーザー名変換ルール | `/name-services/name-mappings` |
| **QoS Policies** | Fixed（最大 IOPS/MBps）と Adaptive（expected/peak） | `/storage/qos/policies` |

### Data Protection カテゴリ

| パネル | 説明 | ONTAP REST エンドポイント |
|-------|------|---------------------------|
| **ARP/AI Protection** | ボリュームごとのランサムウェア対策状態、一括有効化 | `/storage/volumes?fields=anti_ransomware` |
| **Snapshot Management** | ポリシー、スケジュール、改ざん防止ロック | `/storage/snapshot-policies`, `/storage/volumes/{id}/snapshots` |
| **SnapLock** | WORM 保持設定（Compliance / Enterprise） | `/storage/volumes?fields=snaplock` |
| **FPolicy** | ファイルアクセスイベント通知と監査設定 | `/protocols/fpolicy` |
| **Vscan** | オンアクセスウイルススキャンの設定とベンダー案内 | `/protocols/vscan` |
| **SnapMirror** | レプリケーション運用（同期、ブレーク、再同期、一時停止、削除）と転送履歴 | `/snapmirror/relationships`, `/snapmirror/relationships/{id}/transfers` |
| **FlexCache** | キャッシュボリュームの作成（非同期）・一覧・削除（3 段階自動）、write-back の切り替え、オリジンの可視化 | `/storage/flexcache/flexcaches` |

## デモシナリオ

### シナリオ 1: ボリュームのライフサイクル

1. **Admin > Resources > Volumes** を開く
2. **+ Create Volume** をクリック → 名前: `demo_vol_01`、サイズ: 50 GiB、スタイル: UNIX
3. 容量バーが 0% の新しいボリュームが一覧に表示されることを確認
4. **↔**（リサイズ）→ 100 GiB を入力 → 確定
5. **✕**（削除）→ 削除を確認

### シナリオ 2: ARP/AI の一括有効化

1. **Admin > Resources > ARP/AI Protection** を開く
2. サマリーカード（Enabled / Learning / Disabled の件数）を確認
3. **Bulk Enable** → 「ARP/AI（学習期間なし）」を選択
4. 確定 → 無効だったボリュームがすべて "enabled" に遷移
5. サマリーが全ボリューム保護済みに更新されることを確認

### シナリオ 3: ストレージ効率ダッシュボード

1. **Admin > Resources > Storage Efficiency** を開く
2. 全体の削減率（例: 1.21x）と削減割合（17.7%）を確認
3. 表でボリュームごとの重複排除 / 圧縮の状態を確認
4. 効率化機能が有効になっていないボリュームを特定

### シナリオ 4: Snapshot の改ざん防止ロック

> ⚠️ **不可逆な操作**: ボリュームで Snapshot ロックを有効化すると解除できません。保持期間を設定して Snapshot をロックすると、期間は延長のみ可能で短縮はできません。実行前に組織の保持ポリシーを確認してください。

1. **Admin > Resources > Snapshot Management** を開く
2. **Tamperproof** タブに切り替える
3. ボリューム UUID を入力 → **Check Status** をクリック
4. ロックが無効なら **Enable Snapshot Locking** をクリック
5. **Data Protection > Snapshots** で Snapshot の **🔒 Lock** をクリック
6. 保持日数（例: 30）を設定 → 確定 → Snapshot が変更不可になる

### シナリオ 5: ARP/AI のインシデント対応

1. **Data Protection > ARP/AI** を開く
2. 脅威が検出されている場合（attackProbability が "none" 以外）、脅威評価のバナーを確認
3. **Incident Response** セクションで:
   - ドメイン + ユーザー名を入力 → **🛡️ Contain Threat** をクリック
   - Snapshot 作成、SMB ユーザーのブロック、セッション切断がまとめて実行される
4. **Active Blocks** タブで現在のブロックを確認
5. 調査完了後、**Unblock** で隔離を解除

### シナリオ 6: SMB 共有の暗号化管理

1. **Admin > Resources > SMB Shares** を開く
2. KMS による保存時暗号化と SMB の転送時暗号化の違いを説明するメッセージを確認
3. **ℹ️ CA 共有 (Continuously Available) とは？** を展開して Hyper-V / SQL Server 向けの説明を読む
4. 暗号化が「— 任意」の共有で **ON** をクリック → 暗号化が有効になる
5. **OFF** で無効化 → 「— 任意」に戻ることを確認
6. **共有削除** → 自然言語の確認ダイアログ「『testshare01』を本当に削除しますか？」

### シナリオ 7: エクスポートポリシーの作成と削除

1. **Admin > Resources > Export Policies** を開く
2. **+ ポリシー作成** → 名前 `demo_readonly_policy` を入力 → 作成
3. ルール 0 件の新しいポリシーが表示されることを確認
4. **ルール表示** → ルールを追加（クライアント: 10.0.0.0/16、RO: sys、RW: none）
5. **← 一覧に戻る** → `demo_readonly_policy` の **✕** → 削除を確認

### シナリオ 8: Lock パネルのインライン管理

1. **Data Protection > Lock** を開く
2. **SnapLock タブ**: インラインのボリューム一覧を確認（SnapLock ボリュームがなければ空）
3. **S3 Object Lock タブ**: ONTAP 接続エラーなしで描画されることを確認
4. **Tamperproof タブ**: Snapshot ロックが有効なら、インラインのロックフォームを確認
   - Snapshot 選択ドロップダウン（未ロックのもの）
   - 保持期間ドロップダウン（1 日 〜 5 年）
   - ロックボタン

### シナリオ 9: VolumeSelector の検索（大規模環境での絞り込み）

1. **Admin > Resources > Qtrees** を開く
2. 上部の検索入力付き VolumeSelector を確認
3. ボリューム名の一部（例: "cache"）を検索欄に入力
4. 300ms のデバウンス後、ドロップダウンが一致するボリュームのみに絞られる
5. ボリュームを選択 → そのボリュームの qtree が読み込まれる

### シナリオ 10: FlexClone — 瞬時のボリュームコピー

1. **Admin > Resources > FlexClone** を開く
2. 既存クローン（あれば）と親ボリューム、スプリット状態を確認
3. **+ Create Clone** → 入力:
   - クローン名: `clone_dev_test`
   - 親ボリューム: `vol_production`
   - Snapshot（任意）: 空欄なら現在の状態、または Snapshot 名を指定
4. **Create** → 新しいクローンが即座に表示される（メタデータのみのコピー）
5. クローンの **Split** → 確定 → スプリットが開始（バックグラウンド処理）
6. スプリットの進捗率が更新されることを確認

> **補足**: FlexClone は親ボリュームのスループット枠を共有します。開発 / テストやフォレンジック用途に向き、恒久的な並列ワークロードには向きません。

### シナリオ 11: Vscan — ウイルス対策のセットアップ案内（DemoMode）

1. **Admin > Resources > Vscan** を開く
2. Vscan が未設定のため、5 ステップのセットアップ案内が表示される:
   - **Step 1**: ベンダー選択表（6 ベンダー、ライセンスリンク付き）
   - **Step 2**: NetApp Antivirus Connector のダウンロードボタン
   - **Step 3**: EC2 構成図と AWS Blog / GitHub リンク
   - **Step 4**: ONTAP CLI コマンド（scanner-pool、policy、enable）
   - **Step 5**: このパネルに戻って確認
3. ベンダーリンクをクリック → 正しい外部ページが開くことを確認
4. Antivirus Connector のダウンロードボタン → mysupport.netapp.com が開くことを確認
5. 本番で Vscan を設定した後は、オンアクセスポリシーの詳細が表示される

### シナリオ 12: SnapMirror — レプリケーションの運用管理

> ⚠️ **破壊的な操作**: ブレークはレプリケーション関係を切断します。ブレーク後は宛先ボリュームが書き込み可能になりますが、再同期には差分転送が必要で、宛先側の変更は上書きされます。再同期は宛先の変更をすべて破棄します。どちらも UI で明示的な確認を求めます。

1. **Admin > Resources > SnapMirror** を開く
2. レプリケーション関係がソース → 宛先のカードとして表示されることを確認:
   - ソースパスのバッジ: `📦 svm01:vol_production`
   - 矢印: `→`
   - 宛先パスのバッジ: `🪞 svm01_dr:vol_production_mirror`
3. 各関係に表示される情報:
   - **ヘルスバッジ**: 正常（緑）/ 異常（赤）
   - **状態バッジ**（色分け）:
     - ✅ 同期中 (snapmirrored) — 緑
     - 🔴 ブレーク済み (broken_off) — 赤
     - 🔄 転送中 (transferring) — 青
     - ⏸️ 一時停止 (quiesced/paused) — グレー
     - ⚪ 未初期化 (uninitialized) — 白
   - **ラグ時間** と RPO 警告: ラグに "hour" または "day" が含まれる場合、赤太字で `⚠️ RPO` を表示
   - **ポリシー**: 例 MirrorAllSnapshots、Asynchronous
4. **操作ボタン**（状態に応じて変化）:
   - `snapmirrored`: [🔄 同期] [⏸️ 一時停止] [⚡ ブレーク] [🗑️ 削除]
   - `broken_off`: [🔁 再同期] [🗑️ 削除]
   - `paused`: [▶️ 再開] [🗑️ 削除]
5. **🔄 同期** → 確認ダイアログ → 手動転送が開始
6. **⚡ ブレーク** → 確認（「フェイルオーバーに使用します」と警告）→ 宛先が書き込み可能になる
7. **🔁 再同期** → 確認（「宛先の変更は破棄されます」と警告）→ 関係が復帰
8. 関係の **▶ 転送履歴** → 転送履歴の表を展開:
   - 列: 状態（success/failed バッジ）、サイズ（整形済みバイト）、完了日時、所要時間、操作
   - 直近 10 件を表示
   - 進行中の転送（転送中 / キュー / 準備中 / 最終処理中）には **⏹ 転送を中止** ボタンが出る。中止しても差分は次回の更新で再送される
9. **▼** で転送詳細を折りたたむ

> **RPO の監視**: ラグ時間が RPO 目標（例: 2 時間）を超えると、赤い `⚠️ RPO` 警告がレプリケーションの遅延を示します。手動同期を実行するか、ネットワークや負荷を調査してください。

> **DR フェイルオーバーの流れ**: ブレーク → 宛先をプライマリに昇格 → クライアントアクセスを切り替え → 復旧後に元のソースへ再同期。

### シナリオ 13: Local Users — SMB ユーザー / グループ管理

1. **Admin > Resources > Local Users** を開く
2. **Users タブ**:
   - SMB ローカルユーザーの一覧（名前、フルネーム、無効状態）を確認
   - **+ Create User** → 名前、パスワード（複雑さ要件を満たすもの）、フルネームを入力
   - 作成 → 一覧にユーザーが表示される
   - **Delete** → 確認 → ユーザーが削除される
3. **Groups タブ**:
   - メンバー数付きのローカルグループ一覧を確認
   - グループカードをクリック → メンバーを展開表示
   - **+ Add Member** → ユーザーを選択 → 追加
   - メンバーの **Remove** → 削除を確認
   - **+ Create Group** → 名前を入力 → 作成

### シナリオ 14: Name Mapping — ID 変換ルール

1. **Admin > Resources > Name Mapping** を開く
2. 既存ルール（方向、インデックス、パターン、置換）を確認
3. **+ Create** → 入力:
   - 方向: `Windows → UNIX`（ドロップダウン: win_unix / unix_win / s3_unix / s3_win）
   - インデックス: 1（優先順）
   - パターン: `DOMAIN\\(.+)`（正規表現）
   - 置換: `\1`（ドメイン接頭辞からユーザー名を抽出）
4. 作成 → 新しいルールが表に表示される
5. ルールの **Delete** → 削除を確認
6. 拒否マッピングの確認: 置換を `" "`（スペース）にして特定ユーザーをブロック

> **セキュリティに関する補足**: name-mapping の拒否（置換 `" "`）は UNIX / MIXED セキュリティスタイルのボリュームで SMB アクセスをブロックします。NTFS ボリュームは Windows ACL を直接使うため影響を受けません。

### シナリオ 15: FlexCache — 作成、監視、削除

1. **Admin > Resources > FlexCache**（Storage カテゴリの ⚡ アイコン）を開く
2. FlexCache ボリュームが存在しない場合、案内パネルを確認:
   - FlexCache の役割（リモートボリュームのキャッシュ。読み取りを高速化し、書き込みも 2 つのモードで受け付ける）
   - 代表的なユースケース（EDA/CAD、ビルドパイプライン、AI 推論データ）
   - NetApp FlexCache ドキュメントと AWS FSx for ONTAP ボリューム管理へのリンク
3. **+ FlexCache 作成** → 作成フォームが開く:
   - **キャッシュ名**（必須）: 例 `flexcache_eda_tokyo`
   - **オリジンボリューム名**（必須）: 既存ボリュームの datalist ドロップダウン
   - **オリジン SVM**（任意）: 同一 SVM 内キャッシュなら空欄
   - **サイズ (GiB)**: 既定 100、ヒントは「オリジンの 10% 推奨」
   - **ジャンクションパス**: `/<cache_name>` が自動入力
   - **プリポピュレートパス**: 事前ウォームするパスをカンマ区切りで指定（例: `/data/models/, /cache/datasets/`）
4. 入力後 **作成**:
   - 非同期リクエスト中はスピナーと「作成中...」を表示
   - 成功トースト: 「FlexCache を作成しました（バックグラウンドで構築中）」
   - 10 秒 / 30 秒 / 60 秒で段階的に再取得（ONTAP の FlexCache 作成には 30〜120 秒かかる）
5. 再取得後、新しい FlexCache が一覧に表示される:
   - オリジン → キャッシュの矢印表示: `📦 vol_production@svm01 → ⚡ flexcache_eda_tokyo@svm01`
   - サイズとジャンクションパス
   - Global File Locking バッジ（有効時）
   - キャッシュメトリクスの参照注記
6. **▶ Origins** → オリジン詳細（クラスター、SVM、ボリューム、状態）を展開
7. 削除: **削除** → インライン確認「本当に削除？ [実行] [取消]」
   - 削除は 3 段階の自動処理: アンマウント → オフライン → 削除
   - 成功トーストで削除完了を確認

> **補足**: FlexCache は親ボリュームのスループット枠を共有します。推奨キャッシュサイズはオリジンの 10〜20% です。読み取り中心のワークロード（EDA/CAD、ビルドパイプライン、AI 推論）向けで、書き込み先には向きません。

> **複数ファイルシステムの識別**: パネルヘッダーに操作対象の FSx for ONTAP 管理 IP が表示されます。複数のファイルシステムにアクセスできる環境で有用です。

### シナリオ 16: FPolicy — ファイルアクセス監査の設定

1. **Admin > Resources > FPolicy** を開く
2. **Policies タブ**: 有効 / 無効、優先度、エンジン、イベントを確認
3. **Events タブ**: 設定済みイベント（プロトコル、監視対象操作: open/close/read/write/delete/rename）を確認
4. **Status タブ**: 外部エンジンの接続状態（connected/disconnected）を確認
5. DemoMode で 3 タブ構成がエラーなく描画されること（空リスト表示）を確認

### シナリオ 17: Athena SQL — NAS データの分析

1. **AI & Processing > Analytics**（サイドバー: 📊 分析）を開く
2. Athena の役割と Glue Crawler + S3 AP との関係を説明する案内パネルを確認
3. **🗂️ データカタログを開く** をクリック → Glue Data Catalog のデータベース / テーブル / 列を確認
4. テーブルを選択して **このテーブルをクエリする** → データベースとクエリ欄が自動入力される
5. **📝 クエリ例を見る** を展開して例を確認
6. **クエリ実行** で実行
7. 結果が列見出しと行数付きの表として描画されることを確認

> **Athena の前提条件**: S3 AP のファイルをカタログ化する Glue Crawler が設定済みである必要があります。Glue テーブルがなければカタログブラウザーは空で、その旨を表示します。ポータルの Athena パネルはクエリインターフェースであり、Glue Crawler やテーブルを作成するものではありません。

**このパネルの意義**: AWS Athena コンソールを別に開かずに、ストレージ管理者やデータエンジニアがポータルから直接 SQL を実行できます。代表的な用途:
- 「1 GB を超えるファイルはどれか」（キャパシティプランニング）
- 「直近 7 日間に変更されたのは何か」（変更追跡）
- 「engineering/ フォルダーのデータ量はどれくらいか」（プロジェクト規模の把握）

## アーキテクチャに関する補足

### CloudFormation テンプレートサイズの最適化

ポータルは CloudFormation テンプレートを 1MB 未満に保つため、**汎用ディスパッチパターン**を採用しています:

```
57 個の個別 GraphQL 操作 → 8 個の汎用ディスパッチエンドポイント
```

| エンドポイント | データソース | 操作数 |
|---------------|-------------|--------|
| `adminQuery` / `adminMutation` | ResourceMgmtLambda | 管理操作 48 件 |
| `arpQuery` / `arpMutation` | ArpResponseLambda | ARP 操作 7 件 |
| `protectionQuery` / `protectionMutation` | ListSnapshotsLambda | 保護操作 9 件 |
| `fileQuery` / `fileMutation` | ListFilesLambda | ファイル操作 6 件 |

各ディスパッチリゾルバは `action` パラメータで Lambda ハンドラー内の既存のアクション分岐にルーティングします。

### VPC の分割アーキテクチャ

| Lambda の種類 | VPC | 目的 |
|--------------|-----|------|
| ListFiles, GetPresignedUrl, SearchFiles | **VPC なし** | インターネットオリジンの S3 AP アクセス |
| ResourceMgmt, ArpResponse, ListSnapshots | **VPC 内** | ONTAP 管理 LIF（TCP/443） |
| AskAboutFile, DetectLabels, Textract, Comprehend | **VPC なし** | AWS の AI サービス |

### IaC の設定

VPC / ONTAP の設定はすべて `amplify/portal-config.ts` にあります:

```typescript
export const config: PortalConfig = {
  // ... S3 AP の設定 ...
  vpcId: process.env.AMPLIFY_PORTAL_VPC_ID || "",
  vpcSubnetIds: (process.env.AMPLIFY_PORTAL_VPC_SUBNET_IDS || "").split(",").filter(Boolean),
  vpcSecurityGroupIds: (process.env.AMPLIFY_PORTAL_VPC_SG_IDS || "").split(",").filter(Boolean),
  // vpcId を設定する場合は必須 — 下記参照。
  vpcRouteTableIds: (process.env.AMPLIFY_PORTAL_VPC_ROUTE_TABLE_IDS || "").split(",").filter(Boolean),
};
```

`vpcId` が空の場合、Lambda は VPC なしでデプロイされます（管理パネルは「ONTAP 接続が必要です」と穏当に表示）。

#### VPC を使う場合 `vpcRouteTableIds` は必須

Lambda のサブネットに関連付けられたルートテーブルを指定します。これにより DynamoDB のゲートウェイエンドポイントが作成され、VPC 内の関数が封じ込めブロックの台帳に到達できるようになります。`vpcId` が設定されているのに未指定だと **synth が実行を拒否する**ため、後回しにはできません。

`portal-config.ts` は gitignore 済みで、素の値を受け取る `portal-config.example.ts` からコピーします。上記の `AMPLIFY_PORTAL_*` 環境変数は参照実装での読み取り方であり、自身の `portal-config.ts` が同じ配線をしている場合にのみ効きます。フィールドを直接設定する方法は常に機能します。

Lambda の ENI はパブリック IP を持たないため、デフォルトルートがインターネットゲートウェイのサブネットでは関数から一切外部に出られません。Secrets Manager はインターフェースエンドポイントで到達できますが、DynamoDB は追加しない限り経路がありません。ゲートウェイエンドポイントには時間課金もデータ処理料金もかかりません。

**未設定のまま運用した場合**: 封じ込めは動作しますが、何も期限切れになりません。ブロックはクラスターに設定され、定期スイープはそれを認識しません（台帳への書き込みが失敗するため）。レスポンスは `expiryTracked: false` を返し、ブロックが自動解除されるかのように装うことはしません。ただし、この状態はレスポンスを読んだ人にしか見えません。

サブネットのルートテーブルは次のように調べます:

```bash
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<your-subnet-id>" \
  --query "RouteTables[].RouteTableId" --output text
```

サブネットに明示的な関連付けがない場合、VPC のメインルートテーブルが使われます:

```bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=<your-vpc-id>" "Name=association.main,Values=true" \
  --query "RouteTables[].RouteTableId" --output text
```

## 検証結果（2026-07-26）

| パネル | 状態 | 備考 |
|-------|------|------|
| Volumes | ✅ | 9 ボリューム（clone01, cachevol01, ds_migtoaws_bk, ...） |
| Export Policies | ✅ | 2 ポリシー（default, fsx-root-volume-policy）、作成 / 削除が動作 |
| QoS Policies | ✅ | API は動作、ポリシー未設定（空状態を表示） |
| SMB Shares | ✅ | 4 共有（c$, cachevol01, ipc$, testshare01）、暗号化トグルが動作 |
| Storage Efficiency | ✅ | 9 ボリュームで 1.21x、17.7% 削減 |
| Snapshot Admin | ✅ | ポリシー一覧、改ざん防止状態の照会が可能 |
| ARP/AI Admin | ✅ | 9 ボリューム、すべて無効、一括有効化が可能 |
| SnapLock | ✅ | 全ボリューム non_snaplock（WORM 未設定） |
| Qtrees | ✅ | 検索フィルター付き VolumeSelector、先頭を自動選択 |
| Quotas | ✅ | VolumeSelector 連携、クォータルール一覧 |
| Lock パネル | ✅ | 3 タブ: SnapLock（インライン一覧）、S3 Object Lock（ONTAP 非依存）、Tamperproof（インラインロックフォーム） |
| Snapshots（Data Protection） | ✅ | hourly/weekly/daily をロックボタン付きで表示 |
| ARP/AI Status | ✅ | vol1 は disabled、対応アクションが利用可能 |
| FlexCache | ✅ | 作成 / 一覧 / 削除を E2E 検証、3 段階削除（アンマウント → オフライン → 削除）、段階的再取得 |
| SnapMirror | ✅ | 状態バッジ付き一覧、操作ボタン（同期 / ブレーク / 再同期 / 一時停止 / 再開 / 削除）、転送履歴 |
| File Explorer | ✅ | S3 AP から 29 ディレクトリ（ai-outputs, contracts, dicom, ...） |

## スクリーンショット

| ファイル | 説明 |
|---------|------|
| `docs/screenshots/file-explorer-directories.png` | FSx for ONTAP S3 AP のディレクトリを表示する File Explorer |
| `docs/screenshots/resource-management-overview.png` | Resource Management のカード一覧（Storage/Access/Protection/AI、全体） |
| `docs/screenshots/volumes-panel.png` | ONTAP の実データを表示する Volume Manager |
| `docs/screenshots/storage-efficiency-panel.png` | Storage Efficiency ダッシュボード |
| `docs/screenshots/08-arp-admin-panel-en.png` | 9 ボリュームの ARP/AI 管理 |
| `docs/screenshots/snapshots-version-history.png` | hourly/weekly/daily の Snapshot 履歴 |
| `docs/screenshots/snapshot-lock-confirm.png` | Snapshot ロックの確認ダイアログ（保持期間の指定と不可逆である旨の明示） |
| `docs/screenshots/quota-manager.png` | ボリュームセレクターとルール表付きの Quota Manager |
| `docs/screenshots/quota-create-form.png` | クォータ作成フォーム（種別、対象、上限） |
| `solutions/amplify-portal/docs/screenshots/smb-shares-panel.png` | 暗号化トグル + CA 情報 + 削除ボタン付きの SMB Shares |
| `solutions/amplify-portal/docs/screenshots/export-policy-panel.png` | ポリシー作成 / 削除操作付きの Export Policy |
| `solutions/amplify-portal/docs/screenshots/lock-panel-snaplock.png` | Lock パネルの SnapLock タブ（インライン一覧） |
| `solutions/amplify-portal/docs/screenshots/lock-panel-tamperproof.png` | Lock パネルの Tamperproof タブ（インラインロックフォーム） |
| `solutions/amplify-portal/docs/screenshots/lock-panel-s3objectlock.png` | Lock パネルの S3 Object Lock タブ（ONTAP 非依存） |
| `solutions/amplify-portal/docs/screenshots/qtree-volume-selector.png` | VolumeSelector 検索 / フィルター付きの Qtree パネル |
| `docs/screenshots/vscan-setup-guidance.png` | 6 ベンダー比較表付き Vscan 5 ステップ案内 |
| `docs/screenshots/flexclone-manager.png` | クローン一覧と作成フォーム付きの FlexClone パネル |
| `docs/screenshots/snapmirror-status.png` | 状態バッジ、RPO 警告、操作ボタン付きの SnapMirror 関係 |
| `docs/screenshots/snapmirror-create-form.png` | SnapMirror 新規作成フォーム（SVM ピア選択、前提条件、作成される関係のプレビュー） |
| `docs/screenshots/local-user-manager.png` | Local User Manager（Users タブの CRUD 操作） |
| `docs/screenshots/name-mapping-manager.png` | 方向セレクターと作成フォーム付きの Name Mapping ルール |
| `docs/screenshots/flexcache-manager.png` | 作成フォーム（オリジン datalist、プリポピュレートパス）とキャッシュ一覧 |
| `docs/screenshots/flexcache-create-success.png` | FlexCache 作成成功トーストと段階的再取得の表示 |
| `docs/screenshots/flexcache-delete-confirm.png` | FlexCache のインライン削除確認（「本当に削除？ [実行] [取消]」） |
| `docs/screenshots/snapmirror-transfers.png` | SnapMirror 転送履歴の展開（success/failed、サイズ、所要時間） |
| `docs/screenshots/athena-query-panel.png` | 案内テキストと SHOW TABLES 既定値付きの Athena SQL パネル |
| `docs/screenshots/athena-query-panel-expanded.png` | クエリ例を展開した Athena SQL パネル |
| `solutions/amplify-portal/docs/screenshots/storage-dashboard.png` | Storage Health ダッシュボード（容量、ARP、ロック、効率の 4 カード） |
| `solutions/amplify-portal/docs/screenshots/ai-processing-ready.png` | AI Processing ページ（正常、エラーなし） |
| `solutions/amplify-portal/docs/screenshots/lock-panel-s3objectlock-config.png` | バケット一覧付き S3 Object Lock 設定フォーム |

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| 「ONTAP 接続が必要です」 | Lambda が VPC 内にない | `AMPLIFY_PORTAL_VPC_ID/SUBNET_IDS/SG_IDS` を設定 |
| 「User is not authorized」 | fsxadmin のパスワード不一致 | `aws fsx update-file-system --ontap-configuration '{"FsxAdminPassword":"..."}'` でリセットし、シークレットも更新 |
| 「Execution timed out」 | VPC エンドポイント不足または SG でブロック | Lambda の SG から 443 で到達できる Secrets Manager VPC エンドポイントを用意 |
| 「Volume not found」 | SVM 名の誤り | `aws fsx describe-storage-virtual-machines` の結果と `ONTAP_SVM_NAME` が一致するか確認 |
| テンプレートが 1MB 超 | リゾルバが多すぎる | 汎用ディスパッチパターンで解決済み |
| File Explorer にファイルが出ない | S3 AP エイリアスの誤り | `portal-config.ts` のエイリアスが `aws fsx describe-storage-virtual-machines --query ...S3AccessPoints` と一致するか確認 |

## 追加シナリオ

### シナリオ 18: Storage Health ダッシュボード

1. **Admin > Resources** を開く
2. 概要の上部にある **4 つのサマリーカード** を確認:
   - 💾 Volumes（件数 + 平均容量 %）
   - 🛡️ ARP Protected（件数 + 脅威の表示）
   - 🔐 Locked Snapshots（改ざん防止の件数）
   - 📊 Storage Efficiency（削減率 + 削減 %）
3. カードをクリックすると該当パネルに直接遷移
4. 容量が 85% を超えると、カードに黄色の警告表示が出る

### シナリオ 19: ウェルカムオンボーディング（初回利用）

1. localStorage をクリア: `localStorage.removeItem('portal-welcome-dismissed')`
2. ページを再読み込み → 3 ステップのウェルカムモーダルが表示される
3. Step 1: ファイル閲覧（S3 AP アクセスの説明）
4. Step 2: AI 処理（Bedrock/Rekognition/Textract）
5. Step 3: データ保護（Snapshots/SnapLock/ARP）
6. 「はじめる」をクリック → モーダルが閉じる
7. 「次回から表示しない」をチェック → 次回以降は表示されない

### シナリオ 20: インシデントのライフサイクル（ARP 封じ込め）

1. **Data Protection > ARP/AI** を開く
2. **Incident Response** セクションの状態バッジを確認:
   - 🔴 検知済み（脅威検出時）
   - 🟠 封じ込め完了（封じ込め実行後）
   - 🟡 調査中（調査中）
   - 🟢 解決済み（解決済み）
3. **脅威封じ込め** を実行 → バッジが「封じ込め完了」に遷移
4. **→ 調査開始** → バッジが「調査中」に遷移
5. **→ 解決** → バッジが「解決済み」に遷移

### シナリオ 21: EMS イベント（ONTAP アラート）

1. **Admin > Resources > Cluster** を開く
2. **Events** タブに切り替える
3. 直近の EMS イベント（タイムスタンプ、重大度: alert / error / emergency、メッセージ、ノード名）を確認
4. 運用状況の把握に使う: ディスク障害、アグリゲートの警告、HA テイクオーバーなど

> FSx for ONTAP では、クラスター層を AWS が管理するため `/cluster/nodes` と `/cluster/licensing/licenses` が 0 件を返すことがあります。これらのタブが空でもエラーではありません。

### シナリオ 22: ファイルのライフサイクル（名前変更、ごみ箱、復元）

1. **Browse > All Files** を開く
2. ファイル行の **✏️** をクリック → 名前を編集 → **保存**
   - 名前に `/` を含めると拒否される（移動ではなく名前変更のため）
3. 行の **🗑️** → 確認 → ファイルが `.trash/` プレフィックスへ移動
   - S3 Access Point 上ではコピー後に元を削除するため、大きなファイルでは時間がかかる
4. ヘッダーの **🗑️ ごみ箱** をクリック → `.trash/` の内容が表示される
5. **♻️** をクリック → ファイルが元の場所に戻る
6. **🗑️ ごみ箱を閉じる** で通常の閲覧に戻る

### シナリオ 23: アップロードリンク（ポータル外の相手からの受け取り）

1. 受け取り先のフォルダーを開く
2. **📤 アップロードリンク** をクリック
3. ファイル名を入力（空欄なら自動生成）、有効期限を 1 時間または 24 時間から選択
4. **リンクを発行** → 保存先キーと URL が表示される
5. URL をコピーして相手に渡す

> **セキュリティに関する補足**: この URL 自体が認証情報です。期限まで、URL を持つ誰でもそのキーに書き込めます。UI が保存先キーと有効期限を併記するのはこのためです。

### シナリオ 24: 保存済みエージェント / チームの実行

1. **AI & Processing > Agent Directory** を開く
2. エージェントカードをクリック → 詳細（ツール、システムプロンプト）を確認
3. **💬 チャットで使う** → AI Chat が開き、そのエージェント定義で実行される
   - 実行中のエージェント名がバッジで表示され、モード選択は隠れる
4. 作成者本人であれば **✏️ 編集** が出る → 名前 / 説明 / システムプロンプト / 共有設定を変更 → 保存
   - 他人のエージェント（共有されたもの）には編集 / 削除は表示されない
5. **Multi-Agent Teams** からチームを選ぶと、メンバー構成とロールを 1 ターンのスーパーバイザーとして実行する
   - 到達できないメンバーがいても実行は継続し、応答で `unavailableMembers` として明示される

### シナリオ 25: 文書のテキスト抽出と解析

1. **Browse > All Files** でファイルを選択（右側に AI パネルが開く）
2. **🔎 文書を解析** をクリック
3. **テキストを抽出** → Amazon Textract の結果（ページ数、ブロック数、本文）を確認
   - スキャン PDF などテキスト層のない文書は、これを先に実行するとチャットが読めるようになる
4. 解析の種類（エンティティ / 感情 / PII 検出 / キーフレーズ）を選び **解析を実行**
5. 規制フォルダー（`phi/`、`dicom/`、`pii/` など）のファイルでは、どちらも拒否される
   - バイトを外部のマネージドサービスに送る操作であるため、ガードの対象になる

### シナリオ 26: SnapMirror 転送の中止

1. **Admin > Resources > SnapMirror** を開く
2. 転送が進行中の関係で **▶ 転送履歴** を展開
3. 状態が「転送中 / キュー / 準備中 / 最終処理中」の行に **⏹ 転送を中止** が表示される
4. クリック → 確認（差分は次回の更新で再送されることを明示）→ 中止
5. その行の状態が更新されることを確認

### シナリオ 27: フォルダー監視とイベント通知

前提: **Admin > Resources > AI 設定**で「フォルダー監視」を有効化しておく（既定はオフ）。有効化の意味は「FPolicy または Transfer Family が EventBridge にイベントを発行している」という管理者の宣言です。

1. サイドバー **Browse > フォルダー監視**（🔔）を開く
   - トグルがオフの場合、この項目はサイドバーに現れない
2. **フォルダー（プレフィックス）** に監視したいパスを入力（例: `engineering/cad/`）
3. 対象イベント（作成 / 更新 / 削除）を選び **監視を追加**
   - 末尾のスラッシュは自動補完される。前方一致で兄弟フォルダーを巻き込まないため
4. 監視対象の表に追加される。**解除** で削除
5. **受信したイベント** に、登録したプレフィックス配下のイベントが新しい順に表示される
6. イベントが 0 件の場合、必要な 3 条件が列挙される（FPolicy の有効化 / EventBridge への発行 / プレフィックスの一致）

> **セキュリティに関する補足**: 受信箱はまず Cognito グループのパス境界（`GROUP_PATH_PREFIXES`）で絞られ、その後に自分の監視対象で絞られます。監視は自分のレコードなので `/` も登録できますが、それでグループ境界の外が見えることはありません。`storage-admin` は境界を迂回します。単一テナント構成（`GROUP_PATH_PREFIXES` 未設定）では全イベントが見えます。ファイル一覧と同じ境界です。

> **アーキテクチャ**: FPolicy サーバー（または Transfer Family）→ EventBridge → 通知ブリッジ Lambda → `FileNotification` テーブル → ポータル。ポータルは ONTAP にイベントを出させる側ではなく、届いたものを読む側です。FPolicy 自体の構成は [event-driven/fpolicy パターン](../../solutions/event-driven/fpolicy/) を参照してください。

## 関連ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [Admin Resource Management — Demo Guide (EN)](../en/admin-resource-management-demo.md) | 本ドキュメントの英語版 |
| [PoC → 本番移行ガイド](portal-poc-to-production.md) | DemoMode から本番接続への移行手順 |
| [スケーリングガイド](portal-scaling-guide.md) | キャパシティプランニングとスループット共有 |
| [Tamperproof Snapshot 設計](../tamperproof-snapshot-design.md) | 3 層設計と不可逆性のルール |
