# Phase 13 — AWS 環境検証 未実施項目一覧

**作成日**: 2026-05-18
**状態**: 全項目未検証（コード・テンプレート・ユニットテストのみ完了）

> Phase 13 で追加した全パターン（FC1–FC6）は、ローカル環境での pytest（699 passed）、ruff lint（0 errors）、cfn-lint（0 errors）のみ実施済み。AWS 実環境でのデプロイ・実行は一切行っていない。

---

## 検証カテゴリ別 未実施項目

### A. FlexCache 基本機能（ONTAP REST API 経由）

| # | 検証項目 | 前提条件 | リスク | 優先度 |
|---|---------|---------|--------|--------|
| A-1 | FlexCache volume の ONTAP REST API 経由作成 | FSx for ONTAP + Secrets Manager | FlexCache 作成 API のパラメータ/レスポンス形式が想定と異なる可能性 | **高** |
| A-2 | FlexCache volume の ONTAP REST API 経由削除 | A-1 で作成した FlexCache | 削除時の volume busy エラーハンドリング | **高** |
| A-3 | FlexCache prepopulate の実行と完了待ち | A-1 + ONTAP 9.13.1+ | prepopulate の dir_paths 指定形式、ジョブ完了時間 | **高** |
| A-4 | ONTAP 非同期ジョブ (GET /cluster/jobs/{uuid}) のポーリング | A-1 | ジョブ状態遷移（queued→running→success）の実際の挙動 | **高** |
| A-5 | FlexCache 一覧取得（名前フィルタ） | FSx for ONTAP | list_flexcaches の fields パラメータ互換性 | 中 |
| A-6 | 冪等性チェック（同名 FlexCache 存在時のスキップ） | A-1 | 409 Conflict レスポンスの実際の形式 | 中 |
| A-7 | FlexCache 作成失敗時のエラーメッセージ解析 | 容量不足のアグリゲート | エラーメッセージのパース可否 | 中 |

### B. FlexCache + S3 Access Points 組み合わせ

| # | 検証項目 | 前提条件 | リスク | 優先度 |
|---|---------|---------|--------|--------|
| B-1 | **FlexCache volume に S3 AP を attach 可能か** | FSx for ONTAP + FlexCache volume | **最重要**: AWS ドキュメントに明示的記載なし。不可の場合はアーキテクチャ変更が必要 | **最高** |
| B-2 | FlexCache volume の S3 AP 経由 ListObjectsV2 | B-1 が成功した場合 | キャッシュ済み/未キャッシュデータの見え方 | **最高** |
| B-3 | FlexCache volume の S3 AP 経由 GetObject | B-1 が成功した場合 | cache miss 時のレイテンシ、タイムアウト | **最高** |
| B-4 | FlexCache volume の S3 AP 経由 GetObject（cache hit 時） | B-3 + prepopulate 済み | cache hit 時のレイテンシ改善の実測 | 高 |
| B-5 | FlexCache volume の S3 AP NetworkOrigin 設定 | B-1 | Internet/VPC Origin の選択と到達性 | 高 |

### C. CloudFormation デプロイ検証

| # | 検証項目 | テンプレート | リスク | 優先度 |
|---|---------|------------|--------|--------|
| C-1 | solutions/flexcache/anycast-dr/template.yaml デプロイ | flexcache-anycast-dr | SAM Transform + StateMachine Definition の互換性 | **高** |
| C-2 | solutions/flexcache/dynamic-render-workflow/template.yaml デプロイ | dynamic-flexcache-render-workflow | 同上 | **高** |
| C-3 | solutions/flexcache/rag-enterprise-files/template.yaml デプロイ | genai-rag-enterprise-files | 同上 | 高 |
| C-4 | solutions/flexcache/automotive-cae/template.yaml デプロイ | automotive-cae | 同上 | 高 |
| C-5 | solutions/flexcache/life-sciences-research/template.yaml デプロイ | life-sciences-research | 同上 | 中 |
| C-6 | solutions/flexcache/gaming-build-pipeline/template.yaml デプロイ | gaming-build-pipeline | 同上 | 中 |
| C-7 | 全スタックの CREATE_COMPLETE 確認 | C-1〜C-6 | IAM ポリシー、リソース名衝突 | **高** |
| C-8 | EventBridge Scheduler の作成・有効化確認 | C-1〜C-6 | スケジュール式の構文 | 中 |

### D. Lambda 関数実行検証

| # | 検証項目 | 対象 Lambda | リスク | 優先度 |
|---|---------|-----------|--------|--------|
| D-1 | HealthCheck Lambda（SimulationMode=true） | flexcache-anycast-dr | 環境変数の受け渡し | 高 |
| D-2 | HealthCheck Lambda（SimulationMode=false） | flexcache-anycast-dr | ONTAP REST API 到達性、認証 | **高** |
| D-3 | RouteDecision Lambda + DynamoDB 連携 | flexcache-anycast-dr | DynamoDB テーブルの Scan 動作 | 高 |
| D-4 | Discovery Lambda + S3 AP 連携 | flexcache-anycast-dr | S3 AP エイリアスでの ListObjectsV2 | **高** |
| D-5 | CreateFlexCache Lambda（SimulationMode=false） | dynamic-flexcache-render-workflow | ONTAP REST API FlexCache 作成 | **高** |
| D-6 | CleanupFlexCache Lambda（SimulationMode=false） | dynamic-flexcache-render-workflow | ONTAP REST API FlexCache 削除 | **高** |
| D-7 | SubmitJob Lambda | dynamic-flexcache-render-workflow | モックジョブ ID 生成 | 低 |
| D-8 | MonitorJob Lambda | dynamic-flexcache-render-workflow | ポーリングループの動作 | 低 |
| D-9 | Chunking Lambda + S3 AP GetObject | genai-rag-enterprise-files | ファイル読み取り、テキスト抽出 | 高 |
| D-10 | Embedding Lambda + Bedrock InvokeModel | genai-rag-enterprise-files | Titan Embeddings API 呼び出し | 高 |
| D-11 | ACL Extraction Lambda + ONTAP REST API | genai-rag-enterprise-files | get_file_security API | 高 |
| D-12 | SolverOutputParser Lambda + S3 AP Range GetObject | automotive-cae | Range ヘッダーでの部分読み取り | 中 |
| D-13 | QualityCheck Lambda + Bedrock | automotive-cae | Nova Pro API 呼び出し | 中 |
| D-14 | Life Sciences Discovery Lambda | life-sciences-research | S3 AP ListObjectsV2 | 中 |
| D-15 | Gaming Discovery Lambda | gaming-build-pipeline | S3 AP ListObjectsV2 | 中 |
| D-16 | Gaming LogAnalysis Lambda + Bedrock | gaming-build-pipeline | Bedrock ログ分析 | 中 |

### E. Step Functions ワークフロー E2E 検証

| # | 検証項目 | ワークフロー | リスク | 優先度 |
|---|---------|------------|--------|--------|
| E-1 | FlexCache AnyCast ワークフロー全体実行 | flexcache-anycast-dr | HealthCheck→RouteDecision→Report の連携 | **高** |
| E-2 | Dynamic FlexCache ワークフロー全体実行（Simulation） | dynamic-flexcache-render-workflow | Create→Submit→Monitor→Cleanup→Report | **高** |
| E-3 | Dynamic FlexCache ワークフロー全体実行（Real ONTAP） | dynamic-flexcache-render-workflow | 実 FlexCache 作成→削除のライフサイクル | **最高** |
| E-4 | Dynamic FlexCache 失敗時の FailureHandler 動作 | dynamic-flexcache-render-workflow | Catch→FailureHandler→Cleanup の遷移 | 高 |
| E-5 | GenAI RAG インデックスワークフロー | genai-rag-enterprise-files | Discovery→Map(Chunk→Embed→ACL)→Report | 高 |
| E-6 | Automotive CAE ワークフロー | automotive-cae | Discovery→Map(Parse→QC)→Report | 中 |
| E-7 | Life Sciences ワークフロー | life-sciences-research | Discovery→Map(Classify→Metadata)→Report | 中 |
| E-8 | Gaming Build ワークフロー | gaming-build-pipeline | Discovery→Map(QC→Log)→Report | 中 |
| E-9 | MonitorJob ポーリングループの実際の Wait 動作 | dynamic-flexcache-render-workflow | Wait State の 10 秒待機 | 中 |
| E-10 | Map State の MaxConcurrency 制御 | 全ワークフロー | 並列実行数の制御 | 低 |

### F. ネットワーク・ルーティング検証

| # | 検証項目 | 前提条件 | リスク | 優先度 |
|---|---------|---------|--------|--------|
| F-1 | Lambda → ONTAP 管理 IP の到達性（VPC 内） | VPC + SG + FSx for ONTAP | セキュリティグループ設定ミス | **高** |
| F-2 | Lambda → S3 AP の到達性（VPC 内/外） | S3 AP NetworkOrigin 設定 | VPC 内 Lambda + Internet Origin AP のタイムアウト | **高** |
| F-3 | Lambda → Secrets Manager の到達性 | VPC Endpoint or NAT | VPC 内 Lambda からの Secrets Manager アクセス | 高 |
| F-4 | Lambda → Bedrock の到達性 | VPC 外 or NAT | Bedrock API エンドポイントへの到達 | 中 |
| F-5 | Route 53 Failover/Weighted ルーティング動作 | Route 53 ホストゾーン | DNS TTL、ヘルスチェック連携 | 中 |
| F-6 | DynamoDB ルーティングテーブルの読み書き | DynamoDB テーブル | IAM ポリシー、テーブル名の一致 | 中 |

### G. DR / フェイルオーバー検証

| # | 検証項目 | 前提条件 | リスク | 優先度 |
|---|---------|---------|--------|--------|
| G-1 | FlexCache disconnected mode の動作確認 | FSx for ONTAP + FlexCache + Origin 停止 | FSx for ONTAP での disconnected mode サポート有無 | 高 |
| G-2 | Origin 到達不可時の FlexCache 読み取り継続 | G-1 | キャッシュ済みデータのみ読み取り可能か | 高 |
| G-3 | Route 53 ヘルスチェック失敗→フェイルオーバー | Route 53 + ヘルスチェック設定 | フェイルオーバー時間の実測 | 中 |
| G-4 | SnapMirror destination の break + FlexCache re-peer | SnapMirror 設定済み | re-peer の手順と所要時間 | 中 |
| G-5 | フェイルバック手順の実行 | G-3 or G-4 の後 | データ整合性、DNS 切戻し | 中 |

### H. 性能・コスト検証

| # | 検証項目 | 前提条件 | 目的 | 優先度 |
|---|---------|---------|------|--------|
| H-1 | FlexCache 作成時間の実測 | A-1 | PoC チェックリストの KPI 記入 | 高 |
| H-2 | FlexCache prepopulate 時間の実測 | A-3 | データ量別の所要時間 | 高 |
| H-3 | Cache hit ratio の実測 | B-4 | 性能改善効果の定量化 | 高 |
| H-4 | S3 AP 経由 GetObject レイテンシ（Origin vs FlexCache） | B-3, B-4 | FlexCache の効果測定 | 高 |
| H-5 | Step Functions 全体実行時間 | E-1〜E-8 | ワークフロー性能 | 中 |
| H-6 | Lambda コールドスタート時間 | D-1〜D-16 | 初回実行のレイテンシ | 低 |
| H-7 | 月間コストの実測 | 全スタックデプロイ後 | コスト分析の検証 | 中 |

### I. セキュリティ検証

| # | 検証項目 | 前提条件 | リスク | 優先度 |
|---|---------|---------|--------|--------|
| I-1 | IAM ポリシーの S3 AP ARN 形式が正しく動作するか | C-1〜C-6 | AccessDenied エラー | **高** |
| I-2 | Secrets Manager からの ONTAP 認証情報取得 | Secrets Manager シークレット作成 | シークレット形式の不一致 | **高** |
| I-3 | ONTAP RBAC 最小権限ロールでの FlexCache 操作 | ONTAP ユーザー作成 | 権限不足エラー | 高 |
| I-4 | TLS 検証有効時の ONTAP REST API 接続 | FSx for ONTAP 証明書 | 証明書検証エラー | 高 |
| I-5 | KMS 暗号化の S3 出力バケット書き込み | KMS キー | 暗号化エラー | 中 |
| I-6 | SNS 通知の送信確認 | SNS Topic + Email サブスクリプション | メール到達 | 低 |

---

## 検証優先度サマリー

### 最高優先度（ブロッカー）

| # | 項目 | 理由 |
|---|------|------|
| B-1 | FlexCache volume に S3 AP attach 可能か | 不可の場合、アーキテクチャ全体の前提が崩れる |
| E-3 | Dynamic FlexCache ワークフロー（Real ONTAP） | 本パターンの核心機能 |

### 高優先度（Phase 13 の価値証明に必須）

| # | 項目 |
|---|------|
| A-1〜A-4 | FlexCache CRUD + prepopulate の実動作 |
| B-2〜B-3 | FlexCache S3 AP 経由の読み取り |
| C-1〜C-2 | 主要テンプレートのデプロイ |
| D-2, D-5, D-6 | ONTAP REST API 連携 Lambda |
| E-1〜E-2 | 主要ワークフローの E2E |
| F-1〜F-2 | ネットワーク到達性 |
| I-1〜I-2 | IAM + Secrets Manager |

### 中優先度（機能完成度向上）

残りの C-3〜C-8, D-9〜D-16, E-4〜E-10, F-3〜F-6, G-1〜G-5, H-1〜H-7, I-3〜I-6

---

## 検証実施に必要な前提条件

### AWS リソース

- [ ] FSx for ONTAP ファイルシステム（既存 or 新規作成）
- [ ] FlexCache 作成可能なアグリゲート空き容量
- [ ] S3 Access Point（Origin volume に attach 済み）
- [ ] Secrets Manager シークレット（ONTAP 認証情報）
- [ ] VPC + サブネット + セキュリティグループ
- [ ] NAT Gateway or VPC Endpoints（Lambda VPC 内配置の場合）
- [ ] Amazon Bedrock モデルアクセス有効化（Titan Embeddings, Nova Pro）
- [ ] Route 53 ホストゾーン（DR 検証の場合）

### テストデータ

- [ ] GDS/OASIS ファイル（semiconductor-eda 検証用）
- [ ] レンダリングアセット（media-vfx / dynamic-flexcache 検証用）
- [ ] 研究データ（life-sciences 検証用）
- [ ] CAE solver output（automotive-cae 検証用）
- [ ] ゲームアセット（gaming-build 検証用）
- [ ] エンタープライズ文書（genai-rag 検証用）

### 推定所要時間

| フェーズ | 内容 | 推定時間 |
|---------|------|---------|
| 環境準備 | FSx for ONTAP + FlexCache + S3 AP + Secrets Manager | 2-3 時間 |
| B-1 検証 | FlexCache + S3 AP attach 可否 | 30 分 |
| C-1〜C-2 デプロイ | CloudFormation スタック作成 | 1 時間 |
| E-2 シミュレーション | Step Functions E2E（SimulationMode） | 30 分 |
| A-1〜A-4 + E-3 | Real ONTAP FlexCache ライフサイクル | 2-3 時間 |
| D-10 + D-11 | Bedrock + ONTAP ACL 連携 | 1 時間 |
| G-1〜G-5 | DR テスト | 3-4 時間 |
| **合計** | | **10-12 時間** |

---

## B-1 が失敗した場合の代替アーキテクチャ

FlexCache volume に S3 AP を attach できない場合:

```
代替構成:
- NFS/SMB クライアント → FlexCache volume（読み取り高速化）
- Lambda/Step Functions → Origin volume の S3 AP（サーバーレス処理）
- 両方を組み合わせ: クライアントアクセスとサーバーレス処理を分離
```

この場合、以下のドキュメント更新が必要:
1. `docs/support-matrix-fsx-ontap-flexcache-s3ap.md` の B-1 行を ❌ に更新
2. `solutions/flexcache/anycast-dr/README.md` の制約事項を更新
3. `docs/industry-workload-mapping.md` の FlexCache + S3 AP 組み合わせ図を修正
4. 各 UC の FlexCache セクションに「S3 AP は Origin volume 経由」の注記追加
