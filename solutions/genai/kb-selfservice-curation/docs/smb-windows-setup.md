# UC29 リテラル構成: Windows ドラッグ&ドロップ実構築ランブック

業務ユーザーが **Windows エクスプローラーで実際にドラッグ&ドロップ**して AI ナレッジを維持する、
文字どおりの体験を構築する手順。これまでの自動検証は S3 AP API による代替（プロキシ）であり、
本書はリテラル構成（AD + SMB + Windows クライアント）を作る。

> 一部は AWS API/CLI で自動化できるが、**SMB 共有/NTFS ACL 作成（ONTAP 管理・VPC 内）と
> Windows ドラッグ&ドロップ（RDP）は VPC 内ホスト/人手が必要**。

## 既存リソース（検証アカウント、ap-northeast-1）

| リソース | 値・状況 |
|---|---|
| FSx for ONTAP ファイルシステム | `fs-09ffe72a3b2b7dbbd`、VPC `vpc-0ae01826f906191af`、subnet `subnet-0e36804c7fbc819a6` |
| AD 連携 SVM | `FPolicySMB`（`svm-037cedb30df493c1e`）、ドメイン `FPOLICY.LOCAL`、SMB `FPOLSMB.FPOLICY.LOCAL`（10.0.15.0） |
| AD DNS/DC | 10.0.5.22 / 10.0.28.223（自己管理 AD）。DC EC2 `itani-vpc03-ad1`（stopped、共有） |
| ONTAP 管理 LIF | 10.0.15.0（VPC 内プライベート） |
| ONTAP 認証情報 | Secrets Manager `fsx-ontap-fsxadmin-credentials` |
| Windows クライアント候補 | `maru-win01`（別VPC・到達不可）, `test-fujiwara-win-for-itani-vpc03`（stopped） |

> **注意**: `FPolicySMB` SVM と AD（FPOLICY.LOCAL）は同僚の検証環境。共有リソースのため、
> 利用可否は事前合意が必要。専用環境にしたい場合は別途 AWS Managed Microsoft AD + 新規 SVM を作成する。

## 現状ブロッカー（実測・要ユーザー判断）

リテラル構成の試行で以下を実機確認した。先に進むには下記の判断・リソース提供が必要。

| 確認項目 | 実測結果 | 影響 |
|---|---|---|
| Windows identity S3 AP 作成（FPOLICY\Admin） | **失敗**: "Failed to lookup the provided user in ONTAP" | AD ユーザーを ONTAP が解決できない |
| AD DC `itani-vpc03-ad1`（172.29.2.77） | **stopped**、`vpc-061918058c0b96a8f`（172.29.x） | DC 停止中。ユーザー解決不可の一因 |
| Windows クライアント `test-fujiwara-win-for-itani-vpc03`（172.29.12.161） | **stopped**、同上 VPC（172.29.x） | RDP 操作元の候補だが停止中・別VPC |
| FSx for ONTAP ファイルシステム / FPolicySMB SVM | VPC `vpc-0ae01826f906191af`（10.0.x）、AD DNS 10.0.5.22 / 10.0.28.223 | DC/クライアント（172.29.x）と別セグメント。到達性に VPC ピアリング等の確認が必要 |
| `maru-win01`（172.30.1.253） | running だが `vpc-05192d06e1e91d756`（172.30.x） | さらに別VPC。FSx for ONTAP に到達不可 |

> いずれも**同僚の共有リソース**かつ**複数 VPC にまたがる**。停止 EC2 の起動・AD 認証情報・
> VPC 間到達性・RDP 人手操作が必要で、無断のトライ&エラー変更は行わない（安全方針）。

### 先に進むために必要な判断（ユーザー確認事項）
1. **AD ユーザー**: S3 AP Windows identity 用に ONTAP が解決可能な FPOLICY.LOCAL ユーザー（`DOMAIN\user`）の提供
2. **AD DC 起動可否**: `itani-vpc03-ad1`（共有）を起動してよいか。または別の稼働 DC があるか
3. **AD/SVM 方針**: 共有 `FPolicySMB`/FPOLICY.LOCAL を使うか、専用の AWS Managed Microsoft AD + 新規 SVM を新設するか（後者はコスト発生）
4. **VPC 作業ホスト**: SMB 共有/NTFS ACL 作成（ONTAP REST）と RDP ドラッグ&ドロップを行う、FSx for ONTAP VPC（または到達可能な）Windows/Linux ホスト
5. **到達性**: DC/クライアントの VPC（172.29.x / 172.30.x）と FSx for ONTAP VPC（10.0.x）間のピアリング有無
6. **人手前提の承認**: 最終のドラッグ&ドロップは RDP による人手操作になる点の合意

## アーキテクチャ（リテラル）

```
業務ユーザー(Windows, AD参加) ──ドラッグ&ドロップ──▶ SMB 共有
                                                      │ (FSx for ONTAP AD参加SVM, NTFS volume /ai-knowledge)
                                                      ▼ 読み取りパス
                                              S3 Access Point (Windows FileSystemIdentity)
                                                      ▼
                                              Bedrock KB データソース → 同期 → 回答
```

## 手順

### 0. 前提決定（要合意）
- AD: 既存 `FPOLICY.LOCAL` を再利用 or 新規 Managed AD
- Windows クライアント: 既存を AD 参加・同VPC化 or 新規 Windows EC2 を FSx for ONTAP VPC に起動
- VPC 内作業ホスト: ONTAP REST/ SMB 用に Linux/Windows を FSx for ONTAP VPC に用意

### 1. NTFS ボリューム作成（FSx API・自動化可）
```bash
aws fsx create-volume --region ap-northeast-1 \
  --volume-type ONTAP --name ai_knowledge_smb \
  --ontap-configuration '{
    "StorageVirtualMachineId": "svm-037cedb30df493c1e",
    "JunctionPath": "/ai_knowledge_smb",
    "SecurityStyle": "NTFS",
    "SizeInBytes": "10737418240",
    "StorageEfficiencyEnabled": true,
    "TieringPolicy": {"Name": "AUTO"}
  }'
```

### 2. SMB 共有 + ロールフォルダ + NTFS ACL（ONTAP・VPC 内ホストから）
ONTAP REST（管理 LIF 10.0.15.0、`fsx-ontap-fsxadmin-credentials`）または Windows から:
```
# ONTAP CLI 例（CIFS 共有作成）
vserver cifs share create -vserver FPolicySMB -share-name ai-knowledge -path /ai_knowledge_smb
# Windows 側でロールフォルダ作成 + NTFS ACL（各部門グループに変更権限）
#   \\FPOLSMB.FPOLICY.LOCAL\ai-knowledge\{sales,marketing,finance,information-technology,operations,legal,developers}
```

### 3. Windows identity の S3 Access Point 作成（FSx API・自動化可）
```bash
aws fsx create-and-attach-s3-access-point --region ap-northeast-1 \
  --name fsxn-ai-knowledge-smb-s3ap --type ONTAP \
  --ontap-configuration '{
    "VolumeId": "<ai_knowledge_smb の VolumeId>",
    "FileSystemIdentity": {"Type": "WINDOWS", "WindowsUser": {"Name": "FPOLICY\\<解決可能なADユーザー>"}}
  }'
```
> コマンド名は `create-and-attach-s3-access-point`（`create-s3-access-point-attachment` ではない）。
> `WindowsUser` は `Name` のみ（`DOMAIN\\user` 形式）。
> Windows identity にすることで、S3 AP 経由アクセスが NTFS ACL に基づき認可される。
> Amazon Quick の S3 ナレッジベースも Windows identity の S3 AP で正常動作する（[AWS Storage Blog 参照](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/)）。

### 4. Bedrock KB データソース接続 + AutoSync 再ポイント
- 新 S3 AP エイリアスに対し inclusionPrefixes を設定したデータソースを KB に追加
- UC29 スタックの `S3AccessPointAlias/Name`・`DataSourceId` を新 AP/DS に更新して再デプロイ

### 5. Windows でドラッグ&ドロップ（人手・RDP）
1. AD 参加 Windows クライアントに RDP
2. `\\FPOLSMB.FPOLICY.LOCAL\ai-knowledge` をドライブマップ
3. `sample-data/ai-knowledge/<role>/` の各ファイルを対応フォルダへドラッグ&ドロップ
4. AutoSync 実行（または Scheduler 待ち）→ Query で反映確認

### 6. クリーンアップ
- S3 AP attachment 削除 → ボリューム削除 → （新規作成した場合）Windows EC2/Managed AD 削除
- KB データソース削除

## 自動化できる範囲 / できない範囲（本ツール）

| 範囲 | 可否 |
|------|------|
| NTFS ボリューム作成、Windows identity S3 AP 作成、KB データソース、AutoSync 再デプロイ | ✅ FSx/Bedrock API で可能 |
| SMB 共有作成・NTFS ACL 設定 | ⚠️ ONTAP 管理（VPC 内ホスト）必要 |
| Windows エクスプローラーのドラッグ&ドロップ | ❌ RDP/GUI のため人手 |

## コスト・リスク注記
- 新規 Windows EC2 / Managed AD は稼働課金。検証後はクリーンアップ
- 共有 SVM/AD（FPOLICY.LOCAL）への変更は追加的だが、利用は事前合意の上で
