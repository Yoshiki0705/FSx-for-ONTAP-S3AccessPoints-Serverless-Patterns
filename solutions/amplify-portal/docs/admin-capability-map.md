# 管理機能マップ — 各インターフェースの担当範囲とポータルの実装状況

> 目的: ONTAP の運用に使えるインターフェースがそれぞれ何を担うのかを整理し、
> 本ポータルが現時点でどこまで実装済みなのかを、実測に基づいて示します。

[English](admin-capability-map.en.md)

---

## 結論

本ポータルは、**ONTAP REST API で実行できる運用操作を、Cognito 認証つきの画面から実行できるようにする層**です。

Amazon FSx for NetApp ONTAP（以降 FSx for ONTAP）に対して、追加のサードパーティ SaaS を経由せずに到達できるインターフェースは、AWS マネジメントコンソール / FSx API、ONTAP CLI（SSH）、ONTAP REST API の 3 つです。ONTAP System Manager はこの一覧に含まれません（根拠と誤解の整理は [FSx for ONTAP の管理インターフェース](../../../docs/ja/fsx-ontap-management-interfaces.md)）。したがって本ポータルの比較相手は System Manager ではなく **ONTAP CLI と REST API** です。

その 2 つと比べたときの違いは次の 2 点です。

- **委譲**: ストレージ管理者以外（セキュリティ、コンプライアンス、データ保護）に、クラスター管理者相当の SSH を渡さずに特定の操作だけを委譲できます。
- **記録**: 誰がどの操作をいつ実行したかが Cognito の主体つきで残ります。

とくに **クラスターピアリングと SVM ピアリング** は、FSx for ONTAP の AWS マネジメントコンソールに操作面がないため、これまで ONTAP CLI か REST API を手作業で叩く必要がありました。本ポータルはこの領域を画面から実行できるようにしています。

ONTAP のバージョン管理、ノード、ディスク・シェルフは **AWS が運用します**。利用者側の操作としては存在しないため、本ポータルにも他のどのインターフェースにも現れません。

---

## インターフェースの担当範囲

「ONTAP CLI / REST API」と書いた行は、本ポータルを使わない場合にその操作を実行する手段です。

| 領域 | ポータルを使わない場合の手段 | 本ポータルの位置づけ |
|------|---------------------------|--------------------|
| ONTAP のバージョン管理・ノード・ディスク・シェルフ | AWS が運用（利用者の操作なし） | 対象外 |
| ファイルシステム・SVM・ボリュームの作成、バックアップ | AWS マネジメントコンソール / FSx API | 一部（ボリューム操作は実装済み） |
| ボリューム・Qtree・クォータの日常運用 | ONTAP CLI / REST API | 実装済み |
| NAS アクセス制御（エクスポートポリシー、SMB 共有） | ONTAP CLI / REST API | 実装済み |
| ID マッピング（Windows ↔ UNIX）、SMB ローカルユーザー | ONTAP CLI / REST API | 実装済み |
| スナップショット・SnapLock・改ざん防止 | ONTAP CLI / REST API | 実装済み |
| ランサムウェア検知（ARP/AI）の確認と対処 | ONTAP CLI / REST API | 実装済み |
| FlexCache・FlexClone | ONTAP CLI / REST API | 実装済み |
| レプリケーション（SnapMirror）の状態確認と運用操作 | ONTAP CLI / REST API | 実装済み |
| ウイルススキャン（Vscan）・FPolicy の設定 | ONTAP CLI / REST API | 実装済み |
| クラスターピア・SVM ピア | ONTAP CLI / REST API | 実装済み（マネジメントコンソールに操作面なし） |
| ノード・ライセンス・LIF・プロトコルサービス・DNS・ジョブ | ONTAP CLI / REST API | 実装済み（参照） |
| 長期のメトリクス蓄積・容量トレンド分析 | Amazon CloudWatch / ONTAP REST API | 本リポジトリの `operations/` パターン |
| ファイルアクセス監査の集約・異常検知 | FPolicy → EventBridge → 本リポジトリのパターン | `solutions/event-driven/fpolicy/` |
| エンドユーザーのファイル閲覧・共有 | 本ポータル | 実装済み |

> **可観測性・監査の方針に関する補足**: ベンダー提供の可観測性スイートや
> 監査分析製品を使う選択肢もありますが、本リポジトリでは AWS ネイティブな仕組み
> （Amazon CloudWatch、ONTAP REST API、FabricPool、AWS DataSync、
> Snapshot / FlexClone / SnapMirror）に統一しています。追加の運用基盤を
> 導入せずに済み、IaC で構成を管理できることを優先した判断です。
> どちらが適するかは、既に運用している基盤と、監査要件の粒度で決まります。

---

## ONTAP の機能領域との対応

ONTAP の機能領域を軸に、本ポータルの対応状況を示します。
「対象外」は実装漏れではなく、担当インターフェースを分けた結果です。

領域の区切りは ONTAP System Manager の画面構成に合わせています。System Manager を
使い慣れた読者が対応を追いやすいためで、FSx for ONTAP で System Manager が使える
という意味ではありません（[管理インターフェースの整理](../../../docs/ja/fsx-ontap-management-interfaces.md)）。

| 機能領域 | 主な機能 | 本ポータルの対応 |
|---------|---------|----------------|
| ダッシュボード | 容量、性能、健全性の概況 | 部分的（容量・ARP/AI・EMS を個別パネルで表示。性能グラフは CloudWatch 側） |
| ストレージ | ボリューム、Qtree、クォータ、効率、LUN | 実装済み（LUN は対象外。FSx for ONTAP の SAN 用途は本ポータルの範囲外） |
| ネットワーク | LIF、ポート、ルート、ブロードキャストドメイン | 部分的（LIF の一覧と有効・無効。ポートとルートは対象外） |
| イベント | EMS アラート | 実装済み |
| データ保護 | スナップショット、SnapLock、SnapMirror | 実装済み |
| ホスト | NFS / SMB クライアント、iSCSI イニシエーター | 部分的（SMB ローカルユーザーと名前マッピング。iSCSI は対象外） |
| クラスター | ノード、HA、ライセンス、バージョン | 実装済み（参照） |
| クラスター | ピアリング（クラスター / SVM） | 実装済み（作成・承認・削除） |
| クラスター | ネームサービス（DNS） | 実装済み |
| クラスター | プロトコルサービス（NFS / SMB / S3） | 実装済み（有効・無効） |
| クラスター | ジョブ | 実装済み（参照） |
| クラスター | ONTAP アップグレード、ディスク・シェルフ | 対象外（FSx for ONTAP では AWS が運用。利用者の操作なし） |

---

## 破壊的操作の扱い

書き込み操作のうち、影響範囲が広いものは二段階にしています。
UI で確認行を表示し、ハンドラ側でも `confirm=true` がなければ実行しません。
UI を経由しない直接呼び出しでも、確認なしでは通らない構成です。

| 操作 | 確認を必須にしている理由 |
|------|----------------------|
| SnapMirror の break | 宛先が書き込み可能になり、再同期には resync が必要になります |
| SnapMirror の resync | 差分の方向によっては宛先の更新分が失われます |
| SnapMirror の削除 | 関係が消え、再作成には初期転送が必要になります |
| Vscan ポリシーの削除 | スキャン対象から外れます |
| FPolicy イベント・ポリシーの削除 | 監査イベントの発生が止まります |
| クラスターピア・SVM ピアの削除 | 依存するレプリケーションと FlexCache が停止します |
| LIF の無効化 | その LIF が担う経路（管理・データ）が切断されます |
| プロトコルサービスの無効化 | そのプロトコルを使用中のクライアントが切断されます |

ONTAP 側の制約に合わせた振る舞いも入れています。

- FPolicy の有効化は `priority` を必須とし、無効化では送りません（ONTAP の仕様）。
- 有効なままの FPolicy ポリシーは削除できないため、削除ボタンを無効化しています。
- 名前マッピングの `s3_unix` 方向は作成できません。S3 Access Point 用のマッピングは
  FSx for ONTAP が自動管理するためです。
- FlexClone 作成時に `nas.security_style` は送りません。親ボリュームから継承されます。

---

## 実装状況の一覧（実測）

`リソース管理` に表示される 20 パネルすべての実装状況です。
各アクションは ONTAP REST API を呼ぶ Lambda（`functions/resource-management/handler.py`）に
実装されています。

### ストレージ

| パネル | 参照 | 作成 | 変更 | 削除 |
|--------|:---:|:---:|:---:|:---:|
| ボリューム | ○ | ○ | ○ リサイズ | ○ |
| Qtree | ○ | ○ | — | ○ |
| クォータ | ○ | ○ | — | ○ |
| ストレージ効率 | ○ | — | — | — |
| FlexCache | ○ | ○ | — | ○ |
| FlexClone | ○ | ○ | ○ 分割 | — |

### アクセス制御

| パネル | 参照 | 作成 | 変更 | 削除 |
|--------|:---:|:---:|:---:|:---:|
| エクスポートポリシー | ○ | ○ ポリシー/ルール | — | ○ ポリシー/ルール |
| SMB 共有 | ○ | ○ | ○ | ○ |
| QoS ポリシー | ○ | ○ | ○ | ○ |
| ローカルユーザー | ○ | ○ ユーザー/グループ | ○ メンバー追加・削除 | ○ ユーザー/グループ |
| 名前マッピング | ○ | ○ | — | ○ |

### データ保護

| パネル | 参照 | 作成 | 変更 | 削除 |
|--------|:---:|:---:|:---:|:---:|
| ARP/AI 保護 | ○ | — | ○ 状態変更・一括有効化 | ○ 疑いクリア |
| スナップショット管理 | ○ | ○ ポリシー | ○ ロック有効化 | — |
| SnapLock | ○ | — | ○ 保持期間 | — |
| SnapMirror | ○ | — | ○ 即時更新・一時停止・再開・break・resync・転送中止 | ○ 関係の削除 |
| ウイルススキャン | ○ | ○ オンアクセスポリシー | ○ Vscan 有効・無効、ポリシー有効・無効 | ○ ポリシー |
| FPolicy | ○ | ○ イベント/ポリシー | ○ ポリシー有効・無効 | ○ イベント/ポリシー |

### クラスター

| パネル | 参照 | 作成 | 変更 | 削除 |
|--------|:---:|:---:|:---:|:---:|
| ピアリング | ○ クラスターピア/SVM ピア/intercluster LIF | ○ クラスターピア/SVM ピア | ○ 承認（passphrase / state） | ○ クラスターピア/SVM ピア |
| クラスター情報 | ○ ノード/ライセンス/LIF/プロトコル/DNS/ジョブ | — | ○ LIF 有効・無効、プロトコル有効・無効、DNS 更新 | — |

### AI サービス

| パネル | 参照 | 変更 |
|--------|:---:|:---:|
| AI 設定 | ○ | ○ 有効・無効 |

---

## ONTAP REST API エンドポイント対応

| 機能 | エンドポイント |
|------|--------------|
| ボリューム、FlexClone | `/storage/volumes` |
| Qtree | `/storage/qtrees` |
| クォータ | `/storage/quota/rules`、`/storage/quota/reports` |
| エクスポートポリシー | `/protocols/nfs/export-policies` |
| SMB 共有 | `/protocols/cifs/shares` |
| QoS ポリシー | `/storage/qos/policies` |
| SMB ローカルユーザー | `/protocols/cifs/local-users` |
| SMB ローカルグループ | `/protocols/cifs/local-groups` |
| グループメンバー | `/protocols/cifs/local-groups/{svm.uuid}/{sid}/members` |
| 名前マッピング | `/name-services/name-mappings` |
| FlexCache | `/storage/flexcache/flexcaches` |
| SnapMirror 関係 | `/snapmirror/relationships` |
| SnapMirror 転送 | `/snapmirror/relationships/{uuid}/transfers` |
| Vscan | `/protocols/vscan/{svm.uuid}`、`/protocols/vscan/{svm.uuid}/on-access-policies` |
| FPolicy | `/protocols/fpolicy/{svm.uuid}/events`、`/protocols/fpolicy/{svm.uuid}/policies` |
| スナップショットポリシー | `/storage/snapshot-policies` |
| EMS イベント | `/support/ems/events` |
| クラスターピア | `/cluster/peers` |
| SVM ピア | `/svm/peers` |
| クラスター情報 | `/cluster` |
| ノード | `/cluster/nodes` |
| ライセンス | `/cluster/licensing/licenses` |
| LIF（intercluster を含む） | `/network/ip/interfaces` |
| DNS | `/name-services/dns` |
| プロトコルサービス | `/protocols/{nfs,cifs,s3}/services` |
| 非同期ジョブ | `/cluster/jobs` |

すべて同一の Secrets Manager 資格情報で管理エンドポイントに HTTPS 接続します。
追加の AWS 権限は不要です。

---

## 前提条件による差

| 操作 | 追加の前提 |
|------|----------|
| SMB 共有、ローカルユーザー、名前マッピング | SVM で CIFS が有効であること |
| FlexCache | オリジンボリュームを持つクラスターとのピア関係 |
| FlexClone | 親ボリュームのスナップショット（省略時は作成時点のスナップショットを使用） |
| SnapMirror 操作 | 宛先が当該クラスターにある関係のみ表示・操作できます |
| Vscan | 外部スキャンエンジンと Vscan コネクタ（ポリシー定義は本ポータルから作成可能） |
| FPolicy | 外部 FPolicy エンジン（`engine: native` を選べば外部エンジンなしでも定義可能） |
| クラスターピア | 両クラスターに up 状態の intercluster LIF、両者間で TCP 11104・11105 と ICMP の許可 |
| SVM ピア | クラスターピアが `available` であること。作成後は相手側での承認が必要 |

### ピアリングの手順

クラスターピアは両側の操作が必要です。ポータルは片側ずつ実行します。

1. `ピアリング` → `intercluster LIF` タブで、両クラスターに up 状態の LIF があるか確認します。
2. セキュリティグループで、両クラスターの intercluster LIF 間に TCP 11104・11105 と
   ICMP を許可します。
3. 片方のクラスターで `クラスターピア作成` を実行し、`パスフレーズを生成する` を選びます。
   生成されたパスフレーズは **この 1 回だけ** 表示されます。
4. もう一方のクラスターで、同じパスフレーズを `承認` に入力します。
5. 状態が `available` になったら、`SVM ピア` タブで SVM ピアを作成し、相手側で承認します。

> **ネットワークに関する補足**: FSx for ONTAP のファイルシステムは複数の ENI を持ちます。
> intercluster の通信は intercluster LIF のアドレスで行われるため、
> セキュリティグループの許可は管理 LIF ではなく intercluster LIF のアドレスに対して
> 設定してください。

> **AD 連携に関する補足**: SVM が AD 参加している場合、S3 Access Point の
> データ操作（ListObjectsV2 / GetObject / PutObject）はすべて AD ドメイン
> コントローラーへの到達性を必要とします。`HeadBucket` は AD が不通でも成功
> するため、疎通確認には必ずデータ操作を使ってください。詳細は
> [AD 参加 SVM の S3 AP 前提条件](../../../docs/ja/ad-joined-svm-s3ap-prerequisites.md) を参照してください。

---

## ファイル操作の機能

リソース管理パネルとは別に、`全ファイル` 画面から使える機能です。

| 機能 | 場所 | 実装 |
|------|------|------|
| フォルダー単位のお気に入り | 行の ☆ / `お気に入り` | `Favorite` テーブル。末尾スラッシュでフォルダーを判別 |
| ファイル単位のお気に入り | 行の ☆ | 同上 |
| ZIP ダウンロード | フォルダー内のヘッダー `📦 ZIP でダウンロード` | `folderMutation` → 専用 Lambda → S3 AP 読み取り → ZIP → 署名付き URL |
| ファイルタグ | 行の 🏷️ | `FileTag` テーブル。行にバッジ表示、展開して編集 |
| PDF インラインプレビュー | ファイル名クリック | 署名付き URL を iframe で表示 |
| Office プレビュー | ファイル名クリック | docx-preview でクライアント側描画 |
| スナップショット比較 | ヘッダー `🔍 スナップショットと比較` | 現行ボリュームとクローンの S3 AP を並べて差分表示 |
| 共有リンク | 行の 🔗 | 署名付き URL。有効期限は 5 分・15 分・1 時間から選択 |
| スナップショットからの復元 | ヘッダー `📸 Restore from Snapshot` | Step Functions で FlexClone を作成 |

ZIP ダウンロードはフォルダー内でのみ表示されます（ルート直下では非表示）。
上限はファイル数と合計サイズの両方で、超過時は生成前にエラーを返します。

> **容量に関する補足**: ZIP は一時バケットに置かれ、ライフサイクルルールで
> 翌日に削除されます。署名付き URL の有効期限も別に設定されており、
> 期限切れ後は再生成が必要です。

---

## 検証方法

実装状況は次の 2 段で確認しています。

1. **ハンドラ単体**: `functions/resource-management/tests/test_handler.py`
   （モックした ONTAP REST 応答に対して、リクエストパスとレスポンス整形を検証）

   ```bash
   cd solutions/amplify-portal/functions/resource-management
   python3 -m pytest tests/test_handler.py -q
   ```

2. **UI**: 開発サーバーで各パネルを操作し、ハンドラの実出力が正しく描画され、
   書き込み操作が想定どおりのパラメーター（破壊的操作では `confirm=true`）で
   呼ばれることを確認
   （手順は [リソース管理 デモガイド](resource-management-demo-guide.md)）

実機の FSx for ONTAP に対する疎通確認は、`npx ampx sandbox` でバックエンドを
デプロイし、管理エンドポイントに到達できる VPC 構成にした上で行ってください。
デプロイ済み Lambda から実機 ONTAP への 1 ホップは、上記 2 段では検証できません。

---

## 関連ドキュメント

- [リソース管理 デモガイド](resource-management-demo-guide.md) — 各パネルの操作手順
- [実装ガイド](IMPLEMENTATION.md) — アーキテクチャと構成
- [ONTAP 接続ガイド](ONTAP-CONNECTION-GUIDE.md) — 管理エンドポイントへの接続設定
- [AI エージェント デモガイド](ai-agent-demo-guide.md)
- [運用最適化パターン](../../../operations/README.md) — メトリクス蓄積と容量分析
