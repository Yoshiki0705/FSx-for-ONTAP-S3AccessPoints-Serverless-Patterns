# AI 機能クイックスタート — ファイルポータル

🌐 **Language / 言語**: 日本語 | [English](../en/ai-features-quick-start.md)

Bedrock Q&A、Rekognition 画像解析、Athena SQL、ファイルアップロードを 15 分以内で体験するガイド。

---

## 前提条件

| 項目 | 確認・設定方法 |
|---|---|
| FSx for ONTAP S3 AP（または DemoMode 用 S3 バケット） | `aws fsx describe-s3-access-point-attachments --query '...Alias'` |
| Bedrock モデルアクセス | AWS Console → Bedrock → Model access → `amazon.nova-lite-v1:0` を有効化 |
| Glue Data Catalog（Athena 用） | 1 つ以上のデータベース + テーブルが登録済み |
| Athena 結果バケット | 任意の S3 バケット（S3 AP には Athena 結果を保存不可） |

---

## Step 1: ポータルをデプロイ

```bash
cd solutions/amplify-portal
npm install
cp amplify/portal-config.example.ts amplify/portal-config.ts
# portal-config.ts を編集: s3ApAlias に AP alias またはバケット名を設定
npx ampx sandbox --once
```

約 4 分でデプロイ完了:
```
✔ Deployment completed
AppSync API endpoint = https://xxx.appsync-api.ap-northeast-1.amazonaws.com/graphql
```

dev サーバー起動:
```bash
npm run dev
# http://localhost:5173 を開く
```

---

## Step 2: サインアップ＆ログイン

1. 「Create Account」タブでメール + パスワードを入力
2. 別のターミナルでユーザーを手動確認:
   ```bash
   USER_POOL_ID=$(python3 -c "import json; print(json.load(open('amplify_outputs.json'))['auth']['user_pool_id'])")
   aws cognito-idp admin-confirm-sign-up --user-pool-id "$USER_POOL_ID" --username "your@email.com" --region ap-northeast-1
   ```
3. ブラウザで Sign In → ログイン成功

---

## Step 3: ファイル閲覧（All Files）

![All Files — S3 AP ボリューム内容](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/main/solutions/amplify-portal/docs/screenshots/portal-main-view.png)

サイドバー「📂 All Files」で FSx for ONTAP のボリューム内容を表示。

- フォルダクリック → ナビゲーション
- 🖼️ クリック → 画像プレビュー（Presigned URL）
- 📄 クリック → ダウンロード（Presigned URL で新タブ）

---

## Step 4: ファイルに質問（Bedrock Q&A）

1. 「📂 All Files」でテキスト/CSV ファイルをクリック
2. 右パネルに「AI Assistant」が表示
3. 質問を入力（例: "このファイルに何件のレコードがある？"）
4. Enter → Bedrock がファイル内容を解析して回答

---

## Step 5: 画像解析（Rekognition）

1. 画像ファイル（.jpg, .png 等）があるフォルダに移動
2. 🖼️ アイコンクリック → プレビューポップオーバー表示
3. 「Detect Objects」ボタンクリック
4. ラベル + confidence がカラータグで表示

---

## Step 6: SQL クエリ（Athena）

1. サイドバー「📊 Analytics」をクリック
2. データベース名を入力（例: `fsxn_athena_verification`）
3. SQL を入力して「Run Query」
4. 結果がテーブルで表示

---

## Step 7: ファイルアップロード

1. サイドバー「📤 Upload」をクリック
2. ドラッグ＆ドロップ、またはファイル選択
3. PUT Presigned URL で FSx for ONTAP S3 AP に直接アップロード
4. アップロードしたファイルは NFS/SMB からも即座に参照可能

---

## クリーンアップ

```bash
cd solutions/amplify-portal
npx ampx sandbox delete --yes
```

---

## トラブルシューティング

| 問題 | 原因 | 解決策 |
|---|---|---|
| All Files が「Loading...」のまま | S3 AP alias 未設定 | `portal-config.ts` の `s3ApAlias` を設定 |
| Bedrock がエラー | モデル未有効化 | Bedrock コンソール → Model access → Nova Lite 有効化 |
| Athena "No output location" | 環境変数未設定 | `ATHENA_OUTPUT_LOCATION=s3://your-bucket/athena-results/` |
| 画像プレビューが表示されない | Presigned URL の問題 | Lambda ログを確認（SigV4 + リージョナルエンドポイント） |

---

## アーキテクチャ（AI 機能全体）

```
ブラウザ UI
  → AppSync GraphQL の mutation / query
    → Lambda（VPC 外、ARM64、Python 3.13）
      → S3 AP GetObject（ファイル本文の読み取り）
      → AWS の AI サービス（Bedrock / Rekognition / Textract / Comprehend）
    → 結果をブラウザへ返す
```

いずれの Lambda も次の条件で動きます。

- **VPC 不要**（Internet-origin の S3 AP と公開 AI エンドポイントを使うため）
- **ARM64**（Graviton2）でコスト効率を上げる
- **Python 3.13** と boto3（SigV4 + リージョナルエンドポイント）
- **IAM**: 関数ごとの最小権限（`s3:GetObject` と、その機能が使う AI アクションのみ）

---

## 関連ドキュメント

- [本番デプロイガイド](./amplify-hosting-production-guide.md)
- [Storage Browser デモ](./storage-browser-demo-guide.md)
- [S3 AP 互換性ノート](../s3ap-compatibility-notes.md)
