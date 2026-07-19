# ファイルポータル UI の選択肢 — Amplify Gen2 / Nextcloud / カスタムビルド

## エグゼクティブサマリ

FSx for ONTAP ボリューム上のファイルを **Web ブラウザから閲覧・処理指示・結果確認**するためのフロントエンドには、複数のアーキテクチャ選択肢があります。

Box や Google Drive のようなファイル管理体験（フォルダナビゲーション、プレビュー、共有リンク、同期）を NAS データに対して提供する AWS マネージドサービスは、執筆時点では存在しません。S3 Console でオブジェクト一覧は確認できますが、エンドユーザー向けのファイルポータルとしては不十分です。このため、自分で組み上げるか OSS を活用する必要があります。

本ドキュメントでは、AWS Amplify Gen2、Nextcloud、カスタムビルド（CDK + フレームワーク）の3つを比較し、チームの状況に応じた選び方を示します。

**要点**: 3つすべてが妥当な選択肢です。チームの既存スキル、運用方針、コンプライアンス要件に応じて選択してください。本リポジトリのコア S3 AP サーバーレスパターンは、フロントエンドの選択に依存せず独立して動作します。

---

## 目次

1. [アーキテクチャ概要](#アーキテクチャ概要)
2. [比較マトリクス](#比較マトリクス)
3. [選び方ガイド](#選び方ガイド)
4. [Amplify Gen2 統合パターン](#amplify-gen2-統合パターン)
5. [Nextcloud 統合パターン](#nextcloud-統合パターン)
6. [カスタムビルドパターン](#カスタムビルドパターン)
7. [スループットと容量計画](#スループットと容量計画)
8. [認証とコンプライアンス連鎖](#認証とコンプライアンス連鎖)
9. [導入ロードマップ](#導入ロードマップ)
10. [コスト概算（増分）](#コスト概算増分)
11. [トレードオフまとめ](#トレードオフまとめ)
12. [FAQ](#faq)
13. [関連ドキュメント](#関連ドキュメント)

---

## アーキテクチャ概要

3つのアプローチすべてが、同じバックエンド統合ポイント（FSx for ONTAP S3 Access Points にアクセスする Lambda を Step Functions でオーケストレーション）を共有します。

```
┌─────────────────────────────────────────────────────────────┐
│           フロントエンド層（いずれかを選択）                     │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Amplify Gen2│  │  Nextcloud  │  │ カスタム             │ │
│  │ React +     │  │  (EC2/ECS)  │  │ (Vite/Next.js)      │ │
│  │ AppSync     │  │  + External │  │ + CDK               │ │
│  │             │  │    Storage  │  │ + API Gateway        │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
└─────────┼────────────────┼─────────────────────┼────────────┘
          │                │                     │
          ▼                ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│  統合レイヤー                                                 │
│  - AppSync HTTP Resolver → Step Functions                    │
│  - API Gateway REST → Step Functions                         │
│  - Nextcloud External Storage → S3 AP（直接）                 │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│  バックエンド（既存 — 変更不要）                                │
│  ┌──────────────┐     ┌─────────────────────┐              │
│  │Step Functions │     │ Lambda Functions     │              │
│  │(ASL workflow) │────▶│ Discovery (VPC内)    │              │
│  │              │     │ Processing (VPC外)   │              │
│  └──────────────┘     └──────────┬──────────┘              │
└──────────────────────────────────┼──────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────┐
│  FSx for ONTAP S3 Access Point                              │
│  (NFS / SMB / S3 — マルチプロトコル共有ネームスペース)           │
└─────────────────────────────────────────────────────────────┘
```

---

## 比較マトリクス

| 観点 | Amplify Gen2 | Nextcloud | カスタムビルド (CDK) |
|------|:---:|:---:|:---:|
| **セットアップ時間 (PoC)** | 2-3日 | 1-2日（経験者） | 1-2週間 |
| **ファイル閲覧 (組み込み)** | カスタム UI 必要 | 組み込みファイルマネージャ | カスタム UI 必要 |
| **処理ジョブ起動** | AppSync Mutation → SFn | Workflow App or webhook | API Gateway → SFn |
| **認証** | Cognito (SAML/OIDC) | LDAP/SAML/OIDC | Cognito / カスタム |
| **ホスティングモデル** | サーバーレス (Amplify Hosting) | サーバー (EC2/ECS) | CloudFront + S3 / Amplify |
| **運用負荷** | 低（マネージド） | 中（パッチ、アップグレード） | 低〜中 |
| **FSx for ONTAP アクセス** | S3 AP via Lambda | External Storage (S3 AP 直接) | S3 AP via Lambda |
| **マルチプロトコル可視性** | S3 AP 経由のみ | NFS マウント + S3 AP | S3 AP 経由のみ |
| **オフラインファイル編集** | 不可 | デスクトップ/モバイル同期クライアント | 不可 |
| **コラボレーション機能** | カスタム実装 | 組み込み（共有、コメント） | カスタム実装 |
| **インフラコスト** | ~$5-10/月 | ~$50-100/月 (EC2) | ~$5-20/月 |
| **言語/フレームワーク** | TypeScript + React | PHP（サーバー） | 任意 |
| **AD 統合** | Cognito フェデレーション | ネイティブ LDAP/AD | Cognito フェデレーション |
| **モバイルアクセス** | レスポンシブ Web | ネイティブアプリ (iOS/Android) | レスポンシブ Web |
| **S3 AP Presigned URL** | 動作する（※ドキュメント上 Not supported。[詳細](./s3ap-compatibility-notes.md#presigned-url-support)） | 同左 | 同左 |

---

## 選び方ガイド

### Amplify Gen2 が適する状況

- TypeScript/React に慣れたフロントエンド開発者がいる
- サーバーレスファースト（運用負荷最小化）を重視する
- UI からカスタム処理ワークフローを起動したい
- ブランチベースの環境管理（dev/staging/prod）を活用したい
- Cognito + AppSync + Step Functions の密な統合を求める

### Nextcloud が適する状況

- すぐに使えるファイル管理 UI が必要（フロントエンド開発なし）
- 組み込みのコラボレーション機能（共有、コメント、バージョニング UI）が欲しい
- 既存の LDAP/AD インフラに直接接続したい
- デスクトップ/モバイル同期クライアントでオフラインアクセスが必要
- PHP アプリケーション運用（EC2/ECS）に抵抗がない
- NFS マウントと S3 AP の両方でファイルを同時閲覧したい

### カスタムビルドが適する状況

- すべてのアーキテクチャ決定を完全にコントロールしたい
- Amplify にも Nextcloud にも合わない特定の UI/UX 要件がある
- 既存のエンタープライズポータルに統合したい
- 特定のフレームワーク（Vue, Angular, Svelte 等）を使いたい

### フロントエンドが不要な場合

- 処理が完全自動化されている（EventBridge Scheduler トリガー）
- 結果は NFS/SMB 経由で既存ツールが消費する
- AWS Console や CLI で十分
- 既存のモニタリングダッシュボード（Grafana, CloudWatch）で可視性が確保されている

---

## Amplify Gen2 と Nextcloud の共存アーキテクチャ

両者は排他的ではなく、**それぞれの得意領域を活かして併用**できます。

### 役割分担

| 機能 | Nextcloud が担当 | Amplify Gen2 が担当 |
|---|---|---|
| ファイル閲覧・ダウンロード | ✅ External Storage で即利用可 | ✅ ListFiles Lambda + 画像プレビュー |
| ファイルアップロード | ✅ ドラッグ&ドロップ、同期クライアント | ❌ 現在未実装 |
| デスクトップ/モバイル同期 | ✅ 公式クライアント | ❌ |
| 共有リンク・コメント | ✅ 組み込み | ❌ |
| AI/ML 処理ワークフロー起動 | ⚠️ Webhook で可能だが設定が必要 | ✅ AppSync Mutation → Step Functions |
| 処理結果のリアルタイム表示 | ❌ ポーリング機構なし | ✅ 5秒ポーリング + ステータスバッジ |
| ジョブ実行履歴 | ❌ | ✅ DynamoDB (owner-based auth) |
| 処理パターン選択 UI | ❌ | ✅ ドロップダウン + パラメータ入力 |
| データ分類ラベル表示 | ❌ | ✅ dataClassification 表示 |
| FlexClone スナップショット復元 | ❌ | ✅ UI から直接実行 |
| FlexClone ステータス確認 | ❌ | ✅ Results タブで表示 |

### 共存時のアーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│  ユーザー                                                        │
│  ┌─────────────────────┐   ┌──────────────────────────────────┐ │
│  │ Nextcloud           │   │ Amplify Gen2 Portal              │ │
│  │ (ファイル管理)       │   │ (処理ダッシュボード)              │ │
│  │ - 閲覧/DL/UL        │   │ - パターン選択                   │ │
│  │ - 同期クライアント    │   │ - ジョブ投入                     │ │
│  │ - 共有/コメント      │   │ - 結果確認                       │ │
│  └────────┬────────────┘   └──────────────┬───────────────────┘ │
└───────────┼───────────────────────────────┼─────────────────────┘
            │                               │
            │ S3 AP (External Storage)      │ AppSync → Step Functions
            │ or NFS (Direct Mount)         │ + ListFiles Lambda → S3 AP
            │                               │
            ▼                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  FSx for ONTAP                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ Volume (/vol/data)                                        │   │
│  │ NFS + SMB + S3 AP — 同一データ、マルチプロトコル             │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 共存のポイント

1. **データは1箇所**: 両方とも同じ FSx for ONTAP ボリューム/S3 AP にアクセス。データの二重管理は不要。
2. **認証は独立**: Nextcloud は LDAP/SAML、Amplify は Cognito。ユーザーベースが異なっても問題なし。
3. **ネットワーク分離可能**: Nextcloud を VPC 内（NFS + VPC-origin S3 AP）、Amplify を VPC 外（Internet-origin S3 AP）に配置可能。
4. **段階的導入**: まず Nextcloud でファイル管理を始め、処理ニーズが出てきたら Amplify ポータルを追加。
5. **スループット共有**: 両方が同じ FSx for ONTAP の帯域を消費する点に注意（[スループット計画](#スループットと容量計画)参照）。

### 典型的な併用シナリオ

```
Day 1: チームが Nextcloud でファイルを閲覧・共有
       （NFS/SMB ユーザーと同じデータを Web から見える）

Day 2: 管理者が「この契約書フォルダを AI で分類したい」と判断
       → Amplify ポータルの Process タブで UC1 (Legal Compliance) を実行

Day 3: 処理結果（分類ラベル付き）が同じボリュームに書き戻される
       → Nextcloud ユーザーも NFS/SMB ユーザーも結果ファイルを即座に閲覧可能
```

---

## Amplify Gen2 統合パターン

### アーキテクチャ詳細

```
┌────────────────────────────────────────────────────────┐
│  Amplify Gen2                                          │
│  ┌────────────┐  ┌──────────────────────────────────┐  │
│  │ defineAuth │  │ defineData (AppSync)              │  │
│  │ Cognito    │  │  - startProcessing mutation       │  │
│  │ +SAML/OIDC │  │  - getJobStatus query             │  │
│  │            │  │  - onJobComplete subscription     │  │
│  └────────────┘  │  HTTP Resolver → Step Functions   │  │
│                  └──────────────┬───────────────────┘  │
│  ┌────────────────────────────────────────────────────┐│
│  │ CDK カスタムリソース                                ││
│  │  - 既存 Step Functions ASL を参照                   ││
│  │  - VPC Lambda: ONTAP API (Discovery)               ││
│  │  - VPC外 Lambda: S3 AP (Processing)                ││
│  └────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────┘
```

### 実装のポイント

**AppSync → Step Functions（中間 Lambda 不要）**:

AppSync HTTP Resolver が Step Functions を直接呼び出すことで、Wrapper Lambda のコールドスタートを排除:

```typescript
// amplify/data/resource.ts（概念例）
const schema = a.schema({
  startProcessing: a.mutation()
    .arguments({ ucPattern: a.string(), inputPrefix: a.string() })
    .returns(a.json())
    .authorization(allow => [allow.authenticated()])
    .handler(a.handler.custom({
      dataSource: 'StepFunctionsHttpDataSource',
      entry: './resolvers/start-processing.js'
    })),
  getJobStatus: a.query()
    .arguments({ executionArn: a.string() })
    .returns(a.json())
    .authorization(allow => [allow.authenticated()])
    .handler(a.handler.custom({
      dataSource: 'StepFunctionsHttpDataSource',
      entry: './resolvers/get-status.js'
    }))
});
```

**VPC 分離の維持**: Discovery Lambda（ONTAP REST API）は VPC 内配置。Processing Lambda（Internet-origin S3 AP）は VPC 外。既存パターンのアーキテクチャをそのまま踏襲。

**既存 ASL の再利用**: CDK カスタムリソースが既存の `statemachine/workflow.asl.json` を変更なしで参照。

### 推奨ディレクトリ構成

```
solutions/amplify-portal/
├── amplify/
│   ├── backend.ts
│   ├── auth/resource.ts
│   ├── data/resource.ts
│   └── custom/step-functions.ts
├── src/
│   ├── App.tsx
│   ├── components/
│   │   ├── FileExplorer.tsx
│   │   ├── JobSubmitForm.tsx
│   │   └── ResultsViewer.tsx
│   └── pages/
├── tests/                          # フロントエンドテスト
│   ├── components/
│   └── integration/
├── package.json
├── tsconfig.json
├── Makefile                        # amplify-dev, amplify-test ターゲット
└── README.md
```

**開発・テスト**:
- `make amplify-dev`: `npx ampx sandbox` ラッパー（DemoMode バックエンドに接続）
- `make amplify-test`: React コンポーネントテスト + AppSync resolver ユニットテスト
- バックエンド側のテストは既存の `make test-uc1` 等と独立して実行

---

## Nextcloud 統合パターン

### アーキテクチャ詳細

```
┌────────────────────────────────────────────────────────┐
│  Nextcloud (EC2 or ECS Fargate)                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ External Storage App                             │  │
│  │  - S3 AP バックエンド（ファイル閲覧）               │  │
│  │  - FSx for ONTAP ボリュームをフォルダ表示           │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Workflow App / Webhook                           │  │
│  │  - ファイルアップロード/タグ付けで処理トリガー       │  │
│  │  - API Gateway → Step Functions 呼び出し          │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ NFS マウント（オプション）                         │  │
│  │  - プレビュー/メタデータ用の直接ボリュームアクセス    │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│  API Gateway (REST)                                    │
│  → Step Functions StartExecution                       │
└────────────────────────────────────────────────────────┘
```

### 実装のポイント

**External Storage via S3 AP**: Nextcloud の「External Storage」アプリは S3 互換バックエンドをサポート。S3 AP エイリアスをバケット名として設定すると、FSx for ONTAP のファイルを Nextcloud のファイルブラウザに表示できる。

**S3 AP と Nextcloud の制約事項**:
- Presigned URL は AWS ドキュメント上「Not supported」だが、実際にはクライアント側で生成・利用可能（GetObject の署名付きリクエストとして動作する。[詳細](./s3ap-compatibility-notes.md#presigned-url-support)）。ただし本番依存は非推奨のため、Nextcloud はサーバープロセス経由でのダウンロードプロキシも選択可能
- `ListObjectsV2` のページネーション（1リクエスト最大1000オブジェクト）は Nextcloud の S3 バックエンドがネイティブに処理
- PutObject（最大 5 GB）により Nextcloud UI から FSx for ONTAP へのアップロードが可能

**NFS マウントの併用**: より低レイテンシのファイル閲覧やプレビュー生成には、Nextcloud が FSx for ONTAP ボリュームを NFS で直接マウントする構成も可能（同一 VPC/サブネット内の EC2 配置が必要）。

**処理トリガーの選択肢**:
1. Nextcloud Workflow App → HTTP webhook → API Gateway → Step Functions
2. Nextcloud イベント（ファイルタグ付け）→ Lambda → Step Functions
3. 手動: ユーザーがカスタム Nextcloud アプリのボタンをクリック → API 呼び出し

### インフラ要件

| コンポーネント | スペック | 月額コスト |
|---|---|---|
| EC2 (Nextcloud サーバー) | t3.medium 以上 | ~$30-50 |
| RDS or Aurora (メタデータ DB) | db.t3.micro | ~$15-30 |
| EFS or EBS (Nextcloud データ) | アプリ設定/キャッシュのみ | ~$5-10 |
| ALB (HTTPS 終端) | Application Load Balancer | ~$20 |
| **増分合計** | | **~$70-110/月** |

> **補足**: ECS Fargate デプロイも可能だが、コンテナ管理の複雑性が追加される。

---

## カスタムビルドパターン

独自フロントエンドを構築するチーム向け:

```
┌────────────────────────────────────────────────────────┐
│  CloudFront + S3 (静的ホスティング)                      │
│  または Amplify Hosting (静的のみ)                       │
│  ┌──────────────────────────────────────────────────┐  │
│  │ SPA (React/Vue/Angular/Svelte)                   │  │
│  │  - API 経由のファイル一覧取得                       │  │
│  │  - ジョブ投入フォーム                              │  │
│  │  - 結果ポーリング / WebSocket                      │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│  API Gateway (REST or HTTP API)                        │
│  + Cognito User Pool Authorizer                        │
│  → Step Functions / Lambda                             │
└────────────────────────────────────────────────────────┘
```

このアプローチは最大の柔軟性を提供するが、ファイルブラウジング、認証フロー、リアルタイム更新をゼロから実装する必要がある。

---

## スループットと容量計画

> **Storage note**: FSx for ONTAP S3 AP の帯域幅は NFS/SMB ワークロードと共有されます。既存 NAS トラフィックと並行する Web UI ユーザーの同時利用を計画してください。

| シナリオ | S3 AP への影響 | ガイダンス |
|----------|:---:|---|
| 10名がディレクトリ一覧を表示 | ほぼ無視可能 | 特別な計画不要 |
| 10名が 1 GB ファイルを同時ダウンロード | ~80 Mbps（例: 128 MBps 構成で約8%） | `TotalThroughput` メトリクスを監視 |
| 50名が閲覧 + 随時ダウンロード | 典型的に ~20-40 Mbps | 多くのデプロイメントで許容範囲 |
| 100名以上が同時に大ファイル転送 | 顕著（容量に依存） | スループット容量増加または FlexCache 検討 |

**整合性モデル**: FSx for ONTAP S3 AP は ONTAP ファイルシステムの状態をリアルタイムに反映します。NFS/SMB で書き込んだファイルは、S3 AP のリスト取得で即座に見えます（結果整合性の遅延なし）。

**ListObjectsV2 のページネーション**: 1リクエストあたり最大1000オブジェクトを返却。多数のファイルがあるディレクトリでは、UI 側でページネーションの実装が必要。

**サムネイル/プレビュー生成のレイテンシ**: Nextcloud や独自 UI でプレビューを生成する場合、ファイルごとに GetObject（または Range GET で先頭バイトのみ）が発生します。1ディレクトリに100ファイルある場合、逐次的にプレビュー生成すると数秒のレイテンシが発生する可能性があります。並列リクエストまたはプレビューキャッシュで緩和してください。

> **補足**: スループット容量は FSx for ONTAP ファイルシステムの構成により異なります（128/256/512/1024/2048/4096 MBps）。上記の数値例は 128 MBps 構成を前提としています。実際の容量は AWS Console → FSx → ファイルシステム詳細で確認してください。

---

## 認証とコンプライアンス連鎖

ユーザー操作からファイルアクセスまでの完全な監査証跡:

```
ユーザー操作 → 認証トークン (Cognito/LDAP/SAML)
  → API リクエストログ (AppSync/API Gateway CloudWatch)
    → Step Functions 実行履歴
      → Lambda CloudWatch Logs
        → S3 AP 操作 (CloudTrail Data Events)
          → ONTAP 監査ログ (fpolicy/ネイティブ監査)
```

| 要件 | Amplify Gen2 | Nextcloud | カスタム |
|---|---|---|---|
| エンタープライズ IdP (SAML/OIDC) | Cognito フェデレーション | SAML/LDAP アプリ | Cognito フェデレーション |
| MFA | Cognito 組み込み | プラグイン | Cognito 組み込み |
| WAF 保護 | CloudFront + WAF | ALB + WAF | CloudFront + WAF |
| データ滞留 (in-region) | Lambda プロキシ (CDN 経由しない) | サーバーサイドプロキシ | Lambda プロキシ |
| 既存 shared/ モジュール連携 | `data_classification`, `lineage`, `human_review` はバックエンド Lambda で動作 | 同左 | 同左 |

> **Governance note**: S3 AP の Presigned URL はドキュメント上「Not supported」ですが、GetObject の署名付きリクエストとして実際には動作します（[詳細](./s3ap-compatibility-notes.md#presigned-url-support)）。ただし本番依存は非推奨のため、データガバナンスを重視する場合はサーバーサイドコンポーネント（Lambda または Nextcloud サーバー）経由でのアクセスを推奨します。これにより、データ滞留制御がアプリケーション層で担保されます。

> **Compliance note**: 処理結果ファイルには `data_classification` ラベル（INTERNAL/CUI/PUBLIC 等）が付与されます。ファイルポータル UI でこのラベルをユーザーに表示することを推奨します。バックエンドの `shared/data_classification.py` モジュールが分類ロジックを提供します。

> **Incident response note**: ファイルポータルが侵害された場合の対応は [Incident Response Playbook](./incident-response-playbook.md) を参照してください。Cognito トークン無効化、IAM キーローテーション、CloudTrail ログ保全が初動です。

---

## 導入ロードマップ

### クイックデモ（30分パス）

最速でファイルポータルの動作を見たい場合:

```bash
# Nextcloud Docker Compose (ローカル開発/デモ用 — 本番用途ではない)
docker run -d -p 8080:80 nextcloud:latest
# → localhost:8080 にアクセス、管理者アカウント作成
# → External Storage App を有効化
# → DemoMode の S3 バケットを External Storage として設定
```

> これは評価・デモ目的のみです。本番デプロイには後述のフェーズを踏んでください。

### Amplify Gen2 パス

| Phase | 作業内容 | 所要時間 | FSx for ONTAP 必要? |
|---|---|---|---|
| 1. UI プロトタイプ | Amplify sandbox + DemoMode バックエンド。認証・ワークフロー起動・結果表示の動作確認 | 2-3日 | 不要 |
| 2. バックエンド接続 | 既存 Step Functions ASL を CDK カスタムリソースとして参照。AppSync HTTP Resolver で接続 | 1-2日 | 不要（DemoMode） |
| 3. 本番データ接続 | FSx for ONTAP S3 AP に接続。VPC Lambda 配置、容量計画、監査設定 | 1-2週間 | 必要 |

### Nextcloud パス

| Phase | 作業内容 | 所要時間 | FSx for ONTAP 必要? |
|---|---|---|---|
| 1. サーバーセットアップ | EC2/ECS に Nextcloud デプロイ。テスト用 S3 バケットで External Storage 設定（DemoMode） | 1-2日 | 不要 |
| 2. S3 AP 統合 | External Storage を FSx for ONTAP S3 AP に接続。閲覧・アップロード検証 | 1-2日 | 必要 |
| 3. ワークフロー統合 | ファイル操作時に Step Functions を起動する webhook/API 設定 | 2-3日 | 必要 |
| 4. 本番堅牢化 | SAML、WAF、バックアップ、監視、パッチスケジュール | 1-2週間 | 必要 |

---

## コスト概算（増分）

既存の FSx for ONTAP + Lambda + Step Functions インフラに対する**追加コスト**:

| コンポーネント | Amplify Gen2 | Nextcloud | カスタムビルド |
|---|---|---|---|
| ホスティング | ~$0（Free Tier） | ~$50-100 (EC2+RDS+ALB) | ~$5 (S3+CF) |
| 認証 | ~$0.28 (50 MAU) | 含む | ~$0.28 (50 MAU) |
| API レイヤー | ~$4/100万リクエスト | ~$20 (API GW) | ~$4/100万リクエスト |
| ビルド/デプロイ | 含む | 手動/CI | 手動/CI |
| **月額合計（低トラフィック）** | **~$5-10** | **~$70-110** | **~$10-25** |

> **コンテキスト**: 上記は増分コストです。コアインフラ（FSx for ONTAP ~$194、NAT Gateway ~$32 等）は共通。

---

## トレードオフまとめ

| 特性 | Amplify Gen2 | Nextcloud | カスタムビルド |
|---|---|---|---|
| デモまでの時間 | 早い | 早い（ファイル閲覧は即時） | 遅い |
| 組み込みファイル管理 UI | なし（構築必要） | あり（リッチなファイルマネージャ） | なし（構築必要） |
| デスクトップ/モバイル同期 | なし | あり（公式クライアント） | なし |
| 運用オーバーヘッド | 低（サーバーレス） | 中（サーバーパッチ適用） | 低〜中 |
| 処理ワークフロー統合 | ネイティブ（AppSync → SFn） | Webhook ベース | API Gateway → SFn |
| コスト（低トラフィック） | 低 (~$5-10) | 高め (~$70-110) | 低〜中 (~$10-25) |
| カスタマイズの自由度 | CDK Override | プラグインエコシステム | 完全 |
| 必要なチームスキル | TypeScript + React | PHP 管理 + Linux | 任意 |
| ブランチベース環境 | 組み込み（Amplify sandbox） | 手動 | 手動 |
| 長期メンテナンス | Amplify がインフラ管理 | OS/アプリのパッチ・アップグレード | フレームワーク更新 |

---

## FAQ

**Q: Amplify Gen2 と Nextcloud を両方使えますか？**
A: はい。日常のファイル管理（閲覧、同期、共有）に Nextcloud、処理ダッシュボード/ジョブ投入 UI に Amplify、という併用が可能です。同じ FSx for ONTAP バックエンドを S3 AP 経由で共有します。

**Q: ファイルポータルのフロントエンドは既存の NFS/SMB ユーザーに影響しますか？**
A: 直接的には影響しません。フロントエンドは S3 AP 経由でデータにアクセスし、S3 AP は NFS/SMB とスループット容量を共有します。一般的な Web UI 利用（閲覧、随時ダウンロード）では影響は無視可能です。詳細は[スループットと容量計画](#スループットと容量計画)を参照。

**Q: Nextcloud から始めて、後から Amplify を追加できますか？**
A: はい。バックエンドパターンはフロントエンド非依存です。ファイル閲覧用にまず Nextcloud を稼働させ、カスタム UI が必要になった段階で Amplify ベースの処理ダッシュボードを追加できます。

**Q: S3 AP Presigned URL でのダイレクトダウンロードは？**
A: AWS ドキュメント上は「Not supported」ですが、Presigned URL は実際にはクライアント側の SigV4 署名計算であり、使用時に実行されるのは通常の GetObject リクエストのため動作します（[検証結果と AWS Support の見解](./s3ap-compatibility-notes.md#presigned-url-support)）。ただし AWS Support は本番ワークロードでの依存を非推奨としています。データガバナンスの観点でサーバーサイドプロキシ経由を選択することも有効ですが、技術的にはダイレクトダウンロードも可能です。

**Q: 規制環境（FISC、HIPAA）ではどのアプローチが使えますか？**
A: 3つすべてが適切に設定すれば規制要件を満たせます。主要な制御（監査ログ、暗号化、アクセス制御）は共有バックエンド層にあります。フロントエンド固有の考慮事項: Amplify Gen2（Cognito SAML + WAF）、Nextcloud（LDAP + ALB 上の WAF）、カスタム（実装依存）。

**Q: FSx for ONTAP なしで DemoMode でポータルも使えますか？**
A: はい。DemoMode は通常の S3 バケットを使用します。3つすべてのフロントエンド選択肢が DemoMode バックエンドに接続して開発・デモンストレーション可能です。

**Q: Nextcloud の External Storage で S3 AP を使う際の注意点は？**
A: Nextcloud の S3 バックエンド設定でエンドポイント URL と認証情報を正しく設定する必要があります。また、S3 AP の NetworkOrigin が `Internet` であること（VPC 外からのアクセス）が前提です。VPC 内に Nextcloud を配置する場合は NAT Gateway 経由、または同一 VPC 内 Interface VPC Endpoint 経由のアクセスとなります。

---

## 関連ドキュメント

- [Nextcloud External Storage セットアップガイド](./nextcloud-external-storage-s3ap.md) — Nextcloud + FSx for ONTAP S3 AP のステップバイステップ設定手順
- [Quick Desktop MCP セットアップガイド](./quick-desktop-mcp-setup.md) — Amazon Quick + AgentCore MCP Gateway で自然言語ファイル操作
- [AgentCore MCP デモガイド](./demo-agentcore-mcp-quick-desktop.md) — E2E デモ（list_files / read_file / search_files）+ スクリーンショット
- [AgentCore MCP 残課題トラッカー](./agentcore-mcp-remaining-issues.md) — 既知の問題と対応状況
- [代替アーキテクチャ比較 (S3 AP vs EFS vs NFS)](./comparison-alternatives.md) — バックエンドアーキテクチャ比較
- [S3AP 互換性ノート](./s3ap-compatibility-notes.md) — Presigned URL 制限を含む既知の制約
- [Demo Mode ガイド](./demo-mode-guide.md) — FSx for ONTAP なしでの実行方法
- [コスト計算機](./cost-calculator.md) — 全体インフラのコスト見積もり
- [パターン選択ガイド](./pattern-selection-guide.md) — ワークロードに適した UC パターン
- [S3AP パフォーマンス考慮事項](./s3ap-performance-considerations.md) — スループット設計ガイダンス
- [AD-Joined SVM S3 AP 前提条件](./en/ad-joined-svm-s3ap-prerequisites.md) — AD DC 到達性要件

---

*最終更新: 2026-07 | 対象: FSx for ONTAP S3 AP Serverless Patterns v1.x*
