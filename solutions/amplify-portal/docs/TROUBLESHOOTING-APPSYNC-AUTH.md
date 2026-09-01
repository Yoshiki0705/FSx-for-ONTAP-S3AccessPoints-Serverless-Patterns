# AppSync 認可のトラブルシューティング（Amplify Gen2）

🌐 **Language / 言語**: 日本語 | [English](TROUBLESHOOTING-APPSYNC-AUTH.en.md)

## 事象: カスタム Query / Mutation で "User is not authorized"

### 症状

- カスタム `adminQuery`（一覧系の操作）は正常に動作する
- カスタム `adminMutation`（作成・削除系の操作）が `"User is not authorized."` を返す
- ユーザーはサインイン済みであることを確認（Cognito User Pools）
- `data/resource.ts` には `.authorization((allow) => [allow.authenticated()])` がある
- サンドボックスのデプロイは成功している

### 根本原因

Amplify Gen2 で複数の認証プロバイダを設定している場合（Cognito User Pools + IAM）、`authMode` を明示せずに `generateClient<Schema>()` を呼ぶと、**Cognito ID トークンが AppSync に送られないことがあります**。代わりに IAM など別の既定モードが使われ、AppSync がリクエストを拒否します。

これは公開情報として記載のある挙動です。

- [Amplify Docs: AI Generation の例](https://docs.amplify.aws/react/ai/generation/) では `generateClient<Schema>({ authMode: "userPool" })` と書かれています
- [openillumi.com: How to Fix AWS Amplify GraphQL Unauthorized Errors](https://openillumi.com/en/en-amplify-graphql-unauthorized-fix-authmode/) — `authMode` の明示が決定的な対処であると述べられています

Content was rephrased for compliance with licensing restrictions.

### 対処

Amplify データクライアントを作るときは常に `authMode: "userPool"` を指定します。

```typescript
// BEFORE (broken): authMode not specified
const client = generateClient<Schema>();

// AFTER (fixed): explicit authMode
const client = generateClient<Schema>({ authMode: "userPool" });
```

### 一覧が通り作成が失敗した理由

一覧の操作（`action: "listFlexCaches"` を伴う `adminQuery`）は GraphQL の **Query** 型です。AppSync は手元の資格情報のまま Query 型を通す既定・キャッシュ挙動を取ることがあります。一方 **Mutation** 型（`action: "createFlexCache"` を伴う `adminMutation`）はより厳しい認可チェックを受け、Cognito トークンの明示が必要になります。

### 併発する事象: CloudFormation の "Group Already Exists"

`amplify/auth/resource.ts` に `groups: ["storage-admin"]` を追加したとき、そのグループを事前に Cognito User Pool のコンソールで手動作成していると、CloudFormation が次のエラーで失敗します。

```
Group storage-admin already exists in UserPool ap-northeast-1_XXXXX
```

**対処**: グループが既に存在する場合は `defineAuth` に `groups` を宣言しないでください。グループ所属は CLI またはコンソールで管理します。

```bash
aws cognito-idp admin-add-user-to-group \
  --user-pool-id <pool-id> \
  --username <user-id> \
  --group-name storage-admin
```

### 影響を受けたコンポーネント

| コンポーネント | ファイル | 適用した修正 |
|-----------|------|-------------|
| FlexCacheManager | `src/components/admin/FlexCacheManager.tsx` | `authMode: "userPool"` |
| SnapMirrorStatus | `src/components/admin/SnapMirrorStatus.tsx` | `authMode: "userPool"` |
| VolumeManager | `src/components/admin/VolumeManager.tsx` | `authMode: "userPool"` を追加すべき |

### 確認手順

1. サンドボックスがデプロイ済みであることを確認（`amplify_outputs.json` が更新されている）
2. サインアウトして再サインイン（Cognito トークンを更新）
3. Resource Management > FlexCache へ移動
4. 「+ FlexCache Create」をクリック → フォーム入力 → Submit
5. 成功メッセージが出ること（ONTAP のエラーは可。認可エラーでないこと）

### 参考

- [Amplify Gen2 Docs: Customize Authorization](https://docs.amplify.aws/react/build-a-backend/data/customize-authz/)
- [AWS re:Post: Schema difference between Mutation and Query](https://repost.aws/questions/QUBa3YlvqRQsuex_K4YVS9RA)
- [openillumi.com: Fix unauthorized errors using authMode](https://openillumi.com/en/en-amplify-graphql-unauthorized-fix-authmode/)

---

## 事象: ONTAP REST API 側の "User is not authorized"（Lambda レベル）

> **一次情報**: 詳細な接続アーキテクチャ、パスワード管理、ロックアウト復旧手順は [ONTAP-CONNECTION-GUIDE.md](./ONTAP-CONNECTION-GUIDE.md) を参照してください。

### 要約

- ONTAP REST API が 401 を返す主要原因: **パスワード不一致** または **アカウントロックアウト**
- 復旧: `aws fsx update-file-system` でパスワードリセット → Secrets Manager 同期
- 詳細な手順とアーキテクチャ図: [ONTAP-CONNECTION-GUIDE.md](./ONTAP-CONNECTION-GUIDE.md)

---

## 事象: FlexCache の POST で Lambda がタイムアウトする（原因判明）

### 症状

- `listFlexCaches`（GET）は 4-5 秒で完了 ✅
- `createFlexCache`（POST）で Lambda が 60 秒でタイムアウト ❌
- CloudWatch ログに `Duration: 60000.00 ms  Status: timeout`
- 画面表示は "User is not authorized"（誤解を招く。実際の原因はタイムアウト）

### 根本原因

ONTAP REST API の `POST /storage/flexcache/flexcaches` は、既定で**同期的な長時間処理**です。`return_timeout=0` を付けないと、ONTAP は FlexCache の作成が完全に終わるまで HTTP 接続を保持します（ボリュームサイズにより 30-120 秒以上）。これが Lambda のタイムアウトを超えます。

GET のエンドポイント（`/storage/flexcache/flexcaches`）は既存のキャッシュのメタデータを即座に返すため、長時間処理は発生しません。

### 適用した修正

1. **POST の URL に `return_timeout=0` を追加**: `/storage/flexcache/flexcaches?return_timeout=0`
   - ONTAP が `202 Accepted` + ジョブ UUID を即座に返すようになります
   - FlexCache の作成自体は非同期で進みます

2. **Lambda のタイムアウトを 60 秒から 120 秒へ引き上げ**（`amplify/backend.ts`）
   - 他の操作が長引く場合の安全余裕

3. **`_create_flexcache` と `_ontap_request` に詳細ログを追加**
   - HTTP ステータスコードとエラーメッセージが CloudWatch に記録されます

### ONTAP REST API: 同期と非同期

| パラメータ | 挙動 |
|-----------|------|
| （既定） | 処理完了まで ONTAP が接続を保持する（Lambda のタイムアウトを超えうる） |
| `return_timeout=0` | ONTAP が 202 + ジョブ UUID を即座に返す |
| `return_timeout=N` | ONTAP が最大 N 秒待ち、未完了ならジョブ UUID を返す |

### タイムアウトが "User is not authorized" に見える理由

Lambda がタイムアウトすると（60 秒）、AppSync は応答を受け取れず、汎用のエラーを合成することがあります。Amplify クライアントは特定の AppSync エラーパターンを "User is not authorized." と解釈します。これはタイムアウトに起因する誤ったエラーメッセージで、実際の認可失敗ではありません。

---

## 撤回: `/storage/flexcache/flexcaches` が `fsxadmin` を 401 で拒否する、と考えていた

**この結論は誤りでした。** 推論の過程が参考になるため記録として残しています。401 の原因は `fsxadmin` のパスワード不一致とロックアウトであり、API 側の制限ではありませんでした。訂正後の分析を以下に記します。

### 訂正後の根本原因: パスワード不一致 / アカウントロックアウト

`fsxadmin` ユーザーは、以下を含む ONTAP REST API の全エンドポイントにフルアクセスを持ちます。

- `/storage/flexcache/flexcaches`（GET、POST、DELETE）
- `/snapmirror/relationships`（GET、POST、PATCH、DELETE）
- その他すべてのクラスタースコープ API

401 の原因は次の 2 点でした。

1. **パスワード不一致**: Secrets Manager 上のパスワードが、Amazon FSx for NetApp ONTAP ファイルシステム上の実際の `fsxadmin` パスワードと一致していなかった
2. **アカウントロックアウト**: 認証失敗の繰り返し（先のタイムアウト調査によるもの）が ONTAP のアカウントロックアウト機構を発動させた

### 解決手順

```bash
# 1. Reset fsxadmin password via AWS FSx API
aws fsx update-file-system \
  --file-system-id fs-XXXXX \
  --ontap-configuration '{"FsxAdminPassword":"NewSecurePassword"}' \
  --region ap-northeast-1

# 2. Update Secrets Manager to match
aws secretsmanager put-secret-value \
  --secret-id fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"NewSecurePassword"}' \
  --region ap-northeast-1
```

### 証跡: パスワードリセット後は正常動作
- FlexCache 一覧: ✅ `1 FlexCache volumes`（cachevol01 が表示）
- FlexCache 作成: ✅ `fc_e2e_test` が受理（202 + ジョブ UUID）
- SnapMirror 一覧: ✅ `1 レプリケーション関係`（svm_shift:ds_migtoaws → fsxsvm01:ds_migtoaws_bk）

### 学び

401 が出たときに、そのエンドポイントが「制限されている」と決めつけないこと。常に次を確認します。

1. パスワードは正しいか？（Secrets Manager と実際の値を照合）
2. アカウントはロックされていないか？（ONTAP は N 回の失敗でロックする）
3. 接続先のエンドポイントは正しいか？（ファイルシステム管理 IP と SVM 管理 LIF）

---

## 調査中に見つかった UI の改善点

### 1. エラーメッセージの明確化
**問題**: ONTAP の 401 が汎用の "User is not authorized" として表示され、AppSync の認可失敗と同じ文言になるため混乱を招く。
**改善**: ONTAP のエラーには HTTP ステータスとエンドポイントを前置する: `"ONTAP 401: /storage/flexcache/... — check fsxadmin credentials"`

### 2. FlexCache のジョブ状態の追跡
**問題**: 作成成功（202 Accepted）後、UI は「バックグラウンドで構築中」と表示するが、進捗を確認する手段がない。
**改善**: ジョブ UUID を保持し、`/cluster/jobs/{uuid}` をポーリングする「状態を確認」ボタンを追加する

### 3. Mutation 後の自動リフレッシュ
**問題**: 作成・削除の後、一覧を更新するには画面を離れて戻る必要がある。
**改善**: 作成成功の 5-10 秒後に一覧を自動更新する

### 4. 接続状態のインジケーター
**問題**: ONTAP の資格情報が誤っていると、すべての操作が無言で失敗するか、分かりにくいエラーになる。
**改善**: パネル読み込み時に接続チェックを行う（`/api/cluster` エンドポイントを叩き、緑・赤で表示）

### 5. 破壊的操作の保護
**問題**: 削除ボタンが `window.confirm()` を使っており、他の操作と見分けがつかない。
**改善**: 赤系のスタイルを当てたインラインの確認 UI にし、削除にはボリューム名の入力を要求する

### 6. SnapMirror の状態表示
**問題**: 状態 `broken_off` が生の文字列で表示され、意味が分からない。
**改善**: 状態を人が読める表示に対応づけ、色を添える（緑=snapmirrored、黄=transferring、赤=broken_off）
