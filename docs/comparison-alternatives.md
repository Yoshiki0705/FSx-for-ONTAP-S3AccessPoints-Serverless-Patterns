# 代替アーキテクチャ比較 — S3 AP vs EFS vs NFS マウント vs DataSync

## 概要

「なぜ FSx for ONTAP S3 Access Points + Lambda なのか？」という質問に対する
技術的な比較資料です。

## 比較マトリクス

| 観点 | FSx for ONTAP S3 AP + Lambda | EFS + Lambda | EC2 NFS マウント | DataSync → S3 + Lambda |
|------|:---:|:---:|:---:|:---:|
| **データ移動** | なし（in-place 読み取り） | なし（直接マウント） | なし（直接マウント） | あり（コピー） |
| **サーバーレス** | ✅ 完全サーバーレス | ✅ Lambda + EFS | ❌ EC2 必要 | ✅ Lambda (S3 側) |
| **NTFS ACL 保持** | ✅ ONTAP REST API で取得 | ❌ POSIX のみ | ✅ NFS/SMB 経由 | ❌ S3 にコピー時に喪失 |
| **スケーラビリティ** | ✅ Lambda 並列 | ✅ Lambda 並列 | ⚠️ EC2 スケール必要 | ✅ Lambda 並列 |
| **レイテンシ** | 数十 ms (S3 API) | < 1 ms (NFS) | < 1 ms (NFS) | N/A (非同期) |
| **スループット** | FSx 帯域共有 | EFS バースト/プロビジョンド | FSx 帯域共有 | DataSync 帯域 |
| **コスト (処理側)** | Lambda 従量課金 | Lambda + EFS 従量 | EC2 常時稼働 | Lambda 従量課金 |
| **コスト (ストレージ)** | FSx for ONTAP (既存) | EFS 追加 | FSx for ONTAP (既存) | S3 追加 |
| **VPC 依存** | NetworkOrigin による | ✅ VPC 必須 | ✅ VPC 必須 | ❌ 不要 (S3 側) |
| **イベント駆動** | FPolicy (Phase 10) | S3 Event (コピー後) | inotify/FPolicy | S3 Event Notifications |
| **マルチプロトコル** | NFS + SMB + S3 | NFS のみ | NFS or SMB | S3 のみ (コピー後) |
| **データ鮮度** | リアルタイム | リアルタイム | リアルタイム | 同期遅延あり |
| **運用複雑性** | 中 | 低 | 高 | 中 |

## 選択ガイド

### FSx for ONTAP S3 AP + Lambda を選ぶべき場合

- ✅ 既に FSx for ONTAP を使用している
- ✅ NTFS ACL / AD 統合が必要
- ✅ データを移動したくない（規制要件、データ主権）
- ✅ NFS/SMB ユーザーと AI 処理結果を同じボリュームで共有したい
- ✅ サーバーレスでスケーラブルな処理が必要
- ✅ FlexCache によるマルチリージョン/マルチサイト対応が必要

### EFS + Lambda を選ぶべき場合

- ✅ POSIX 権限で十分（NTFS ACL 不要）
- ✅ サブミリ秒のレイテンシが必要
- ✅ シンプルな構成を優先
- ✅ FSx for ONTAP を使用していない

### EC2 NFS マウントを選ぶべき場合

- ✅ 長時間実行のバッチ処理（Lambda 15 分制限を超える）
- ✅ 大量のメモリ/GPU が必要
- ✅ 既存の EC2 ベースパイプラインがある
- ✅ ファイルシステムの全機能（ロック、シンボリックリンク等）が必要

### DataSync → S3 + Lambda を選ぶべき場合

- ✅ S3 Event Notifications によるイベント駆動が必須
- ✅ S3 の全機能（バージョニング、ライフサイクル、Presigned URL）が必要
- ✅ データのコピーが許容される
- ✅ FSx for ONTAP を使用していない

## コスト比較（月額概算、100 files/日、1 MB 平均）

| アーキテクチャ | 処理コスト | ストレージコスト | 合計 |
|--------------|-----------|----------------|------|
| FSx for ONTAP S3 AP + Lambda | ~$15 | $0 (既存 FSx) | **~$15** |
| EFS + Lambda | ~$15 | ~$30 (100 GB EFS) | **~$45** |
| EC2 NFS マウント | ~$50 (t3.medium 常時) | $0 (既存 FSx) | **~$50** |
| DataSync → S3 + Lambda | ~$15 + DataSync $5 | ~$2.3 (100 GB S3) | **~$22** |

> **注記**: 上記は概算であり、実際のコストはワークロード特性により異なります。FSx for ONTAP の既存環境を前提としています。

## FAQ

**Q: S3 AP のレイテンシ（数十 ms）は問題にならないか？**
A: バッチ処理（定期スキャン）では問題になりません。リアルタイム応答が必要な場合は EFS + Lambda を検討してください。

**Q: S3 AP で書き込みもできるか？**
A: はい。PutObject（最大 5 GB）をサポートしています。AI 処理結果を同じボリュームに書き戻し、NFS/SMB ユーザーが閲覧できます。

**Q: FlexCache と EFS の違いは？**
A: FlexCache は ONTAP ボリュームのキャッシュであり、Origin のデータ変更が自動的に反映されます。EFS は独立したファイルシステムです。

---

> **Governance Caveat**: 本比較は技術的な観点からの参考情報です。最終的なアーキテクチャ選択は、顧客の要件、既存環境、規制要件を総合的に評価して決定してください。
