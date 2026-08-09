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
| AgentCore Gateway `create-gateway-target` で Lambda not found | Gateway と Lambda は**同一リージョン**に配置必須。クロスリージョン Lambda 呼び出しは不可 |
| Quick Desktop サインインで「account name is invalid」 | IAM ユーザー名 ≠ QuickSight ユーザー名。`aws quicksight list-users` で確認。Email ベースのサインインが最もシンプル |
| KNFSD cache hit speedup が見られない | NVMe なしインスタンス (`t3`, `m6i`) では L2 キャッシュ不可。`m6gd`/`im4gn`/`i3en` を使用 |
| KNFSD NFS mount: Connection refused | SG で TCP 2049 が未許可。KNFSD SG に NFS inbound rule を追加 |
| KNFSD 経由 write → S3 AP で見えない | NFS write は非同期。`sync` 後 2-3 秒待機してから S3 AP GetObject |
| KNFSD Terraform: InvalidAMIID | AMI ビルドリージョンとデプロイリージョンの不一致。`--region` を揃える |
