# 利用者への引き渡しと問い合わせ対応 — ファイルポータル

🌐 **Language / 言語**: 日本語 | [English](portal-handover-guide.en.md)

> ポータルのインフラを用意した人が、**利用者に渡すもの**と**利用者の質問に答えるもの**をまとめた文書です。
> 「何をどこから取って、どこで管理し、どう渡すか」を項目ごとに書いています。

---

## 3 つの文書の関係

ポータルには読者の違う文書が 3 種類あります。**どれを誰に渡すかを間違えると、
デプロイ手順書をスマホ利用者に読ませることになります。**

| 文書 | 読者 | 内容 | 渡す相手 |
|------|------|------|---------|
| [Getting Started](GETTING-STARTED.md) | インフラ担当 | VPC Endpoint、Secrets Manager、`portal-config.ts`、デプロイ | **渡さない**（自分用） |
| **この文書** | インフラ担当 | 渡すもの、管理場所、問い合わせ対応 | **渡さない**（自分用） |
| [スマートフォン操作ガイド](../../../docs/ja/portal-mobile-guide.md) | 利用者（スマホ） | サインインから各操作まで、画面つき | **渡す** |
| [ユーザーガイド](../../../docs/ja/portal-user-guide.md) | 利用者（PC） | 全機能の説明 | **渡す** |

デプロイが終わったら、この文書の[引き渡しチェックリスト](#引き渡しチェックリスト)に進みます。

---

## 利用者に渡す 3 点

これだけで利用者は使い始められます。**これ以上渡すと、インフラの事情を利用者に持ち込むことになります。**

| 渡すもの | どこから取るか | 共有方法 |
|---------|--------------|---------|
| **ポータルの URL** | 下記「URL の実体」 | 社内 wiki / チャットのピン留め。恒久的な場所に置く |
| **アカウント**（メールアドレス + 初回パスワード） | 下記「アカウントの作り方」 | **パスワードはチャットに貼らない。** 資格情報管理ツール、または初回サインイン時変更を前提とした個別連絡 |
| **操作ガイドの URL** | [スマートフォン操作ガイド](../../../docs/ja/portal-mobile-guide.md) / [ユーザーガイド](../../../docs/ja/portal-user-guide.md) | URL の隣に併記する。**URL だけ渡すと必ず操作の質問が来ます** |

> **渡さないもの**: `fsxadmin` のパスワード、ファイルシステム ID、管理 LIF の IP、
> Secrets Manager のシークレット名、VPC やサブネットの ID。いずれも利用者の操作には不要で、
> 問い合わせの回答にも出す必要がありません。

---

## 「必要なもの」の裏側

利用者向けガイドの[「準備するもの」](../../../docs/ja/portal-mobile-guide.md#準備するもの)にある 3 項目について、
**実体・管理場所・取得方法・変えたときの影響**をまとめます。利用者から「これは何ですか」と聞かれたときの答えです。

### URL の実体

| 配信方法 | URL の形 | 取得方法 | 恒久性 |
|---------|---------|---------|-------|
| Amplify Hosting | `https://<branch>.<app-id>.amplifyapp.com`（またはカスタムドメイン） | `aws amplify list-apps` → `aws amplify list-branches --app-id <app-id>` | **恒久。利用者に渡すのはこれ** |
| ローカル + トンネル | `https://<ランダム>.trycloudflare.com` 等 | `npm run phone` の出力（[手順](GETTING-STARTED.md)） | **実行ごとに変わる。渡さない**（自分の実機確認用） |
| ローカル | `http://localhost:5173` | `npm start` の出力 | 自分の端末のみ。**他人の端末からは開けない** |

**`https://` である必要があります。** ポータルはサインイン（SRP 認証）で `crypto.subtle`、
共有リンクのコピーで `navigator.clipboard` を使い、どちらもブラウザが secure context に
限定している API です。`http://localhost` は例外扱いですが、`http://192.168.x.x` のような
LAN アドレスは該当しません。**`npm run dev -- --host` で LAN の IP を配る方法ではサインインできません。**
詳細は [Getting Started の「スマートフォン実機で確認する」](GETTING-STARTED.md#スマートフォン実機で確認する)。

### アカウントの作り方

管理場所は **Cognito ユーザープール**です。プール ID は `amplify_outputs.json` にあります。

```bash
cd solutions/amplify-portal
POOL=$(python3 -c "import json;print(json.load(open('amplify_outputs.json'))['auth']['user_pool_id'])")

# 1. 作成（招待メールを送らない場合は --message-action SUPPRESS）
aws cognito-idp admin-create-user --user-pool-id "$POOL" \
  --username <user@example.com> --message-action SUPPRESS \
  --user-attributes Name=email,Value=<user@example.com> Name=email_verified,Value=true

# 2. 初回パスワードを設定（--permanent を付けないと初回サインインで変更を求められる）
aws cognito-idp admin-set-user-password --user-pool-id "$POOL" \
  --username <user@example.com> --password '<initial-password>' --permanent
```

**管理系セクション（リソース管理・分析）を使わせる場合のみ**、グループに入れます。

```bash
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL" \
  --username <user@example.com> --group-name storage-admin
```

> **付与後はサインアウトして再サインインが必要です。** グループは ID トークンに入るため、
> 既存のトークンには反映されません。「権限をもらったのにメニューが出ない」の答えはこれです。
>
> グループ自体は `amplify/auth/resource.ts` が作成するので手作業は不要です。所属の付与だけが手作業です。

### ブラウザ

iOS Safari / Android Chrome の最新版。特別な設定は要りません。
**プライベートブラウズでも動作しますが、言語とテーマの設定は保持されません**（`localStorage` を使うため）。

---

## 利用者の言葉 → 確認するもの

利用者向けガイドの[「困ったとき」](../../../docs/ja/portal-mobile-guide.md#困ったとき)と 1 対 1 で対応します。

**まず「調べる必要があるか」を判定します。** 半分は仕様の説明で終わります。

### 調べる必要がないもの（答えるだけ）

| 利用者が言うこと | 実際に起きていること | 返す答え |
|----------------|------------------|---------|
| メニューが出てこない | スマホではドロワーが既定で閉じている | 画面左上の **☰** をタップ |
| 一覧が空に見える | 上部の操作ボタンが縦に並び、一覧はその下 | 下にスクロール |
| プレビューが出ずダウンロードされた | その形式にプレビューがない | 画像・PDF・テキストは画面内、それ以外はダウンロード |
| 共有・改名・削除が見つからない | 行の操作は **⋮** の中 | 行の **⋮** をタップ（画面下にシートが出る） |
| 文字が小さい | 仕様 | ピンチで拡大可。入力欄は 16px 以上なのでタップでは拡大しない |
| 「PHI — AI ブロック」と出る | 保護対象フォルダでの AI 実行を意図的に止めている | 保護対象外のフォルダで実行 |
| 権限をもらったのに管理メニューが出ない | ID トークンが古い | **サインアウトして再サインイン** |

### 調べる必要があるもの

| 利用者が言うこと | 最初に確認すること | よくある原因 |
|----------------|-----------------|------------|
| サインインできない（押しても進まない） | URL が `https://` か | `http://` の LAN アドレスを配っている → [URL の実体](#url-の実体) |
| サインインできない（パスワードが違うと出る） | `aws cognito-idp admin-get-user --user-pool-id "$POOL" --username <user>` の `UserStatus` | `FORCE_CHANGE_PASSWORD` のまま → `--permanent` 付きで再設定 |
| 「ONTAP 接続が必要」「ONTAP が認証情報を拒否しました」等 | `make ontap-preflight FS_ID=<fs-id> LAMBDA=<関数名>` | 6 段のどれか。→ [ONTAP 接続ガイド](ONTAP-CONNECTION-GUIDE.md#まず-make-ontap-preflight-を実行する) |
| 画面が横に切れてボタンに届かない | 画面名とボタン名を聞く | **不具合。** スマホ幅で横スクロールは起きない設計 → [検証手順](../../../docs/ja/portal-mobile-guide.md#このガイドの検証状況) |
| ファイルが見えない / 一部しか見えない | 権限か、S3 Access Point の対象範囲 | [認可モデル](../../../docs/ja/portal-authorization-model.md) |

> **ONTAP 系のメッセージは、利用者に「見出しとエラー詳細をそのまま送ってください」と頼むのが最短です。**
> ポータルは原因を 5 クラスに分類して表示し、エラー詳細に ONTAP 自身のメッセージ・HTTP ステータス・
> エラーコードをそのまま出します。この文言があれば、どの層を調べるかが決まります。
> ネットワークを疑う必要があるのは `UNREACHABLE` のときだけです。

---

## 定型返信

そのままコピーして使えます。

**URL とアカウントを渡すとき**

```
ファイルポータルを使えるようにしました。

URL: https://<portal-url>
アカウント: <user@example.com>
パスワード: 別途お送りします

操作方法（スマートフォン）: <mobile-guide-url>
操作方法（PC）: <user-guide-url>

専用アプリは不要で、ブラウザで URL を開くだけです。
うまくいかないときは、画面に出ている文言をそのまま送ってください。
```

**ONTAP 系のメッセージを報告されたとき**

```
ご報告ありがとうございます。ストレージ側の問題で、操作方法の誤りではありません。
確認のため、画面の見出しと「エラー詳細」を開いた中身をそのまま送っていただけますか。
（ファイル閲覧・アップロード・AI 処理は影響を受けずに使えます）
```

**仕様の質問に答えるとき（例: メニューが出ない）**

```
スマートフォンでは、画面が狭いためメニューが既定で隠れています。
画面左上の ☰ をタップすると開きます。項目を選ぶと自動で閉じます。

画面つきの手順はこちらにあります: <mobile-guide-url>
```

---

## 管理場所の一覧

**「あの値はどこにある？」を毎回探さないための表です。**

| 項目 | 管理場所 | 確認コマンド |
|------|---------|------------|
| ポータルの URL | Amplify Hosting（アプリ / ブランチ） | `aws amplify list-apps` |
| 利用者アカウント | Cognito ユーザープール | `aws cognito-idp list-users --user-pool-id "$POOL"` |
| 管理権限の所属 | Cognito グループ `storage-admin` | `aws cognito-idp list-users-in-group --user-pool-id "$POOL" --group-name storage-admin` |
| プール ID / API エンドポイント | `amplify_outputs.json`（デプロイで生成、**手で編集しない**） | `cat amplify_outputs.json` |
| ONTAP 接続先（管理 IP / SVM / ボリューム） | `amplify/portal-config.ts` | `grep ontap amplify/portal-config.ts` |
| `fsxadmin` の資格情報 | Secrets Manager | `aws secretsmanager get-secret-value --secret-id <secret-name>` |
| ファイルシステム / SVM / ボリュームの実体 | FSx for ONTAP | `make ontap-preflight FS_ID=<fs-id>` |
| 監査ログ（誰が何をしたか） | ポータルの「監査証跡」タブ | ポータル UI |

> **`amplify_outputs.json` はデプロイ成果物です。** 手で書き換えても次のデプロイで戻ります。
> 値を変えたいときは `amplify/` 側を直します。

---

## 引き渡しチェックリスト

デプロイ完了後、利用者に渡す前に:

- [ ] `make ontap-preflight FS_ID=<fs-id> LAMBDA=<関数名>` が**全 6 段 PASS**（`LAMBDA=` 省略時の SKIP は PASS ではない）
- [ ] `https://` の恒久的な URL がある（トンネルの URL を配ろうとしていない）
- [ ] 利用者アカウントを作成し、`UserStatus` が `CONFIRMED`
- [ ] 管理権限が必要な人だけ `storage-admin` に入れた
- [ ] 自分の端末のブラウザで、その URL からサインインできた
- [ ] スマホ幅（またはスマホ実機）でファイル一覧が開けた
- [ ] 利用者に **URL + アカウント + 操作ガイドの URL** の 3 点を渡した
- [ ] パスワードをチャットに貼っていない
- [ ] 問い合わせ窓口（自分の連絡先）を伝えた

---

## 関連ドキュメント

| ドキュメント | 使う場面 |
|-------------|---------|
| [Getting Started](GETTING-STARTED.md) | 作るとき |
| [ONTAP 接続ガイド](ONTAP-CONNECTION-GUIDE.md) | ONTAP 系のメッセージを調べるとき |
| [スマートフォン操作ガイド](../../../docs/ja/portal-mobile-guide.md) | 利用者に渡すとき / 仕様を確認するとき |
| [ユーザーガイド](../../../docs/ja/portal-user-guide.md) | PC 利用者に渡すとき |
| [認可モデル](../../../docs/ja/portal-authorization-model.md) | 「見えない」の原因を切り分けるとき |
| [Amplify Hosting 本番ガイド](../../../docs/ja/amplify-hosting-production-guide.md) | 恒久的な URL を用意するとき |
| [クリーンアップガイド](cleanup-guide.md) | 環境を畳むとき |
