# 他端末に渡すデモ環境

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/` 側が読み込み条件だけを持ち、該当する作業をしているときにこの内容へ誘導する。
> `.kiro/` は公開しないため、知識の本体は常にこちら側に置く。

対象は「自分以外の PC からポータルを開いてデモする」ための URL とアカウント。sandbox の
同居と後始末は [portal-sandbox-lifecycle](portal-sandbox-lifecycle.md)、CDK 側の制約は
[portal-cdk-quality-gates](portal-cdk-quality-gates.md) にある。

## 手順

```bash
# 1. バックエンド（未デプロイのときだけ）
cd solutions/amplify-portal && make sandbox

# 2. https の URL。AWS 内で完結する経路
make portal-hosting

# 3. アカウント。パスワードは実行時に一度だけ表示される
make portal-demo-user ARGS='--username demo@example.com \
  --groups storage-admin,internal --expected-sandbox demo'

# 4. 渡す前の確認
make portal-preflight
make portal-hosting-url
```

URL は `make portal-hosting-url` が返す `https://demo.<app-id>.amplifyapp.com`。この doc に
実 URL を書かないのは、公開リポジトリに載せると検索に載り、ポータルの前段が Cognito だけに
なるため。

## https が必須である理由

サインインは SRP 認証で `crypto.subtle` を、共有リンクのコピーで `navigator.clipboard` を
使い、どちらもブラウザが secure context に限定している。したがって

- `http://localhost:5173` — 例外扱いなので自分の端末では動く
- `http://192.168.x.x` — **動かない**。`npm run dev -- --host` で LAN に配る方法は選択肢に
  ならない
- `https://...` — 他端末から使えるのはこれだけ

## 2 つの経路と選び方

| 経路 | URL | 恒久性 | 使う場面 |
|---|---|---|---|
| Amplify Hosting | `https://demo.<app-id>.amplifyapp.com` | 固定 | **既定。** 他人に渡す |
| Cloudflare トンネル（`npm run phone`） | 実行ごとに変わる | 使い捨て | 自分の実機確認。渡さない |

Amplify Hosting を既定にするのは、URL が固定で、自分の PC を起動し続ける必要がなく、経路が
AWS 内で完結するため。トンネルは実行ごとに URL が変わり、ローカルの vite が生きている間だけ
有効なので、[portal-handover-guide](../../solutions/amplify-portal/docs/portal-handover-guide.md)
は「渡さない」と明記している。トンネルは AWS 側に何も作らずに実機を確認できる点だけが利点で、
その用途では今も有効。

`make portal-hosting` は zip アップロード方式で、git 接続を作らない。公開されるのは手元で
ビルドした成果物そのものになり、build minutes も消費しない。

## 公開バンドルの束縛先

`main.tsx` は `amplify_outputs.json` を静的に import するので、**User Pool と GraphQL
エンドポイントはバンドルにコンパイルされる**。つまり恒久 URL の恒久性は、背後の sandbox が
生きている限りのものである。sandbox を消して作り直すと、ページは開き、サインイン画面も出て、
**あらゆる資格情報が拒否される**。

このため `make portal-hosting` は app に束縛先をタグで記録する。

```bash
make portal-hosting-url    # built against sandbox 'demo', pool ap-northeast-1_...
```

タグの pool と現在の `amplify_outputs.json` の pool が食い違う場合、`portal-hosting-url` が
警告する。そのときの復旧は `make portal-hosting` の再実行（再ビルドして再公開）。

sandbox ごとに別の app を作る（app 名が `fsxn-portal-<sandbox>`）のは、2 つ目の sandbox から
publish したときに 1 つ目のバンドルを別プールを指すバンドルで上書きしないため。

## アカウントの権限

2 軸で、それぞれ別の場所で強制される（`amplify/portal-groups.ts`）。

| 軸 | 値 | 強制される場所 |
|---|---|---|
| role | `viewer` / `contributor` / `storage-admin` / `auditor` | AppSync の認可ルール |
| scope | `internal` / `external` | アクセスポイントとパス接頭辞 |

`enforceRoles` の既定は真なので、**グループを持たないユーザーはほぼ何もできない**。付与は
必須の手順であって移行時の作業ではない。

実測 2026-09-03、デプロイ済み API の introspection SDL から読んだ対応:

| エンドポイント | 要求するグループ |
|---|---|
| `adminQuery` / `adminMutation` / `arpMutation` / `protectionMutation` / `runAthenaQuery` | `storage-admin` |
| `fileMutation` / `folderMutation` | `contributor` または `storage-admin` |
| `queryAuditLog` | `auditor` または `storage-admin` |

したがって**全権限は `storage-admin` + `internal`**。`external` は role が `storage-admin`
でも閲覧範囲を絞り、AI エンドポイントを既定で拒否する。

グループは ID token に載るので、**付与後にサインアウトとサインインが必要**。これが
「付与したのに何も変わらない」の通常の原因。

### storage-admin で到達可能な不可逆操作

付与自体は `admin-remove-user-from-group` で戻せる。**戻せないのは、付与によって到達可能に
なる操作**。

| 操作 | 実装 | 戻せない理由 |
|---|---|---|
| SnapLock ボリューム作成（compliance / enterprise） | `resource-management/handler.py` | 型は作成時のみ。未期限の WORM ファイルがある間、ボリューム・SVM・**ファイルシステム**が削除不能 |
| Snapshot ロックの有効化 | 同上 | compliance ボリュームでは無効化不可 |
| Snapshot のロック / 保持期間の延長 | `snapshots/index.py`、`SnaplockManager.tsx` | 延長のみ。短縮・解除不可 |

**`acknowledgeIrreversible` は画面操作に対する防御ではない。** ハンドラはこのフィールドを
要求するが、フロントエンドがリテラルで送っている（`SnaplockManager.tsx`、
`VolumeManager.tsx`、`SnapshotAdminManager.tsx` など）。このゲートが止めるのはスクリプトや
エージェントからの呼び出しで、ボタンを押す人は素通りする。

デモで管理操作を見せる必要がないなら `contributor,internal` で払い出す。見せる必要があるなら
`storage-admin,internal` で払い出し、**終わったあとにグループを外す**。

```bash
aws cognito-idp admin-remove-user-from-group --user-pool-id <pool> \
  --username demo@example.com --group-name storage-admin
```

## 渡す前の確認

ページが開くことはサインインできる証拠ではない。出力ファイルが別 sandbox のプールを指して
いると、画面は正常に描画されてサインインだけが「ユーザー名またはパスワードが違います」で
失敗する。

```bash
make portal-preflight    # 出力が指すプールの実在と所有 sandbox、VPC 配線、DynamoDB route
```

`make portal-demo-user` に `--expected-sandbox` を渡すのも同じ理由で、プールが想定と違えば
アカウントを作る前に止まる。

最終的な確認は実際にサインインすること。2026-09-03 はホストした URL 上で
`demo@example.com` でサインインし、管理セクションが表示され、リソース管理から `adminQuery`
が実データ（ボリューム 10 本）を返すところまで確認した。変更系の操作は実行していない。

## 認可が効いていることの確認方法

`enforceRoles` の設定値ではなく、デプロイ済み API の directive を読む。

```bash
API=$(aws appsync list-graphql-apis --query "graphqlApis[?name=='amplifyData'].apiId" --output text)
aws appsync get-introspection-schema --api-id "$API" --format SDL /tmp/schema.sdl
grep -o 'cognito_groups : \[[^]]*\]' /tmp/schema.sdl | sort -u
```

**`cognito_groups :` のコロンの前に空白が入る。** `cognito_groups:` で grep すると 0 件に
なり、「認可が設定されていない」という逆の結論が出る。

AppSync の URL ホスト接頭辞と `apiId` は正当に異なるので、`amplify_outputs.json` の URL から
`apiId` を切り出すと `NotFoundException` になる。`list-graphql-apis` から引く。

## 後始末

```bash
make portal-hosting-url                                   # app id を確認
aws amplify delete-app --app-id <app-id>                  # ホスティングのみ削除
aws cognito-idp admin-delete-user --user-pool-id <pool> --username demo@example.com
```

ホスティングの削除は sandbox に影響しない（別スタック、VPC 資源を持たない）。逆に sandbox を
消すとホスティングは残るが誰もサインインできなくなる。

## 実測値

| 項目 | 値 | 測定日 |
|---|---|---|
| バンドルサイズ | 857 KiB | 2026-09-03 |
| `make portal-hosting`（ビルドから公開完了まで） | 2 分未満 | 2026-09-03 |
| build minutes 消費 | なし（zip アップロード方式） | 2026-09-03 |

## 罠

- **初回サインイン後にオンボーディングのオーバーレイがクリックを遮る。** 自動化で操作する
  場合は「次へ」を 3 回押して閉じる必要がある。手動のデモでは問題にならない。
- **アプリはハッシュルーティング**（`#files`、`#resources`）なので、サブルートの再読込は
  サーバに到達しない。Amplify 側の SPA rewrite は保険として入れてあるが、これがなくても
  現状の画面遷移は壊れない。
- **`oauth` 設定を持たない**（SRP のみ）ので、新しいオリジンを追加してもコールバック URL の
  登録は不要。ホスティングを足すために auth の設定を触る必要はない。
