# Harvest / Prometheus メトリクス経路の設計判断記録

ファイルポータルに NetApp Harvest + Prometheus 由来のメトリクス監視を足すときの、
**採った案・採らなかった案・その代償**の記録。人と AI エージェントが同じ箇所を再検討する
ときの判断軸として使う。

この記録の目的は「結論を伝えること」ではなく、**再検討したときに同じ結論に戻るか、戻らない
なら何が変わったのかが判定できる状態を保つこと**。したがって各決定に、選ばなかった案と、
採った案自身の代償を書く。

**確度の表記**: `documented`（一次情報の出典あり） / `verified`（この環境で実測した） /
`assumption`（見積りの前提。実測していない） / `open`（未確認、確認手順あり）。

関連: 実装 spec は `.kiro/specs/portal-harvest-metrics/`（未追跡）。
既存の観測性設計は [observability-design](observability-design.md)。
S3 AP と ONTAP API の罠は [pitfalls-s3ap-ontap](agent/pitfalls-s3ap-ontap.md)。

---

## 0. 前提として確認した事実

再検討のたびに調べ直さないための事実の置き場。**数値・提供状況は陳腐化するので、
引用する前に出典を開くこと。**

| # | 事実 | 確度 | 出典 / 確認方法 |
|---|---|---|---|
| F1 | ポータルのリソース管理 20 パネルに時系列メトリクス表示は存在しない。チャートライブラリも依存に無い | verified | `solutions/amplify-portal/package.json`、`src/components/admin/` の全読み |
| F2 | ポータルは CloudWatch を読んでいない。CloudWatch の import は Alarm を作る側だけ | verified | `amplify/backend.ts`、`functions/**` の grep |
| F3 | ポータルが操作できる ONTAP は環境変数 `ONTAP_MGMT_IP` の 1 台。`platform-discovery` は列挙のみ | verified | `functions/platform-discovery/handler.py` の docstring |
| F4 | Harvest のエクスポータは Prometheus（プル用 `/metrics`）/ InfluxDB / VictoriaMetrics（`/api/v1/import/prometheus` へのプッシュ）の 3 種で、**Prometheus `remote_write` を話すものは無い** [E-002]。プッシュ手段が無いのではなく、AMP が要求するプロトコルを話す手段が無い | documented | <https://netapp.github.io/harvest/26.08/prometheus-exporter/>、<https://netapp.github.io/harvest/26.08/configure-harvest-basic/>、<https://netapp.github.io/harvest/26.08/victoriametrics-exporter/> |
| F5 | FSx for ONTAP がサポートする Harvest ダッシュボードは `fsx` タグ付きに限られる。非サポートは 10 種で、うち `ONTAP: S3 Object Stores` と `ONTAP: File Systems Analytics (FSA)` 以外はハードウェア系または当リポジトリで未使用 | documented | <https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/monitoring-harvest-grafana.html> |
| F6 | `ONTAP: S3 Object Stores` は ONTAP の S3 オブジェクトストアであり、**FSx for ONTAP S3 Access Points とは別物** | documented | 同上 + FSx for ONTAP の S3 AP ドキュメント |
| F7 | FSx for ONTAP には `fsxadmin-readonly` ロールがあり、AWS が **NetApp Harvest のような監視アプリケーション向けとして名指しで推奨**している | documented | <https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/roles-and-users.html> |
| F8 | ~~同じ FSx for ONTAP ガイドの別ページに矛盾する記述がある~~ → **この主張は誤りだった（§10.1）。** 該当の 1 文は `-role` パラメータ説明の中にあり、**同じページが `fsxadmin-readonly` の作成例と、NetApp Harvest 用の読み取り専用ユーザーを作る例を載せている。** 矛盾は 2 ページ間ではなくページ内の不整合で、用途は最初からドキュメントに書かれていた | documented（訂正済み） | <https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-new-ontap-users.html>（**全文を読んだ**。当初はスニペットだけで判断していた） |
| F9 | AMP の保持期間は**ワークスペース単位で一律**。既定 150 日、最大 1095 日まで変更可 [E-004] | documented | <https://docs.aws.amazon.com/prometheus/latest/userguide/AMP-workspace-configuration.html> |
| F10 | AMP の「ラベルセット単位のアクティブシリーズ上限」はスパイク隔離の機能で、**偽ラベルの書き込みを拒否しない** [E-005] | hypothesis（推論: ページは送信可能なラベル値への制限に触れていない） | 同上 |
| F11 | Amazon Managed Grafana のワークスペース認証は **IAM Identity Center / SAML / 両方**から選ぶ。**ワークスペース内の権限割り当てに IAM ユーザーとロールは使えない** [E-003]。~~匿名アクセスを持たない~~ という言い方は community 回答が出典で公式の言明ではない（§10.3） | documented（範囲を縮小して訂正） | [AMG-create-workspace](https://docs.aws.amazon.com/grafana/latest/userguide/AMG-create-workspace.html)、[authentication-in-AMG-SSO](https://docs.aws.amazon.com/grafana/latest/userguide/authentication-in-AMG-SSO.html)。匿名アクセスの表現は repost.aws の回答 |
| F12 | AWS と NetApp のサイジングは食い違っていない。AWS は「10 台ごとに CPU 2 コア / メモリ 1 GB / **ディスク** 500 MB」を NetApp の推奨として引用し、NetApp のブログの「4 CPU / 16 GB」は Harvest + Prometheus + Grafana を 1 台に同居させる前提条件 | documented | F5 の URL + <https://www.netapp.com/learn/aws-fsx-blg-how-to-monitor-amazon-fsx-for-netapp-ontap-using-netapp-harvest/> |
| F13 | AWS のテンプレートが起動する Harvest イメージは Docker Hub の個人名前空間 `rahulguptajss/harvest`（タグ指定なし） | documented | F5 の URL のトラブルシューティング節の `docker ps` 出力 |
| F14 | FSx for ONTAP S3 Access Points の CloudWatch メトリクスは、ドキュメントにも実際の名前空間にも見当たらない。**ただし確度は 3 層に分かれる（§10.2）**: ドキュメントの分類にアクセスポイント次元が無い（documented）/ AP が 22 件ある環境で S3 系メトリクス名が 0（verified、`list-metrics` の性質による留保つき）/ S3 のバケット単位オプトイン機構は適用されないと考えられる（hypothesis） | 3 層（§10.2） | 全文を読んだページ 3 本と実行結果を §10.2 に列挙。**AWS サポートへの確認と機能改善要望は未実施**（当初この確認を省いていた） | <!-- allow:naming: CloudWatch 名前空間の literal -->

> **F12 は「食い違いがある」という広く流布した読みを否定する。** 引用するときは、
> 何をサイズしている数字なのかを併記すること。AMP を採る構成では Prometheus と Grafana が
> 中央から消えるので、ブログ側の前提はそもそも適用されない。

---

## 1. スコープの決定

### D1. 既存表示の出典は変えない（新規追加として扱う）

- **採った案**: 20 パネルの数値読みは ONTAP REST のまま。時系列は新規に足す。
- **却下**: `StorageDashboard` の容量・効率カードを Prometheus 由来に差し替える案、
  20 パネルの数値読みを可能な限り Prometheus に寄せる案。
- **根拠**: 設定操作画面で見る容量は**操作直後に反映されること**に意味がある。Prometheus 経由に
  するとスクレイプ間隔ぶん古い値になり、機能の劣化になる。F1 のとおり「置き換える対象」は
  そもそも存在しない。
- **代償**: 同じ量（容量）が 2 つの出典で画面に出る。**どちらを見ているかを画面が言わないと
  読者が混乱する**ので、傾向表示側には必ず出典と鮮度を書く（D18 と対）。
- **再検討の引き金**: ONTAP REST の呼び出し回数が問題になったとき。

### D2. メトリクス UI の置き場所はリソース管理の外

- **採った案**: リソース管理とは別のトップレベル画面。
- **却下**: リソース管理に 6 番目のカテゴリを足す案。
- **根拠**: 出所（Harvest 経由）とスコープ（複数クラスター横断）が既存 20 パネル
  （接続済み 1 台の設定操作）と違う。同じグリッドに混ぜると「ここで設定変更できるのか」が
  判別できない。20 パネルという既存記述（`docs/IMPLEMENTATION.md` ほか 6 箇所）も無傷で済む。
- **代償**: ナビゲーションの項目が 1 つ増える。

### D3. 取り込むのは Grafana の UI ではなくデータ層

- **採った案**: ポータルが AMP を PromQL でクエリし、自前チャートで描く（AppSync → Lambda → AMP）。
  Grafana は管理者の深掘り先としてディープリンクで併存。
- **却下**: Grafana OSS を自前ホストして JWT で iframe 埋め込み。Grafana へのリンクのみ。
- **根拠**: F11 のとおり Amazon Managed Grafana の匿名アクセス不可は回避策で通す種類の制約では
  ない。Grafana OSS で埋め込むには `allow_embedding=true` と多くの場合 `cookie_samesite` の
  緩和が要り、**監視機能 1 つのためにポータル全体のセキュリティ姿勢を変えることになる**。
  データ層を取り込めば Cognito と AppSync の認可がそのまま効く。
- **代償**: Harvest 同梱ダッシュボードの作り込みを享受できない。ポータルに時系列描画の前例が <!-- allow:not-a-claim: Grafana を自前ホストしない選択の帰結であって、Harvest の機能不在の主張ではない -->
  無く（F1）、チャートライブラリ・8 言語の軸ラベル・ダークテーマの系列色・アクセシビリティが
  丸ごと新規コストになる。**v1 は 6〜8 枚に絞り、それ以上は Grafana に送る**（D19）。
- **再検討の引き金**: 自前チャートが 15 枚を超えたとき。そこまで来たら Grafana を正面から
  ホストするほうが総コストが低い可能性がある。

---

## 2. 収集と配置の決定

### D4. 拠点ごとの collector bundle + 中央への push

- **採った案**: 各拠点に Harvest + スクレイパを置き、拠点から中央の AMP へ片方向 HTTPS で
  `remote_write`。
- **却下**: 中央 1 台の Harvest から全クラスターの管理 LIF をポーリングする形
  （AWS 公式のクロスアカウント手順の素直な延長）。
- **根拠**: F4 により、どの構成でも「Harvest の `/metrics` を誰かがスクレイプして SigV4 で
  送る」1 ホップが必ず入る。**このホップを設計から落とすと動かない。** 中央集約型は、監視の
  ために中央から各拠点の管理 LIF への L3 到達性を作ることになり、オンプレ・他クラウドまで
  広げると攻撃面が便益に見合わない。
- **代償**: 拠点ごとに稼働物が増える。拠点の collector が死んだことを検知する仕組みが別に
  必要になる（D18 の「最終スクレイプ時刻」がその役目）。
- **関連**: AWS 公式の Transit Gateway + RAM 版は代替として文書に残す（D22）。

### D5. AWS 拠点は ECS Fargate、単一タスクに 2 種のコンテナ、arm64

- **採った案**: 1 タスクに Harvest poller × N + Prometheus agent。CPU アーキテクチャは arm64。
- **却下**: AWS 公式テンプレートの EC2 単騎。EKS。タスク分離 + サービスディスカバリ。
- **根拠**: EC2 単騎はクラスターを足すたびに 1 台を太らせる形でスケールしない。EKS は
  このリポジトリに K8s の運用資産が無い（Terraform は KNFSD のみ）。同一タスクなら agent が
  poller を `localhost:<prom_port>` で引けてサービスディスカバリが不要。arm64 は同一構成で
  約 20% 安い（§4 の単価）。
- **代償**: 1 タスクの vCPU / メモリ上限までしかクラスターを足せない。F12 の per-10-cluster
  指針に照らすと 1 タスクで 10 クラスター程度が上限で、超えたらタスクを増やす。
- **確度**: 上限の実測はしていない（assumption）。

### D6. `prom_port` を poller ごとに明示し、`port_range` を使わない

- **根拠**: `port_range` は poller の順序でポートが決まるため、`harvest.yml` の順序を変えると
  ポートが変わる。Prometheus は `instance` ラベルにポートを含むので、**データが消えたように
  見える**。マルチクラスタで poller を足し引きする前提と両立しない。
- **代償**: poller を足すたびにポート番号を人が決める。
- **確度**: documented（Harvest のエクスポータ設定ドキュメント）。

### D7. AWS 外拠点の資格情報は IAM Roles Anywhere

- **採った案**: X.509 証明書で一時資格情報を取得し、`remote_write` を SigV4 署名する。
- **却下**: 長期アクセスキー。
- **根拠**: AWS が ADOT + IAM Roles Anywhere でオンプレから AMP に取り込む形を公開している。
  **公開リファレンスに長期キーの手順を書くと読者がそのまま真似する。**
- **代償**: CA と証明書の配布・失効という PKI 運用が新規に要る。**拠点が 1〜2 個の PoC では
  これが最も重い部品になる。** PKI を持たない環境向けの注記と、その場合の最小権限
  （`remote_write` のみ、ワークスペース 1 個に限定）を文書に併記する。

### D8. Harvest イメージは公式レジストリのものを digest でピン留め

- **却下**: F13 の `rahulguptajss/harvest` をそのまま使う。タグでのピン留め。
- **根拠**: リポジトリの `supply-chain-security` は Actions の SHA ピン留めと依存の厳密ピンを
  求めている。**公開リファレンスが個人名前空間の暗黙 `latest` を引く形は、その規約と正面から
  矛盾する。** タグは差し替えられるので digest にする。
- **解決済み（2026-09-05、verified）**: レジストリは **`ghcr.io/netapp/harvest`**。
  レジストリ API で 34 タグを確認し、`YY.MM.n-1` の版と `-fips` 派生、`latest`、`nightly` が
  並んでいる。現行の安定版は **`26.08.0-1`**、index digest
  `sha256:5e92452cd8adbf4af5ef549f8cf046358326d3eff1aa11f819c3302e3e31c437`
  （`linux/amd64` = `sha256:027b4a24…`、`linux/arm64` = `sha256:3cafddb4…`）。
  **arm64 のマニフェストが存在するので D5 の arm64 選択は成立する。** この digest で実際に
  起動して収集できることを確認した（§9）。
  - `latest` は現時点で `26.08.0-1` と同じ index digest を指す。**それでも digest で書く**
    （`latest` は後から別の版を指す）。
  - **`cr.netapp.io` は使わない。** タグ一覧を引いたが応答が空だった。手掛かりとして挙がって
    いたが、出典として使える状態ではない。
- **陳腐化の注意**: この設計が参照している Harvest のドキュメントは 25.08 系だが、
  **実機で動かした版は 26.08.0-1**。実装時に 26.08 のドキュメントで読み直す
  （`port_range` の挙動、コレクタ一覧、コンテナの起動形はいずれも版に依存する）。

---

## 3. 保存と認可境界の決定

### D9. 保存先は AMP。分離の単位は「監視ドメイン」でワークスペース 1 個 = 1 ドメイン

- **採った案**: 監視ドメイン（拠点 / アカウント群のオーナー）ごとに AMP ワークスペースを 1 つ。
  ドメイン内の複数クラスターは `cluster` ラベルで区別。
- **却下**: 単一ワークスペース + Lambda での PromQL ラベル強制のみ。自前 Prometheus。
- **根拠**: **ラベルは書き込み側が自由に付けられる。** 拠点 A の collector が
  `cluster="domain-b-cluster"` を付けて `remote_write` すれば、単一ワークスペースでは A の
  データが B のクエリに混ざる。「Harvest が付ける cluster 名を信頼できるか」への答えは
  **信頼できない**で、信頼の根拠を作るには書き込み側 ID とデータの入れ物を 1 対 1 にする
  必要がある。つまり境界は**ワークスペース = IAM の書き込み権限**に置くのが唯一の硬い形
  （F10 が示すとおり、AMP のラベル上限機能はこの用途を満たさない）。
- **代償**: ワークスペースごとに固定費がかかり、**ドメイン横断の集約クエリができない**
  （Lambda 側でのマージ以外に手段が無い）。ドメイン数に比例して管理対象が増える。
- **用語**: 「テナント」と呼ばない。ポータルに顧客テナントは存在せず、
  `docs/ja/multi-tenant-design.md` の S3 AP によるファイル単位分離と混同されるため。
- **v1 の出荷形**: ワークスペース 1 個で出し、解決層は複数対応の形で作る。

### D10. AMP のラベル上限はコスト保護としての併用

- **根拠**: 認可境界にはならない（F10）が、あるドメインのシリーズ急増が課金を押し上げるのを
  抑える用途では有効。

### D11. 監視対象の登録簿は `portal-config.ts` の静的マップ

- **却下**: DynamoDB テーブル + 管理 UI。SSM Parameter Store。
- **根拠**: これは「どのワークスペースを読むか」という**認可境界の定義**であり、UI から編集
  できるようにすると**その編集画面自体が新しい権限昇格の面になる**。デプロイ時に固定されて
  いるほうが監査もしやすい。
- **代償**: クラスターや監視ドメインを足すたびにポータルの再デプロイが必要。
- **再検討の結果（R4 / R5、追記）**: **部分的に覆した。** 決定を書き換えず経緯を残す。
  - **覆した部分**: クラスター一覧は静的マップで持たない。**AMP に届いている `cluster` ラベルの <!-- allow:not-a-claim: ポータルが一覧を静的に持たず AMP のラベルから導出する設計の記述であって、ベンダーの機能不在の主張ではない -->
    値から導出する**（D33）。理由は、静的マップではオンプレ / 他クラウドのクラスターを
    UI に出す手段が無く（既存の `platform-discovery` は `fsx:DescribeFileSystems` で
    AWS の FSx for ONTAP しか列挙できず、`_PROBES` が空なので宣言しても `hidden` に入る）、
    クロスプラットフォームの要件を満たせないため。
  - **維持した部分**: **監視ドメイン → ワークスペースの対応はデプロイ時固定のまま**（D35）。
    ここが D9 の境界の実体なので、UI から編集できるようにすると境界が UI 操作で動く。
  - この分割ができたのは、**登録簿を「編集するもの」から「観測されるもの」に変えたため**。
    編集面を作らずに UI ディスカバリーの要件を満たせた。

### D12. 認可は `storage-admin` の再利用、エンドポイントは独立

- **採った案**: 表示条件は既存の `storage-admin`。ただし `adminQuery` に相乗りせず
  `metricsQuery` を新設する。
- **根拠**: 相乗りすると**後から認可を分離できない**。独立していれば、将来「メトリクスは
  読めるが設定は変えられない」ロールを足せる。
- **代償**: v1 ではその役割が表現できない。監視を運用チームに開きたくなった時点で、その人に
  設定変更権限も渡すことになる。
- **再検討の引き金**: 運用チームにメトリクスだけを見せたい要求が出たとき。

### D13. 認可境界の実測による確認

- **採った案**: 実装中に短命のワークスペースを 2 つ作り、**偽ラベルを書き込んで別ワークスペース
  のクエリに現れないことを実測**し、終わったら削除する。
- **却下**: 手順として文書化するだけ。
- **根拠**: 文書化だけは「検証していないものを検証したように見せる」形に最も近い。
  ワークスペースの削除は可逆で、試験規模の取り込みは費用として無視できる。
- **記録先**: 実行日・リージョン・使ったラベル・観測結果を design に書く。

---

## 4. 量とコストの決定

### D14. 有効化するコレクタの 7 オブジェクトへの限定

- **採った案**: Rest（cluster / node / svm / volume / snapmirror）+ RestPerf（node / volume）。
  既定の LUN / qtree / NFS クライアント / workload は有効化しない。ボリュームは
  **内部ボリューム（`_root` 等）を除く全ボリューム**を対象にする。
- **根拠**: 取り込み量 = カーディナリティ × スクレイプ頻度で、AMP のコストは取り込みが支配的。
  ボリュームをフィルタすると**トラブル時に「見たいボリュームだけ入っていない」が起きる**ため、
  絞るのはオブジェクト種別のほうにする。
- **代償**: LUN / SMB / NFS クライアント単位の切り分けができない。必要になったら
  そのオブジェクトだけを有効化し、**カーディナリティの増分を見積り直す**。
- **スクレイプ間隔**: Harvest 既定（性能系 60 秒 / 構成系 180 秒）から下げない。
- **確度**: ~~assumption~~ → **実測した（2026-09-05）。結論は維持、根拠は差し替え、
  オブジェクト名は訂正が必要**（§9）。
- **実測でわかった訂正点（3 つ）**:
  1. **ここに書いた 7 オブジェクトは Harvest のオブジェクト名と 1 対 1 で対応しない。**
     `Rest:Node` というコレクタは存在せず、ノードの数値は `RestPerf:SystemNode` や
     `RestPerf:*Node` から来る。実装時は Harvest 側の実際のテンプレート名で書き直す。
  2. **FSx for ONTAP ではボリュームの性能値が `KeyPerf:Volume` から来た**（`RestPerf:Volume`
     ではない）。`Rest` と `RestPerf` しか宣言していないのに `KeyPerf` が動いており、
     FSx for ONTAP が一部の perf カウンタを出さないことへの Harvest 側の対応と思われる。
     **「RestPerf を有効化する」という書き方では実際に動くコレクタを言い当てられない。**
  3. **既定の取り込み量の主因は NFS と Workload だった。** 既定では
     `RestPerf:NFSv3/4/41/42`（計 4,368 metrics）と `RestPerf:Workload` +
     `RestPerf:WorkloadVolume`（計 1,947）が動く。FSx for ONTAP の対応ダッシュボード表では
     NFS clients / NFS troubleshooting / Workload は「既定で無効」に分類されているが、
     **ダッシュボードが無効なだけでコレクタは動く。** 絞る対象はダッシュボードではなくコレクタ。
- **効果（実測ベースの再計算）**: 既定のまま 4 クラスターで取り込み **約 $158/月**、
  絞ると **約 $24/月**。**絞る判断がコストの本体**という当初の主張は、推測ではなく
  6.6 倍という測った差で裏づけられた。

### D15. コレクタは REST 系。ZAPI を「廃止済み」と書かないこと

- **根拠**: REST コレクタは ONTAP 9.12+ で検証済みとされ、FSx for ONTAP では REST 系を選ぶ。
  **ZAPI の EOA は無期限に延期された**（CPC-00410, 2024-06）。Harvest の古い版のドキュメントは
  今も「9.13.1 で EOA」と書いているので、それを引用すると**それ自体が誤情報になる**。
- **確度**: documented（Harvest の rest-strategy）。

### D16. 保持は単一ワークスペース 400 日。2 段構成にしない

- **却下**: raw 14 日 + ダウンサンプル 400 日の 2 ワークスペース構成。
- **根拠**: F9 のとおり AMP の保持はワークスペース単位で一律なので、2 段にすると
  **ワークスペース数がドメイン × 2 になり、D9 の境界管理も倍になる**。recording rule の出力を
  別ワークスペースへ送る経路は AMP のルーラー単体では組めず、拠点側に二重書き込みをさせるか
  中間の書き戻し役が要る。
- **代償**: 高解像度データを 400 日保持するのでストレージ費がかかる。D14 で絞った規模では
  無料枠付近に収まる見込み（§4 の見積り）。
- **再検討の引き金**: ストレージ費を実測して想定を超えたとき。そのとき 2 段に移る。

### D17. 参照構成は「1 AWS 拠点（3 クラスター）+ 1 AWS 外拠点（1 クラスター）」

- **根拠**: クロスプラットフォームが要件なので、**参照構成に AWS 外の拠点が 1 つ無いと
  「対応している」と書けない**。

### 単価（Pricing API、ap-northeast-1、publicationDate 2026-08-31、取得日 2026-09-05）

| 項目 | 単価 |
|---|---|
| AMP 取り込み | 2B サンプルまで $0.90 / 10M、以降 250B まで $0.35 / 10M |
| AMP ストレージ | 最初の 10 GB-Mo 無料、以降 $0.03 / GB-Mo |
| AMP クエリ | $0.10 / 10 億クエリサンプル |
| AMP マネージドコレクタ | $0.04 / collector-hour（本構成では不使用） |
| Fargate x86 | $0.05056 / vCPU-h、$0.00553 / GB-h |
| Fargate arm64 | $0.04045 / vCPU-h、$0.00442 / GB-h |

> 0〜40M サンプルの区間にさらに低い階層が存在するが、**その単価は読んでいない**。
> 下の概算は全量を $0.90 / 10M で計算しているので、実費はこれ以下になる。

### 概算（D17 の参照構成、**assumption。実測ではない**）

前提: 4 クラスター、各 50 ボリューム、1 クラスターあたり約 5,000 アクティブシリーズ、
D14 の間隔 → 約 120M サンプル / 月 / クラスター。

| 項目 | 概算 / 月 |
|---|---|
| AMP 取り込み（480M サンプル） | 約 $43 |
| AMP ストレージ（400 日で定常 約 12.6 GB） | 約 $0.1 |
| AMP クエリ（レンジ上限あり） | $0.1 未満 |
| Fargate arm64 0.5 vCPU + 1 GB × 730 h | 約 $18 |
| VPC エンドポイント（4 本、1 AZ） | **未取得** |

**シリーズ数が全体を決めるので、この表の確度はシリーズ数の確度と同じ。**
実機の `/metrics` を数えるまでは概算である（tasks の最初の検証項目）。

---

## 5. 出口経路とネットワークの決定

### D18. コレクタの出口は Interface VPC Endpoint

- **採った案**: `aps-workspaces` の Interface Endpoint + ECR（`api` / `dkr`）+ CloudWatch Logs +
  S3 Gateway Endpoint。
- **却下**: NAT Gateway。パブリックサブネット + パブリック IP。
- **根拠**: NAT Gateway は**タスクに無制限のアウトバウンドを与える**。エンドポイントなら宛先が
  AMP と ECR に限定され、監視エージェントが他のどこにも出られないことが構成で保証される。
  パブリック IP を持つタスクを ONTAP の管理 LIF に届くサブネットに置く形は、公開
  リファレンスとして推奨しない。
- **代償（未解決）**: **Interface Endpoint は 4 本必要で、AZ ごとに時間課金がある。本数の分だけ
  NAT Gateway より高くなる可能性がある。** 単価を取得していないので確定していない。
  加えて、**その VPC に既に NAT Gateway が別用途で存在する場合、NAT を使う増分費用は
  データ処理分だけになる**ので、既存構成によって最適解が変わる。
- **再検討の引き金**: 単価取得後に (b) が NAT より高いと判明したとき。そのとき
  「境界を構成で保証する価値」と差額を並べて再判断する。**安いほうを黙って選ばない。**
- **単価取得後の再判断（2026-09-05、verified。決定は維持）**: 単一 AZ では
  **エンドポイントのほうが安く、かつ宛先も限定される**ので、トレードオフは存在しなかった。
  単価（Pricing API、ap-northeast-1、publicationDate 2026-08-31 / 2026-09-04、取得日 2026-09-05）:

  | | 時間 | データ処理 | 4 本 / 1 AZ の月額（730 h） |
  |---|---|---|---|
  | Interface VPC Endpoint | $0.014 / endpoint-h | $0.01 / GB | **$40.88** |
  | NAT Gateway | $0.062 / h | $0.062 / GB | $45.26（1 台） |

  - データ処理も **$0.01 対 $0.062 で 6 倍差**。取り込みトラフィックは AMP 向けに継続的に
    出ていくので、ここも効く。
  - **AZ を増やすと逆転する**: 2 AZ で冗長化すると endpoint は 8 本相当で $81.76 になり、
    NAT 2 台の $90.52 とほぼ並ぶ。**AZ 数が判断を変える**ので、参照構成では 1 AZ を前提に
    書き、冗長化する場合の分岐点を併記する。
  - **既に別用途の NAT Gateway がある VPC では、NAT を使う増分費用はデータ処理分だけ**という
    観点は残る。ただしその場合もアウトバウンドが無制限になる点は変わらない。

### D19. `metricsQuery` Lambda は VPC 外、クエリのレンジと解像度に上限

- **根拠**: AMP のクエリ API は AWS の公開エンドポイントで、この Lambda は ONTAP と話さない。
  VPC に入れると NAT / エンドポイントの費用と ENI の遅延を負う（`platform-discovery` と同じ形）。
  クエリサンプルは課金対象なので、UI のバグや連打で費用が伸びる形にしない。
- **上限超過時の挙動**: **黙って丸めず、拒否してその旨を返す。** 黙って粗くすると、
  見ている人が粗いことに気づけない。

---

## 6. 表示と穴の決定

### D20. 横断オーバービュー → クラスター単位のドリルダウンの 2 段

- **採った案**: オーバービューは 1 クラスター 1 行の表（クラスター名 / 拠点 / 到達状態 /
  **最終スクレイプ時刻** / 主要な 2〜3 指標）。チャートはドリルダウン側に置き、v1 は 6〜8 枚
  （クラスター・ノードの CPU / レイテンシ / IOPS / スループット、ボリューム容量トレンド、
  SnapMirror ラグ）。
- **根拠**: 「横断できる」ことが要件なので、**横断が見える画面が 1 枚も無いと要件を満たさない**。
  オーバービューにチャートを並べるとクエリサンプルが表示のたびに線形に増える。
- **最終スクレイプ時刻を必須にする理由**: Prometheus 由来の画面で最も危険な誤読は、
  **収集が止まっているのにグラフが平坦な線として見える**こと。データが古いことを画面が
  言わないなら、その画面は嘘をつく。

### D21. チャートは recharts と、表形式の代替表示の併置

- **却下**: uPlot、Chart.js、自前 SVG。
- **根拠**: 既存コンポーネントが React + CSS 変数で完結しており、命令的ライブラリを入れると
  テーマ切替（`[data-theme="dark"]`）と 8 言語の軸ラベルを自分で配線することになる。
  既存のテスト形（vitest + `src/lib/dispatch` のモック）にも宣言的コンポーネントが乗る。
- **代償**: バンドルが増える（d3 のサブモジュール依存）。データ点数が多いと uPlot に劣る。
  v1 は 6〜8 枚・60 秒間隔・レンジ上限つきなので点数は問題にならない見込み（assumption）。
- **アクセシビリティ**: 色と位置だけで情報を伝える要素を足さない。系列色は `:root` と
  `[data-theme="dark"]` の**両方**に新規トークンとして定義する。

### D22. 埋めない穴の明記

- **F5 の非サポート 10 種のうち 8 種**（Disk / Shelf / Power / MetroCluster / Headroom /
  Health / External Service Operation / MAV Request）は、ハードウェアが AWS 管理であるか
  当リポジトリで未使用のため、**FSx for ONTAP では埋める必要がない**。
- **`ONTAP: S3 Object Stores`** は ONTAP の S3 オブジェクトストアを有効にしたときだけの
  特殊ケースとして例外扱い。**FSx for ONTAP S3 Access Points とは別物**（F6）。
- **`ONTAP: File Systems Analytics (FSA)`** は埋めない。有効化のコストと FSx for ONTAP での可否が別調査。
- **FSx for ONTAP S3 AP の CloudWatch 監視**は F14 のとおり**未確認**。確認手順を書き、
  存在しなければ「不在」として記録する。FPolicy 由来の自前メトリクスで代替する案は却下
  （新しいメトリクス生産者を増やすとスコープと姉妹リポジトリとの住み分けが崩れる）。

### D23. EMS は既存の ONTAP REST 直叩きの維持

- **却下**: Harvest の `Ems` コレクタを有効化する。
- **根拠**: ポータルの `getEmsEvents` は既に稼働していて、`ClusterManager` は「いま何が
  起きているか」を見るパネルなので Prometheus を経由する意味がない。Harvest 経由を足すと
  **同じイベントが 2 経路になり二重計上とアラート重複を招く**。
- **姉妹リポジトリの EMS webhook 経路**はアラート用途としてあちらに残す。

### D24. アラートは v1 の対象外

- **根拠**: 通知経路は姉妹リポジトリの CloudWatch Alarm / EMS webhook が既にある。
  ここに 3 本目を作ると同じ事象が 3 経路で鳴く。
- **文書に書くこと**: 対象外であること、理由、**どこを見ればアラートがあるか**。

---

## 7. 成果物と品質ゲートの決定

### D25. 置き場所は `infrastructure/harvest-metrics/`

- **却下**: `operations/OPS7-*` として新パターンにする。
- **根拠**: 1 パターンのデプロイ単位ではなく、複数拠点にまたがる監視基盤なので、
  `operations/` の「1 ディレクトリ = 独立してデプロイ可能な 1 パターン」に収まらない。
  KNFSD と同じ扱い。

### D26. 配布形は 3 点セット

1. AWS 拠点向け: CloudFormation / SAM（ECS Fargate + Prometheus agent + Secrets Manager 参照）。
   `cfn-lint` と `cfn-guard` の対象。
2. AWS 外拠点向け: `docker-compose.yml` と K8s マニフェスト。
3. 3 つが共有する `harvest.yml` テンプレート（D6 に従い `prom_port` を明示）。

### D27. PromQL のメトリクス名への契約チェックの新設

- **根拠**: Harvest 側でメトリクス名が変わると、**チャートは壊れずに空になる**。
  エラーも型エラーも出ない。これはポータルで既に一度出荷された失敗の型
  （action-parameter の不一致）と同じ構造で、**型が届かない境界の 3 本目**。
- **形**: 実機の `/metrics`（または `bin/harvest grafana metrics` の出力）から取ったメトリクス名の
  スナップショットを repo に置き、ポータルが使う名前がその集合に含まれることを `make drift` で
  検査する。含まれなければ fail。
- **代償**: Harvest を上げるたびにスナップショットの更新が要り、忘れると偽陽性で CI が止まる。
  更新手順を `Makefile` のターゲットにする。
- **併せて**: `docs/CONTRIBUTING-UI.md` 冒頭の「型が届かない境界」の表（現在 2 行）に
  **React → Prometheus** の行を足す。

### D28. ONTAP 資格情報はクラスターごとの `fsxadmin-readonly` ユーザー

- **却下**: `fsxadmin` を全クラスターで共用する。
- **根拠**: F7 のとおり AWS が Harvest 用途に名指しで推奨している。`fsxadmin` を横に広げると、
  1 つの誤った資格情報がロックアウトを起こし、**そのクラスターの設定操作（ポータルの
  20 パネル）も同時に止まる**。監視の失敗が操作系を落とすのは受け入れられない結合。
- **付随して必須**: secret はクラスターごとに 1 つ。認証失敗時は指数バックオフ +
  サーキットブレーカ（連続失敗でそのクラスターのポーリングを止め、リトライで穴を掘らない）。
- **解決済み（2026-09-05、verified）**: F8 の矛盾は**ドキュメント側の誤り**だった。実機
  （FSx for ONTAP、ONTAP 9.18.1P3D1）で確認した内容は §9。要点は 3 つ。
  `fsxadmin-readonly` はクラスタースコープのロールとして実在する / そのロールのユーザーを
  `POST /api/security/accounts` で作れる（HTTP 201）/ そのユーザーで読み取りは通り、
  書き込みとアカウント作成は 403 で拒否される。**ゆえに縮退（`fsxadmin` 前提）は不要。**
- **旧記述（残す）**: F8 の矛盾があるため、**実機で `fsxadmin-readonly` ユーザーを作れることを
  確認していない**。作れない場合は `fsxadmin` 前提に落ち、そのときバックオフと
  ロックアウト復旧手順（`aws fsx update-file-system --ontap-configuration FsxAdminPassword=...`。
  ONTAP 認証を必要としない）が必須になる。

### D29. Transit Gateway 版の代替としての記載

- **根拠**: 読者は AWS 公式手順を先に見て来る可能性が高く、**触れずに別の形を出すと
  「公式手順を知らないのか」になる**。
- **書き方**: どちらがどの条件に向くかを対称に書く。TGW 版はすでに TGW がある単一組織の
  AWS 拠点なら追加部品が少ない。push 版は AWS 外を含む場合・組織をまたぐ場合・中央から
  各拠点への到達性を作りたくない場合に向く。**優劣として書かない。**

### D30. 姉妹リポジトリのファイルは変更しない

- `FSx-for-ONTAP-Observability-integrations` の `docs/en/native-alternative-matrix.md` は
  「System Manager の性能ビューの代替 = CloudWatch ダッシュボード」と位置づけている。
  Harvest 経路は**同じ問いへの 2 つ目の答え**なので、あちらに「CloudWatch 経路と Harvest 経路の
  選び方」の追記が必要になる。**その必要性をここに記録し、あちらのファイルはこの作業で
  変更しない。**
- こちら側の「選び方ガイド」に住み分けを書く。

### D31. `docs/observability-design.md` の非目標記述の改訂

- 現状 Prometheus / Grafana を Theme N の非目標として列挙している。放置すると
  「対象外」と書いた文書と Prometheus を使う文書が同居する。
- **削除ではなく、Theme N 時点の非目標だった旨と範囲が変わった旨を書き足す**（経緯を残す）。

---

## 8. UI からの有効化とディスカバリーの決定（R4 / R5）

この節は D11 の一部を覆している。経緯は D11 の追記にある。

### F15〜F18. この節が依拠する追加の事実

| # | 事実 | 確度 | 出典 |
|---|---|---|---|
| F15 | ポータルの既存トグル（AI エージェント / セマンティック検索 / マルチモーダル / チャット履歴 / FolderWatch）は**1 つも AWS リソースを変えない**。`PortalSettingsTable`（DynamoDB）に文字列を書き、UI のセクション表示とハンドラ側の実行時ゲートに効くだけ | verified | `AiSettingsManager.tsx`、`functions/resource-management/handler.py` の `_get/_update_portal_settings`、`amplify/backend.ts` の `PortalSettingsTable` |
| F16 | **Smart Routing はトグルから表示専用に降格された。** コードに理由が書かれている: 誰も読まない値を書いていたので何も変わらず、**かつ配線されていたら UI からマルチテナントのスコープ境界を広げられるようになっていた** | verified | `AiSettingsManager.tsx` の該当節のコメント |
| F17 | ポータルの Lambda は `ecs:*` / `aps:*` / `secretsmanager:CreateSecret` / `fsx:Create*` / `fsx:Update*` / `ssm:*` を**一切持たない**。`secretsmanager:GetSecretValue` は 1 本の secret に限定。`least-privilege-arns.test.ts` / cdk-nag / IAM Policy Validation ワークフローがこれを守っている | verified | `amplify/backend.ts` の各 Lambda の IAM | <!-- allow:not-a-claim: 自リポジトリの IAM 設定の記述であってベンダーの機能不在の主張ではない。3 つのゲートが機械的に守っている -->
| F18 | 既存の確認作法は 2 系統。可逆な操作は `window.confirm`（ARP の一括有効化は**対象件数を文面に埋める**）、不可逆な操作は専用ダイアログ + `acknowledgeIrreversible`（SnapLock / Snapshot ロック） | verified | `ArpAdminManager.tsx`、`SnaplockConfirmDialog.tsx` の呼び出し側 |
| F19 | Harvest の設定のホットリロード（`harvest.yml` の書き換えだけで poller が増える）を裏づける記述は**見つからなかった**。推奨構成は poller-per-container で、poller の追加はプロセスを起こすこと | open | Harvest の containers / configure-harvest-basic を確認。**無いことの証明ではない**（U8） |

### D32. 機能トグルは表示と実行時ゲートのみ

- **採った案**: `PortalSettingsTable` に `harvestMetricsEnabled` を追加（既定 `false`、
  `storage-admin` のみ）。既存 5 キーと同じ経路。**AWS リソースは変えない。**
- **却下**: ECS サービスの `desiredCount` を 0/1 する案、AMP ワークスペースの作成まで行う案。
- **根拠**: F15 が確立した語彙（切ってもリソースは変わらない）を壊さない。F17 のとおり
  ポータルは書き込み権限を持たず、それを越える最初の変更にしない。FolderWatch のトグルが
  既に「発行元が存在するという管理者の宣言」という意味で使われており、Harvest では
  「この拠点の collector が動いていて AMP に届いているという宣言」がそのまま当てはまる。
- **代償（隠さない）**: **無効化してもコストは止まらない。** Fargate と AMP の取り込みは
  走り続ける。パネルに「無効化は表示を止めるだけで、収集と費用は止まらない。止めるには
  この手順」と明記することを条件にする。
- **`desiredCount` 案を採らなかった主因**: 止まるのは AWS 拠点の collector だけで、
  オンプレ拠点は止まらない。**拠点によって「無効」の意味が変わるトグルは UI として嘘に近い。**
- **解消の見込み**: フェーズ 2（D37）が入れば台帳から行を消すことで poller が止まり、
  費用も止まる。この代償はフェーズ 2 で消える。

### D33. クラスター一覧は AMP のラベル値から導出

- **採った案**: AMP に届いている `cluster` ラベルの値を源にし、既存の FSx for ONTAP インベントリと
  突き合わせて 3 状態を出す。

  | 状態 | 意味 | 源 |
  |---|---|---|
  | 監視中 | メトリクスが届いている | AMP のラベル値 |
  | 未監視 | FSx for ONTAP としては存在するが、メトリクスが来ていない | インベントリのみ |
  | 未確認 | 宣言されているが何も答えない | 既存の `hidden` + `reason` 契約 |

- **却下**: `platform-discovery` のみを源にする案（AWS の FSx for ONTAP しか見えず、
  クロスプラットフォームの要件を満たさない）。手動登録 UI（編集面を作ることになり F16 に反する）。
- **根拠**: 拠点が push している以上、**届いているクラスターは必ず AMP が知っている**。
  プローブも資格情報も到達性も要らず、オンプレでも他クラウドでも同じように見える。
- **代償**: オーバービューの初回表示に AMP のクエリが 1 本増える。加えて
  **「届いていない」と「クラスターが無い」を区別できない**——収集が止まっている拠点は
  「未監視」に見える。だから D20 の最終スクレイプ時刻がここでも同じ役目を果たす。

### D34. 導出した一覧は永続化しない

- **採った案**: 都度導出し、react-query の `staleTime` でのみキャッシュする
  （既存の `PlatformSelector` と同じ 5 分）。
- **却下**: DynamoDB にキャッシュする案。
- **根拠**: 保存すると**退役したクラスターが一覧に残り続け、誰も消さない**。

### D35. UI から編集できるものと、デプロイ時固定のものの線

| 対象 | 扱い |
|---|---|
| `harvestMetricsEnabled` | UI から変更可 |
| 表示するクラスターの絞り込み | UI から変更可（`sessionStorage`。既存の `activePlatform` と同じ） |
| **監視ドメイン → AMP ワークスペースの対応** | **デプロイ時固定。UI に表示するが編集させない** |
| AWS 外拠点の宣言 | 同上 |
| secret 名（v1） | 同上 |

- **根拠**: F16 の前例がそのまま当てはまる。対応表を UI から編集できるなら、そのボタンを
  押せる人は自分のドメインを他ドメインのワークスペースに向けられる。**D9 の境界の根拠が
  UI 操作で崩れる。**
- **「v1 はワークスペースが 1 個なので危険が無い」への答え**: 危険が無いのは今だけで、
  2 個目を足した瞬間に危険になる。そのとき UI から機能を取り上げるのは、最初から入れないより難しい。
- パネルは**固定である旨とどこで設定するかを表示する**（制御するふりをしない）。

### D36. 未監視のクラスターに対して v1 がすること

- **採った案**: 監視対象にする**手順を表示するだけ**（`fsxadmin-readonly` ユーザーの作り方、
  secret 名、その拠点の collector に poller を足す方法）。
- **却下（v1 では）**: UI から監視を開始する案 → フェーズ 2（D37）。
- **却下（恒久）**: UI で ONTAP のパスワードを入力させる案（D38）。
- **根拠**: 「選択」を「監視対象の切り替え」ではなく**「見つかったものの一覧と、その状態と、
  次にすべきこと」**として実装すれば、ディスカバリーは UI 上で起き、要件は満たせる。

### D37. フェーズ 2（UI からの監視開始）の受け入れ形

**v1 の実装対象ではない。** ただし v1 の形を縛るので、design に節として書く（D40）。

- 監視対象台帳（DynamoDB）をポータルが書き、**拠点の collector タスク内のスーパーバイザが
  定期的に読んで poller プロセスを起動 / 停止する**（pull）。
- **却下**: ポータルが ECS を操作する案（AWS 拠点にしか効かず、オンプレ用に 2 本目の経路が
  必要になる。**2 つ持つと片方だけが保守される**）。IaC 再デプロイで反映する案。
- **この案の決定的な利点**: **ポータルが AWS リソースを変える権限を持たないまま監視を <!-- allow:not-a-claim: ポータル側の権限設計の記述であってベンダーの機能不在の主張ではない -->
  開始できる。** 書くのは DynamoDB の行だけで、既存の `PortalSettingsTable` と同じ権限の範囲。
  制御の向きが拠点からの pull なので、D4 の「中央から拠点への経路を作らない」と一致する。
- **前提**: F19 のとおりホットリロードは確認できていないので、**スーパーバイザを新規に書く**
  （台帳を読み、差分だけ poller を起こす / 落とす、`prom_port` を台帳の行から決定論的に割り当てる）。
- **D6 との相互作用**: ここで `port_range` を使っていたら、poller の増減でポートが動いて
  `instance` ラベルが変わり、**データが消えたように見える**。D6 の判断がそのまま効く。
- **代償**: 反映が即時でない（pull 間隔ぶん遅れる）。UI は「監視開始を要求した」と
  「メトリクスが届き始めた」を**別の状態として出す**。D33 の導出設計と噛み合うので、
  届き始めれば自動で「監視中」に変わる。

### D38. 資格情報は値ではなく参照の登録

- **採った案**: ポータルは **secret の名前 / ARN だけ**を受け取る。値は管理者が
  Secrets Manager 側で作る。**ポータルは値を一度も持たない。** <!-- allow:not-a-claim: ポータルが secret の値を扱わない設計の記述であってベンダーの機能不在の主張ではない -->
- **却下**: ポータルが ONTAP のユーザー名とパスワードを受け取って Secrets Manager に書く案。
- **根拠**: 却下案は `secretsmanager:CreateSecret` / `PutSecretValue` を初めて与えるだけでなく、
  **パスワードがブラウザ・AppSync・Lambda のログ・スクリーンショットを通過する経路を作る**。
- **UX への影響**: 入力欄が「パスワード」から「secret 名」に変わるだけで、
  発見 → 登録 → 監視開始という流れは保てる。
- **代償**: 手順が 2 か所にまたがる（ポータルで secret 名、Secrets Manager で値）。
  **「UI で完結する」という当初の狙いからは 1 歩後退している。** これが今回の最大の妥協点。
- **鶏と卵（いずれの案でも残る）**: `fsxadmin-readonly` ユーザーの作成は ONTAP 側の操作で、
  ポータルは監視対象クラスターの ONTAP にまだ資格情報を持っていないので、そのクラスターに <!-- allow:not-a-claim: 導入手順の順序に由来する状態の記述であってベンダーの機能不在の主張ではない -->
  ユーザーを作れない。**UI で完結しえない部分がここに 1 つ残る。**

### D39. 監視開始は可逆な操作としての確認

- **採った案**: `window.confirm` に対象クラスター名と**推定シリーズ数・月額増分**を埋める
  （F18 の ARP 一括有効化と同型）。台帳の行に**誰がいつ有効化したか**を記録する。
- **却下**: 確認なし。SnapLock 系の専用ダイアログ + `acknowledgeIrreversible`。
- **根拠**: 監視開始は可逆。**不可逆操作の語彙を借りると「取り消せない」という読者の期待を
  壊す。** ARP が `window.confirm`、SnapLock が専用ダイアログという既存の区別が正しい。
  課金が増える操作に主体の記録が無いのは避ける。

### D40. UX の由来を製品名で書かない

- この UX の形（資格情報を登録し、リソースを発見し、監視を開始する）は特定ベンダーの
  管理 SaaS 製品の操作順序に由来する。**その製品名は成果物にも判断記録にも書かない**
  （このリポジトリの規約で、該当する言及は native な仕組みに読み替える）。
- **書き方**: 「登録 → ディスカバリー → 監視開始」という一般的な操作の順序として書く。
- フェーズ 2 の記述は、**節の冒頭に「v1 の範囲外」と明記する**（実装済みと誤読させない）。

---

## 9. フェーズ 0 の実測記録（2026-09-05）

### 測定環境

| 項目 | 値 |
|---|---|
| 対象 | FSx for ONTAP ファイルシステム 1 台（検証用、ap-northeast-1） |
| ONTAP | NetApp Release 9.18.1P3D1 |
| 規模 | ボリューム 35、SVM 6、ノード 2、アグリゲート 1、FlexCache 2、SnapMirror 関係 0 |
| Harvest | `ghcr.io/netapp/harvest@sha256:5e92452c…`（26.08.0-1、linux/arm64） |
| コレクタ | `Rest` + `RestPerf` を宣言、**テンプレートの絞り込みなし**（既定） |
| 到達経路 | 管理 LIF はプライベートで手元から届かないため、同一 VPC の SSM 管理インスタンス経由で `AWS-StartPortForwardingSessionToRemoteHost` でトンネルし、コンテナ側は素の TCP プロキシで 443 に見せた。TLS はホスト名が一致しないので `use_insecure_tls: true`。**この 1 点は本番構成と異なる**（本番では poller が管理 LIF に直接届く） |

### 測定結果

| 測ったもの | 値 |
|---|---|
| `/metrics` のシリーズ行数（既定） | **11,617** |
| 異なるメトリクス名 | **813** |
| `Rest`（構成系、既定 180 秒）の metricsExported 合計 | 3,367 |
| `RestPerf` ほか（性能系、既定 60 秒）の metricsExported 合計 | 9,031 |
| ボリューム 1 本あたりのシリーズ | 約 69（`Rest:Volume` 1,532 + `KeyPerf:Volume` 894 / 35 本） |
| 上位の寄与 | `Rest:Volume` 1,532 / `RestPerf:NFSv41` 1,410 / `RestPerf:NFSv4` 1,242 / `RestPerf:NFSv3` 1,062 / `RestPerf:WorkloadVolume` 1,035 / `RestPerf:Workload` 912 / `KeyPerf:Volume` 894 |

メトリクス名の一覧は `infrastructure/harvest-metrics/metrics-snapshot.txt` に保存した
（**名前のみ。ラベル値を含まないので、クラスターもアカウントも特定できない**）。D27 の契約
チェックの源にする。

### 実測に基づくコスト（30 日換算、単価は §4）

| 構成 | 1 クラスターの月間サンプル | 4 クラスターの取り込み |
|---|---|---|
| Harvest 既定 | 約 438.6M | **約 $158 / 月** |
| D14 の絞り込み | 約 66.3M | **約 $24 / 月** |

保持 400 日のストレージは 4 クラスターで定常約 7.1 GB、**10 GB-Mo の無料枠内**（$0）。

**§5 の旧概算（1 クラスター約 5,000 シリーズ / 120M サンプル）は低すぎた。** 既定では
約 3.6 倍、絞った状態でも計算の内訳が違う。**結論（絞る）は変わらず、根拠が推測から実測に
変わった。**

### S3 Access Points の CloudWatch メトリクス（U3、実行した観測）

`aws cloudwatch list-metrics --namespace AWS/FSx --region ap-northeast-1` を実行した。
<!-- allow:naming: CloudWatch 名前空間の literal -->

- 返ってきた**異なるメトリクス名は 33 個**。内訳は容量（`StorageCapacity`、`StorageUsed`、
  `LogicalDataStored`、`FilesUsed` ほか）、IO（`DataRead/WriteBytes`、`*Operations`、
  `*OperationTime`、`MetadataOperations`）、ネットワーク、ディスク、キャパシティプール、
  ファイルサーバー側の利用率。
- **`s3` / `object` / `accesspoint` / `bucket` を名前に含むものは 1 つも無い。**
- 同じアカウント・同じリージョンに **S3 Access Point のアタッチメントが 22 件、すべて
  `AVAILABLE`** で存在する状態での観測。「S3 AP を作っていないから出ないのだろう」という
  読みは成り立たない。

**残る留保を明示する**: `list-datapoints` ではなく `list-metrics` なので、返るのは
**直近にデータポイントが publish されたメトリクス**である。仮に S3 AP のリクエストメトリクスが
存在しても、対象期間に S3 AP へのリクエストが 1 件も無ければ一覧に現れない。したがって <!-- allow:not-a-claim: 「機能として存在しない」という言い方を否定するために引用している行 -->
**「機能として存在しない」ではなく「S3 AP が 22 件ある環境で、S3 に関するメトリクス名が
1 つも publish されていない」**が観測できたことである。design にはこの言い方で書く。

### 検証の手順そのものについて踏んだ罠（3 件、記録に残す価値がある）

**1. 読み取り専用ロールの検証を、存在しない対象で行うと 400 が返って「書き込みが通った」に
見える。** `fsxadmin-readonly` のユーザーで `POST /api/storage/volumes` を**架空の SVM 名**で
叩いたところ、403 ではなく **400「SVM が存在しない」**が返った。つまり ONTAP は認可より先に <!-- allow:not-a-claim: ONTAP が返したエラーメッセージの引用であって、ベンダーの機能不在の主張ではない -->
`svm.name` を検証する。**実在する SVM 名**で同じ呼び出しをすると **403「not authorized for
that command」**になった。

> **架空の対象で拒否を測ると、測っているのは認可ではなく入力検証。** 成功するはずの
> コントロール（実在する対象）を同じセッションに置いて初めて、拒否が認可のものだと言える。

**2. 検証スクリプトに追記して再実行し、自分の測定を無効化した。** アカウント作成と
パスワード生成を含むスクリプトに検査を追記して再実行したため、2 回目は新しいパスワードを
生成する一方でアカウント側は 1 回目のパスワードを保持し、**すべての呼び出しが 401 になった**。
これを「読み取り専用が効いた」と読むこともできた。

> **1 回で完結しないスクリプトに追記して再実行しない。** 状態を作る処理と検査する処理が
> 同じスクリプトにあるなら、追記した検査は前回の状態と噛み合わない。

**3. 後片付けの識別子を間違え、消したつもりのアカウントが残った。** `DELETE
/api/security/accounts/<owner>/<name>` の `<owner>` はクラスター名ではなく **UUID**。
クラスター名を渡すと 404 が返り、それを「もう無い」と読み違えた。**一覧を引き直して初めて
残存が分かった。** 削除は、削除の応答ではなく**一覧の再取得**で確認する。

### 後片付け

検証で作ったものは残していない。probe アカウント 2 件は削除して一覧で不在を確認、
コンテナとネットワークは削除、**fsxadmin の資格情報を含む `harvest.yml` は削除**、
SSM のトンネルは終了。リポジトリに追加したのは `metrics-snapshot.txt` のみ。

---

## 10. 根拠の再確認（2026-09-05、指摘を受けて実施）

**きっかけ**: 「U3 は AWS ドキュメントで確認したのか。クリティカルな内容なのに、ドキュメントの
状況への言及も、AWS サポートへの確認も、機能改善要望もせずに決めているのは疑問」という指摘。
**正しい指摘だった。** U3 でやっていたのは 2 ページに対する `S3` という 2 文字の選択的検索で、
これは「無い」の根拠にならない。同じ弱さを持つ主張を全部洗い直した結果を以下に置く。

### 10.1 訂正 1: F8「2 ページが矛盾している」は誤り

**何を間違えたか**: `create-new-ontap-users.html` を**読んでいなかった**。検索結果の
スニペットにあった 1 文（「ファイルシステムレベルで指定できるロールは `fsxadmin` のみ」）を
根拠に「2 ページが矛盾している」と書いた。ページを開くと確認したのは 1 度目の選択検索が
`No matches` を返したときだけで、そこで読むのをやめていた。

**全文を読んだ結果**:

- その 1 文は `-role` パラメータの説明の中にある。
- **同じページが、`fsxadmin-readonly` を割り当てるユーザー作成例を載せている**
  （`security login create -user-or-group-name new_fsxadmin -application ssh
  -authentication-method password -role fsxadmin-readonly`）。
- さらに**NetApp Harvest 用の読み取り専用ユーザーを作る例が名指しで載っている**:
  `security login create -user-or-group-name harvest2-user -application ssh
  -role fsxadmin-readonly -authentication-method password`、
  「NetApp Harvest アプリケーションが性能と容量のメトリクスを収集するために使う読み取り専用の
  ファイルシステムユーザー」という説明つきで、Harvest / Grafana のページへのリンクもある。
- `security login show` の出力例にも `new_fsxadmin ssh password fsxadmin-readonly` の行がある。

**したがって**: 矛盾は 2 ページ間ではなく**1 ページの中の不整合**で、`-role` の説明文が
古いか不正確なだけ。そしてこの用途（Harvest 用の読み取り専用ユーザー）は**最初から
ドキュメントに書かれていた**。D28 は「実測で分かった」ではなく**「ドキュメントに書かれており、
実測でも確認した」**が正しい。私は根拠を弱く引いた上に、存在しない矛盾を作っていた。

**この訂正から出た新しい発見（実装に効く）**: ドキュメントの例は
**`-application ssh`** である。Harvest の REST コレクタは HTTP を使うので、
**例をそのまま実行すると REST API で認証できないユーザーができる。**
§9 の実測では `applications: [{application: "http", ...}]` で作って REST が通った。
`harvest.yml` が REST コレクタを使う構成では `http`（必要なら `ssh` と併記）が必要。

### 10.2 訂正 2: U3 の根拠を、ドキュメントの全文読みに置き換えた

**やり直した内容**（すべて全文取得）:

| 読んだもの | 分かったこと |
|---|---|
| [Monitoring with Amazon CloudWatch](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/monitoring-cloudwatch.html) | メトリクスは**次元によって 4 分類**と書かれ、実際に列挙されているのは File system / File server / Detailed file system aggregate / Detailed file system / Volume / Detailed volume。**アクセスポイントを次元とする分類は無い。** 「すべての CloudWatch メトリクスは `AWS/FSx` 名前空間に publish される」と明記。ページの目次も Accessing / console / File system metrics / Second-generation file system metrics / Volume metrics のみ <!-- allow:naming: CloudWatch 名前空間の literal --> |
| [File system metrics](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/file-system-metrics.html) | 全メトリクスの次元は `FileSystemId`（詳細系は `StorageTier` と `DataType` を追加）。**S3 / アクセスポイントに関するメトリクスは 1 つも無い** |
| [Managing Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-manage.html) | アタッチメントのライフサイクル状態（AVAILABLE / CREATING / DELETING / UPDATING / MISCONFIGURED / FAILED）と管理操作のみ。**目次に監視やメトリクスの項目が無い**（Listing / Viewing details / Deleting / Configuring network access） |

**S3 側のメトリクス機構が適用できるかについての推論（推論であると明示する）**: Amazon S3 の
アクセスポイント向け CloudWatch リクエストメトリクスは、**バケット単位でのオプトイン**として
文書化されている。FSx for ONTAP のアクセスポイントの背後に S3 バケットは存在しないので [E-001]、
この機構がそのまま当てはまるとは考えにくい。**これは推論であり、AWS の言明ではない。**

**まとめると U3 の確度は 3 層になる**。design にはこの区別のまま書く。

1. **ドキュメントの状況（documented）**: FSx for ONTAP の CloudWatch ドキュメントは
   メトリクスの分類を列挙しており、そこにアクセスポイント次元は無い。S3 アクセスポイントの
   管理セクションにも監視のページが無い。
2. **実行した観測（verified）**: S3 AP アタッチメントが 22 件 `AVAILABLE` の環境で
   `list-metrics --namespace AWS/FSx` が返した 33 のメトリクス名に S3 系は 0。
   <!-- allow:naming: CloudWatch 名前空間の literal -->
   留保: `list-metrics` は直近に publish されたものしか返さない。
3. **推論（hypothesis）**: S3 のバケット単位オプトイン機構は FSx for ONTAP の AP には
   適用されないと考えられる。

**やっていないこと（正直に書く）**: **AWS サポートへの確認をしていない。機能改善要望も
出していない。** ドキュメントに無いことと、機能として存在しないことは別である。
S3 AP のリクエスト単位の可視性は、このリポジトリの主題（S3 AP 経由のデータ処理）にとって
中核的な観測項目なので、**「取れない」を設計の前提にする前にサポートに確認し、
無ければ機能改善要望として出すのが正しい順序**だった。タスクに追加した。
公開物には**ケース番号やベンダー内部 ID を書かない**（トピックとしてのみ言及する）。

### 10.3 訂正 3: F11（Amazon Managed Grafana の匿名アクセス）の出典の格下げ

公式ドキュメントで確認できたのはここまで。

- ワークスペース作成時の Authentication access は **IAM Identity Center / SAML / 両方**から
  選ぶ（[Create an Amazon Managed Grafana workspace](https://docs.aws.amazon.com/grafana/latest/userguide/AMG-create-workspace.html)）。
- **「Amazon Managed Grafana はワークスペース内の権限割り当てに IAM ユーザーとロールを
  使うことをサポートしない」**（[Use AWS IAM Identity Center with your workspace](https://docs.aws.amazon.com/grafana/latest/userguide/authentication-in-AMG-SSO.html)）。

**「匿名アクセスをサポートしない」という言い方の出典は community の回答（repost.aws）であって
公式の言明ではない。** 結論（Cognito のポータルに AMG を素直に埋め込めない）は変わらないが、
**根拠は「認証方式が IdC / SAML に限られる」までにする**。D3 の記述をこの強さに合わせた。

### 10.4 補強できたもの（弱かった根拠を一次情報に差し替え）

| 対象 | 差し替えた根拠 |
|---|---|
| **D6（`port_range` を使わない）** | Harvest **26.08** の [Prometheus Exporter](https://netapp.github.io/harvest/26.08/prometheus-exporter/) が `port_range` の欠点として、poller の順序に依存すること、順序を変えるとポートが変わること、**Prometheus は `instance` ラベルにポートを含むので別インスタンスとして扱われ「データを失ったように見える」**ことを明記している（issue #2782 を参照）。**つまり D6 は私の推測ではなくベンダーが文書化した既知の挙動。** なお同ドキュメントは `prom_port` と `port_range` の両方を推奨しており、D6 は**推奨の一方を意図的に採らない判断**である |
| **D33（AMP のラベル値からクラスターを導出）** | AMP に `GetLabels` があり、URI は `/workspaces/{workspaceId}/api/v1/label/{label-name}/values`、GET のみ（[GetLabels](https://docs.aws.amazon.com/prometheus/latest/userguide/AMP-APIReference-GetLabels.html)）。**設計が依拠する API は文書化されている** |
| **D18（エンドポイントは AZ ごとに課金）** | 「VPC エンドポイントが各アベイラビリティーゾーンでプロビジョニングされている時間ごとに課金される」（AWS PrivateLink の料金ページ）。インターフェイスエンドポイントは時間課金とデータ処理課金の両方（[Access an AWS service using an interface VPC endpoint](https://docs.aws.amazon.com/vpc/latest/privatelink/create-interface-endpoint.html)）。**§4 の「2 AZ で逆転する」は per-AZ 課金という文書化された性質に基づく** |
| **F4（Harvest に `remote_write` が無い）** | 26.08 の同ページが、エクスポータの役割を「Prometheus 行プロトコルへの整形」と「`/metrics` の web エンドポイント作成」と定義し、**「Prometheus が Harvest をポーリングする」**と明記。**当初 open として残していた「エクスポータは Prometheus と InfluxDB のみ」という列挙は、26.08 を読んで閉じた。答えは「列挙が古い」だった**: 26.08 は Prometheus / InfluxDB / **VictoriaMetrics** の 3 種を挙げ、VictoriaMetrics は `/api/v1/import/prometheus` へ**プッシュする**。つまり「Harvest はプル専用」は誤りで、正しくは**AMP が要求する `remote_write` を話すエクスポータが無い**。`remote_write` の 1 ホップが必要という結論は変わらない |

### 10.5 この再確認から学んだ、手順としての規律

- **選択的検索の `No matches` を「無い」の根拠にしない。** 短い語（`S3` のような 2 文字）は
  特にあてにならない。**クリティカルな不在を主張するなら全文を読む。**
- **検索結果のスニペットを出典にしない。** スニペットは文脈を落とす。§10.1 では、
  同じページに載っている反例（Harvest 用の作成例）を見落として、存在しない矛盾を作った。 <!-- allow:not-a-claim: 過去に自分が作った誤りの記述であって、ベンダーの機能不在の主張ではない -->
- **「ドキュメントに無い」と「機能として無い」を分ける。** 前者を後者として設計の前提に
  置くなら、**ベンダーへの確認と機能改善要望までを含めて初めて筋が通る。**
- **community の回答を公式の言明として引かない。** 結論が同じでも根拠の強さは違う。

---

## 未検証事項の一覧（実測していないもの）

U1〜U5 は 2026-09-05 に解消した（§9）。**解消したものを表から消さない**——「何を測って
いないか」と同じくらい「何をどう測ったか」が後から必要になる。

| # | 内容 | 状態 |
|---|---|---|
| U1 | Harvest が実際に出すアクティブシリーズ数 | **verified（§9）**。既定 11,617 シリーズ / 813 メトリクス名（ボリューム 35 本、ONTAP 9.18.1P3D1、Harvest 26.08.0-1）。D14 のオブジェクト名に訂正が必要と判明 |
| U2 | `fsxadmin-readonly` ユーザーを FSx for ONTAP で作れること（F8 の矛盾） | **verified（§9）**。実在し、作れ、書き込みは 403 で拒否される。F8 はドキュメント側の誤り。縮退は不要 |
| U3 | FSx for ONTAP S3 AP の CloudWatch メトリクスの有無（F14） | **verified に近い（§9 の下の注記）**。`AWS/FSx` の 33 メトリクス名に S3 / object / accesspoint / bucket 系は 1 つも無い。同アカウントに S3 AP アタッチメントが 22 件 AVAILABLE で存在する状態での観測 | <!-- allow:naming: CloudWatch 名前空間の literal -->
| U4 | Harvest の正式な公開レジストリと現行 digest（D8） | **verified（D8 の追記）**。`ghcr.io/netapp/harvest`、26.08.0-1、index digest `sha256:5e92452c…` |
| U5 | Interface VPC Endpoint の時間単価（D18） | **verified（D18 の追記）**。$0.014 / endpoint-h + $0.01 / GB。単一 AZ ではエンドポイントのほうが安く、判断は維持 |
| U6 | 1 Fargate タスクが扱えるクラスター数の上限（D5） | 未実測 |
| U10 | **S3 AP のリクエスト単位のメトリクスが AWS の機能として存在しないのか、ドキュメントに書かれていないだけなのか**（§10.2） | **2026-09-06 に起票済み、回答待ち [E-001]。** 「機能として無い」と分かれば機能改善要望として出す。公開物にはケース番号やベンダー内部 ID を書かず、トピックとしてのみ言及する |
| U11 | Harvest 26.08 のエクスポータの列挙（F4 の列挙部分。25.08 の記述に依拠していた） | **resolved（§10.4）**。26.08 のエクスポータは Prometheus / InfluxDB / VictoriaMetrics の 3 種で、VictoriaMetrics はプッシュ型。「2 種のみ」は 25.08 に依拠した古い記述だった。`remote_write` が無いという結論は変わらない |
| U7 | recharts のバンドル増分と 6〜8 枚での描画性能（D21） | ビルド後に計測 |
| U8 | Harvest が設定のホットリロードを持つか（F19。持つならフェーズ 2 のスーパーバイザが不要になる） | 公式ドキュメントを再確認し、無ければ実機で `harvest.yml` を書き換えて挙動を見る |
| U9 | AMP のラベル値取得（`/api/v1/label/<name>/values`）が課金上どれだけ安いか（D33 の代償の大きさ） | クエリサンプル数を実測 |
