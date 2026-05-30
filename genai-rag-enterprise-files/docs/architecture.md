# FC3: GenAI RAG Enterprise Files — アーキテクチャ

## 概要

FSx for ONTAP 上のエンタープライズファイルに対して、NTFS ACL ベースの
権限フィルタリングを適用した RAG（Retrieval-Augmented Generation）パイプライン。

## アーキテクチャ図

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Permission-Aware RAG                            │
│                                                                         │
│  ┌──────────────┐     ┌──────────────────────────────────────────────┐ │
│  │  EventBridge │     │         Step Functions (Indexing)             │ │
│  │  Scheduler   │────▶│                                              │ │
│  │              │     │  ┌──────────┐  ┌────────┐  ┌─────────────┐  │ │
│  │ rate(1 hour) │     │  │Discovery │─▶│Chunking│─▶│  Embedding  │  │ │
│  └──────────────┘     │  │ Lambda   │  │ Lambda │  │   Lambda    │  │ │
│                       │  └────┬─────┘  └────────┘  └──────┬──────┘  │ │
│                       └───────┼──────────────────────────────┼───────┘ │
│                               │                              │         │
│                               ▼                              ▼         │
│                       ┌──────────────┐              ┌──────────────┐   │
│                       │ FSx for ONTAP│              │  OpenSearch  │   │
│                       │ via S3 AP    │              │  Serverless  │   │
│                       │              │              │ (Vector DB)  │   │
│                       │ ListObjectsV2│              └──────────────┘   │
│                       │ GetObject    │                      ▲          │
│                       └──────────────┘                      │          │
│                               │                              │         │
│                               ▼                              │         │
│                       ┌──────────────┐              ┌──────────────┐   │
│                       │ ACL Extract  │              │  Query API   │   │
│                       │ Lambda       │              │ (API Gateway)│   │
│                       │ (ONTAP REST) │              │              │   │
│                       └──────────────┘              └──────────────┘   │
│                                                             │          │
│                                                             ▼          │
│                                                     ┌──────────────┐   │
│                                                     │   Bedrock    │   │
│                                                     │  (生成 AI)   │   │
│                                                     └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## コンポーネント

| コンポーネント | 役割 |
|--------------|------|
| Discovery Lambda | S3 AP 経由でファイル一覧取得 |
| ACL Extraction Lambda | ONTAP REST API で NTFS ACL 取得 |
| Chunking Lambda | ドキュメントをチャンク分割 |
| Embedding Lambda | Titan Embeddings でベクトル化 |
| OpenSearch Serverless | ベクトル DB（ACL メタデータ付き） |
| Query API (API Gateway) | ユーザークエリ受付 + 権限フィルタリング |
| Amazon Bedrock | 回答生成（Nova Pro / Claude） |

## 権限フィルタリングの仕組み

1. インデックス時: 各チャンクに ACL メタデータ（SID リスト）を付与
2. クエリ時: ユーザーの SID をもとに OpenSearch フィルタクエリを構築
3. 結果: ユーザーがアクセス権を持つドキュメントのみが検索対象

## データフロー

```
[ファイル] → S3 AP → Discovery → Chunking → Embedding → OpenSearch
                                                              ↓
[ユーザー] → API GW → Query Lambda → OpenSearch (ACL filter) → Bedrock → 回答
```

## セキュリティ考慮事項

- データは FSx ONTAP 上に留まる（S3 バケットへのコピーなし）
- ベクトル DB にはチャンクテキスト + ACL メタデータのみ格納
- クエリ時に必ず ACL フィルタリングを適用
- Bedrock への入力はフィルタ済みチャンクのみ
