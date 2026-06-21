# AWS Summit New York 2026 — 統合評価サマリ

- 評価日: 2026-06-18
- イベント: AWS Summit New York City 2026 (2026-06-17)
- 対象プロジェクト: FSx for ONTAP S3 Access Points Serverless Patterns

---

## 評価対象リリース

| リリース | 状態 | プロジェクトへの適合度 | 対応 |
|---------|------|-------------------|------|
| Bedrock Managed Knowledge Base | GA | ⚠️ 方針不一致 | 比較文書化のみ |
| AgentCore Web Search Tool | GA (us-east-1) | ✅ 高 | **実装完了** |
| AWS Context (Knowledge Graph) | Coming soon | ✅ 高（将来） | 調査文書化 |
| AWS Continuum (Security Agent) | Preview | ○ 中 | ウォッチ |
| AWS Transform – Continuous Modernization | Preview | ○ 中 | 既存調査に追記 |
| AWS DevOps Agent – Release Management | Preview | ○ 中 | ウォッチ |
| Glue Data Catalog Business Context | Preview | ✅ 高（短期） | AWS Context 調査内に記載 |
| S3 Annotations | GA | ✅ 高 | 別途調査進行中 |
| Bedrock AgentCore (Web Search, Memory, Gateway) | GA | ✅ 高 | Web Search 実装済み |

---

## 実施した対応

### 実装済み（コード変更）

| 成果物 | ファイル |
|--------|---------|
| 共通モジュール | `shared/web_search_client.py` |
| ユニットテスト (24件) | `shared/tests/test_web_search_client.py` |
| IAM Role CFn テンプレート | `shared/cfn/agentcore-gateway-role.yaml` |
| PoC スクリプト | `scripts/poc-web-search.py` |
| UC29 Query Lambda ハイブリッド化 | `solutions/genai/kb-selfservice-curation/functions/query/handler.py` |
| UC29 テンプレート パラメータ追加 | `solutions/genai/kb-selfservice-curation/template.yaml` |
| UC30 新アクション追加 | `solutions/genai/quick-agentic-workspace/functions/quick_action/handler.py` |
| UC30 テンプレート パラメータ追加 | `solutions/genai/quick-agentic-workspace/template.yaml` |

### 調査文書

| ドキュメント | ファイル |
|------------|---------|
| AgentCore Web Search 統合設計 | `docs/investigations/agentcore-web-search-fsxn-integration.md` |
| AWS Context × FSx ONTAP メタデータ Graph | `docs/investigations/aws-context-fsxn-metadata-graph.md` |
| Managed KB vs Custom KB + S3 Vectors ADR | `docs/investigations/managed-kb-vs-custom-kb-s3vectors.md` |
| Summit NY 2026 統合評価サマリ（本文書） | `docs/investigations/summit-ny-2026-integration-assessment.md` |

---

## 設計判断サマリ

### 採用

- **AgentCore Web Search Tool** → UC29/UC30 に opt-in 統合。`EnableWebSearch=true` で有効化。

### 不採用（理由明確化）

- **Bedrock Managed Knowledge Base** → S3 Vectors のコスト優位性 + Permission-Aware RAG の制御性を優先。

### 将来採用候補（追跡）

- **AWS Context** → GA 時に FSx ONTAP メタデータの Knowledge Graph 化を検討。
- **Glue Business Context & Semantic Search** → Preview 期間中に Glue Crawler + S3 AP の PoC を実施。
- **S3 Annotations** → FSx S3 AP 互換性検証の結果次第。

---

## 検証状況

| チェック | 結果 |
|---------|------|
| shared/web_search_client.py テスト | 24/24 PASS |
| UC29 既存テスト | 26/26 PASS |
| UC29 template cfn-lint | PASS |
| UC30 template cfn-lint | PASS |
| UC29 handler ruff | PASS |
| UC30 handler ruff | PASS |
| shared/cfn/agentcore-gateway-role.yaml cfn-lint | PASS |
| scripts/poc-web-search.py ruff | PASS |

---

## 次のアクション（優先順）

1. `scripts/poc-web-search.py setup` で us-east-1 に Gateway を作成し動作確認
2. S3 Annotations × FSx S3 AP 互換性検証を完了
3. Glue Crawler で S3 AP ファイル一覧のカタログ化 PoC
4. AWS Context Preview / GA のリリースノート監視
5. ap-northeast-1 への AgentCore Web Search 対応リージョン拡大を監視
