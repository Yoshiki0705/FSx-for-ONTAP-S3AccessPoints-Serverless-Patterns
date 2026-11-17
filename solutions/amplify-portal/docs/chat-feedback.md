# AI チャットの回答の評価
🌐 **Language / 言語**: 日本語 | [English](chat-feedback.en.md)

AI チャットの回答ごとに、利用者が「良い回答」「良くない回答」を付け、コメントを添えられます。評価は DynamoDB に保存され、管理者と監査者が日ごとに見直せます。保存の形は、権限制御付き RAG の Web アプリ（[FSx-for-ONTAP-Agentic-Access-Aware-RAG](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG)）の評価と同じにしています。

## 保存する項目
評価は追記だけで、1 つの評価が 1 つの項目になります。直したり消したりする操作はありません。

| 項目 | 内容 |
|---|---|
| `feedbackId` | UUID |
| `timestamp` / `date` | UTC の ISO 形式 / `YYYY-MM-DD` |
| `userId` | AppSync のリゾルバーが渡す Cognito のユーザー名。ブラウザが送った値は使わない |
| `responseId` | 回答ごとの ID（`r-` と 32 桁の 16 進数）。形式 `[A-Za-z0-9_-]{1,64}` を確かめる |
| `rating` | `positive` か `negative` だけ |
| `comment` | 任意、1,000 文字まで |
| `modelId` | 回答したモデル。文字種と長さ（128 文字）を確かめる |
| `sourceDocIds` | 回答が根拠にしたファイルの不透明な ID（キーの SHA-256 の先頭 32 桁）、20 件まで |
| `ttlEpoch` | `timestamp` と保持日数（既定 365 日、`FEEDBACK_RETENTION_DAYS`） |

質問（`query`、500 文字まで）は、同じ `feedbackId` の別の項目（`kind` が `query`）に入れ、保持は既定 90 日（`FEEDBACK_QUERY_RETENTION_DAYS`）です。利用者が入力した文章なので、評価より短く持ちます。DynamoDB の TTL は項目ごとに効くので、項目を分けています。

`sourceDocIds` に入るのは、その利用者に返したファイルだけです。`kb_search` の結果（ツールの中で利用者のパスの範囲に絞ったもの）と、`read_file` が利用者のパスの範囲で読めたファイルのキーから作ります。読めなかったファイルの ID や名前は残しません。ID はチャットの応答で画面に渡り、評価と一緒に戻ってきます。評価を受けるときは形（16 進 32 桁、20 件まで）だけを確かめます。

## 使える人
- **評価する**: AI チャットを使える利用者。外部の利用者で AI の利用が許されていない人は評価できません
- **見直す**: `storage-admin` と `auditor` のロール。一覧に評価した人の利用者 ID は出ません
- **テーブルが無いとき**: Lambda に `FEEDBACK_TABLE` が無いと、画面に評価のボタンは出ません。`submitFeedback` も「保存した」とは返さず、`ratings are not enabled` を返します

## 見直しの手順
画面: AI チャットのヘッダーの評価のボタン（storage-admin と auditor にだけ出る）から、日付（UTC）ごとの評価を、時刻・評価・質問・コメント・モデル・根拠の件数の一覧で見られます。

週に 1 回、次の順で見ることを想定しています。

1. 前の週の各日の「良くない回答」を開き、質問とコメントを読む
2. 似た質問がまとまっているものを、原因で分ける（根拠のファイルが 0 件で答えた、根拠はあるが読み違えた、質問の範囲外、モデルの限界）
3. 原因ごとに直し方を決める（ナレッジベースへのファイルの追加、エージェントのプロンプトや使うツールの見直し、パスの範囲の見直し）
4. 次の週に、同じ種類の質問の評価が変わったかを見る

画面を使わずに見るときは、`ByDate` のインデックスを日付で引きます。

```bash
aws dynamodb query --table-name <ChatFeedbackTable の名前> --index-name ByDate \
  --key-condition-expression '#d = :d' --expression-attribute-names '{"#d":"date"}' \
  --expression-attribute-values '{":d":{"S":"2026-11-17"}}'
```

## 権限
AgentChat の Lambda のロールに足す権限は、`ChatFeedbackTable` への `dynamodb:PutItem` と `GetItem`、`ByDate` インデックスへの `dynamodb:Query` です。更新と削除の権限は付けません。
