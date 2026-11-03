# 生成 AI / エッジキャッシュの罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/pitfalls-genai-edge.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

| Pitfall | Solution |
|---------|----------|
| Quick S3 Knowledge base not visible in ap-northeast-1 | S3 KB feature only available in us-east-1, us-west-2, ap-southeast-2, eu-west-1. Use Bedrock KB for Tokyo region, or cross-region Quick account |
| Bedrock `InvokeModel` with `inputText` → ValidationException | Nova/Claude models require Messages API. Use `bedrock.converse()` (not `invoke_model` with `inputText`). Add `bedrock:Converse` to IAM policy |
| AgentCore Gateway us-east-1 only assumption | **ap-northeast-1 で利用可能（検証済み 2026-07）**。Workshop が us-east-1 を使うのは簡便性のため。Gateway + Lambda + S3 AP を同一リージョンに配置すること |
| AgentCore Lambda event format: `event.toolName` で取得 | ❌ 正しくは `context.client_context.custom['bedrockAgentCoreToolName']`。event はフラットなパラメータ辞書。ツール名は `targetName___toolName` 形式 |
| AgentCore Gateway + Quick Desktop: Remote MCP 追加が永続化されない | **Import 方式**（JSON ファイルからの読み込み）を使う。Local/Remote 直接追加は Quick Desktop v0.1000.1495 で不安定 |
| Quick Web コンソール MCP コネクタ Step 2 エラー | Previous で Step 1 に戻ると OAuth フィールドがクリアされる。一度で全フィールド入力を完了すること。再現しない場合もある（間欠的） |
| AgentCore Gateway CUSTOM_JWT + Quick Desktop → 403 | NONE auth を PoC に使用。CUSTOM_JWT は認可ポリシー設定が必要（未解決、`docs/agentcore-mcp-remaining-issues.md` 参照） |
| AgentCore Gateway の `AuthorizerType` を更新すると "Authorizer type cannot be updated for an existing gateway"（2026-11-03、[E-017]） | 変更できない（更新はロールバックされる）。`NONE` から `AWS_IAM` へは新しい Gateway（スタック）を作る。`AWS_IAM` の呼び出しは SigV4 でサービス名 `bedrock-agentcore`、権限は `bedrock-agentcore:InvokeGateway`。署名なしは HTTP 401 |
| Gateway の Step Functions コネクタ: `DescribeExecution` に `output` が無い、FAILED の実行に `error` / `cause` が無い | `includedData: "ALL_DATA"` を渡す。省略と `METADATA_ONLY` では返らない（2026-11-03、SUCCEEDED と FAILED の両方で比較）。エージェントのシステムプロンプトに書く |
| Gateway の `GetExecutionHistory` で長い履歴を読めない | ツールの入力は `executionArn` だけで、`maxResults` と `nextToken` がない。71 イベントで約 93 KB（1 イベント約 1.3 KB）。結果の確認は `DescribeExecution` を使い、履歴は原因調査だけにする |
| Gateway 経由のツール入力の日本語が `??` になる（2026-11-03 に再観測） | エージェントに日本語を渡させない設計にする（許可リストの ASCII ID）。渡す必要があるなら `\uXXXX` に変換する |
| AgentCore Gateway `create-gateway-target` で Lambda not found | Gateway と Lambda は**同一リージョン**に配置必須。クロスリージョン Lambda 呼び出しは不可 |
| Quick Desktop サインインで「account name is invalid」 | IAM ユーザー名 ≠ QuickSight ユーザー名。`aws quicksight list-users` で確認。Email ベースのサインインが最もシンプル |
| KNFSD cache hit speedup が見られない | NVMe なしインスタンス (`t3`, `m6i`) では L2 キャッシュ不可。`m6gd`/`im4gn`/`i3en` を使用 |
| KNFSD NFS mount: Connection refused | SG で TCP 2049 が未許可。KNFSD SG に NFS inbound rule を追加 |
| KNFSD 経由 write → S3 AP で見えない | NFS write は非同期。`sync` 後 2-3 秒待機してから S3 AP GetObject |
| KNFSD Terraform: InvalidAMIID | AMI ビルドリージョンとデプロイリージョンの不一致。`--region` を揃える |
