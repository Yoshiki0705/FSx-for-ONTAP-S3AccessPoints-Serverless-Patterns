# FC3: GenAI RAG Enterprise Files — デモガイド

## Executive Summary

エンタープライズファイルサーバー上のドキュメントに対して、ユーザーのアクセス権限を
尊重した AI 検索・回答生成を実演する。

**デモの核心メッセージ**: ファイルサーバーの権限体系を維持したまま、生成 AI による
ドキュメント検索・要約を実現する。

**想定時間**: 5〜7 分

---

## Target Audience

| 項目 | 詳細 |
|------|------|
| **役職** | IT 部門長 / 情報セキュリティ担当 / DX 推進担当 |
| **課題** | 社内ドキュメント検索の非効率性、権限管理との両立 |
| **期待する成果** | 権限を維持した AI 検索で業務効率化 |

---

## Demo Scenario

### ワークフロー全体像

```
1. インデックス構築（バックグラウンド）
   ファイルサーバー → S3 AP → チャンキング → エンベディング → ベクトル DB

2. ユーザークエリ（リアルタイム）
   ユーザー → API → 権限フィルタ → ベクトル検索 → Bedrock → 回答
```

### デモシナリオ: 権限による検索結果の違い

1. **管理者ユーザー**: 全ドキュメントが検索対象 → 包括的な回答
2. **一般ユーザー**: アクセス権のあるドキュメントのみ → 限定的な回答
3. **外部ユーザー**: 公開ドキュメントのみ → 最小限の回答

---

## Storyboard

### Section 1: Problem Statement（0:00–1:00）
- 社内ドキュメントが分散、検索が非効率
- AI 検索を導入したいが、権限管理が課題

### Section 2: Architecture Overview（1:00–2:00）
- FSx for ONTAP + S3 AP + OpenSearch + Bedrock の構成説明
- 権限フィルタリングの仕組み

### Section 3: Indexing Demo（2:00–3:30）
- Step Functions でインデックス構築を実行
- ACL メタデータの付与を確認

### Section 4: Query Demo — Admin（3:30–5:00）
- 管理者として質問 → 全ドキュメントから回答
- 検索結果のソースドキュメント表示

### Section 5: Query Demo — Limited User（5:00–7:00）
- 一般ユーザーとして同じ質問 → 限定的な回答
- 権限フィルタリングの効果を確認

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | インデックス構築オーケストレーション |
| Lambda (Chunking) | ドキュメント分割（512 トークン、128 オーバーラップ） |
| Lambda (Embedding) | Titan Text Embeddings V2 でベクトル化 |
| OpenSearch Serverless | k-NN ベクトル検索 + ACL メタデータフィルタ |
| API Gateway | クエリ API エンドポイント |
| Bedrock (Nova Pro) | 回答生成 |

---

## 出力サンプル

### クエリ: 「来期の予算計画について教えてください」

**管理者の回答**:
```json
{
  "answer": "来期の予算計画では、IT インフラ投資として...",
  "sources": [
    {"file": "budget/2026-Q3-plan.xlsx", "relevance": 0.92},
    {"file": "strategy/mid-term-plan.pdf", "relevance": 0.87}
  ],
  "acl_filter_applied": false
}
```

**一般ユーザーの回答**:
```json
{
  "answer": "公開されている情報によると、来期は...",
  "sources": [
    {"file": "public/company-newsletter-2026-05.pdf", "relevance": 0.71}
  ],
  "acl_filter_applied": true,
  "filtered_count": 3
}
```


## スクリーンショット

![Phase 13 — CloudFormation Stacks](../../docs/screenshots/masked/phase13-cloudformation-stacks.png)
![Phase 13 — Lambda Functions](../../docs/screenshots/masked/phase13-lambda-functions.png)
