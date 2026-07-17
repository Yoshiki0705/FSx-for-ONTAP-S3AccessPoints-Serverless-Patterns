# ハンズオン手順書 (個人検証用)

Amazon FSx for NetApp ONTAP の S3 Access Points + Amazon Q Business、および Tamperproof Snapshot / FlexClone によるランサムウェア対策を体験するハンズオンガイドです。

---

## 環境情報

| 項目 | 値 |
|------|-----|
| リージョン | ap-northeast-1 (東京) |
| ドメイン | handson.local |
| SVM 名 | svm01 |
| ボリューム名 | user01 |
| ユーザー名 | user01 |
| ONTAP 管理 IP | (スタック出力 `OntapManagementIp` 参照) |
| S3 AP エイリアス | (スタック出力 `S3AccessPointAlias` 参照) |

### スタック出力の確認

```bash
aws cloudformation describe-stacks \
  --stack-name fsx-ontap-handson \
  --region ap-northeast-1 \
  --query "Stacks[0].Outputs" \
  --output table
```

---

## 事前確認

### 1. Windows EC2 への接続

**Fleet Manager (推奨)**:
1. AWS Console → Systems Manager → Fleet Manager
2. 対象インスタンスを選択 → Node actions → Connect → Remote Desktop
3. 認証情報: `HANDSON\user01` / (Secrets Manager に格納したパスワード)

**Session Manager (PowerShell)**:
```bash
aws ssm start-session \
  --target <InstanceId> \
  --region ap-northeast-1
```

**RDP ポートフォワーディング**:
```bash
aws ssm start-session \
  --target <InstanceId> \
  --document-name AWS-StartPortForwardingSession \
  --parameters "portNumber=3389,localPortNumber=13389" \
  --region ap-northeast-1
# ローカルの RDP クライアントで localhost:13389 に接続
```

### 2. ドライブマッピング

EC2 のデスクトップにある `map_drives.ps1` を右クリック → PowerShell で実行:

```powershell
# 自動実行 or 手動:
net use X: \\svm01.handson.local\user01 /persistent:yes
net use Y: \\svm01.handson.local\user01\.snapshot /persistent:yes
```

- **X: ドライブ**: 作業データ (SMB 共有)
- **Y: ドライブ**: Snapshot アクセス (読み取り専用)

---

## 前半: Amazon Q Business + S3 Access Points

> 所要時間: 約20-30分

### ステップ 1: S3 Access Point 経由のファイルアクセス確認 (約10分)

EC2 の PowerShell で以下を実行:

```powershell
# S3 AP エイリアスを変数に設定 (スタック出力から取得)
$S3AP = "<S3AccessPointAlias>"

# ファイル一覧取得
aws s3 ls s3://$S3AP/ --region ap-northeast-1

# ファイルダウンロード
aws s3 cp s3://$S3AP/FSxONTAPGuide.txt C:\Users\user01\Desktop\ --region ap-northeast-1

# ファイルアップロード
"Test file from hands-on lab $(Get-Date)" | Set-Content C:\temp\test_upload.txt
aws s3 cp C:\temp\test_upload.txt s3://$S3AP/test_upload.txt --region ap-northeast-1

# アップロード確認
aws s3 ls s3://$S3AP/ --region ap-northeast-1
```

**確認ポイント**:
- SMB (X: ドライブ) に配置したファイルが S3 AP 経由で見える
- S3 AP 経由でアップロードしたファイルが X: ドライブに出現する
- NFS/SMB と S3 API のデータ一貫性

> **データ一貫性に関する補足**: FSx for ONTAP の S3 Access Points は NAS プロトコル (NFS/SMB) と同一のボリュームデータを参照します。書き込み直後に S3 AP で読み取り可能ですが、大容量ファイルの書き込み中にはメタデータの反映に数秒のタイムラグが生じる場合があります。

> **IAM 権限に関する補足**: S3 AP のデータ操作には AWS IAM 権限 (`s3:GetObject`, `s3:PutObject`, `s3:ListBucket` on AP ARN) と、ONTAP 側のファイルシステム ID マッピング (WindowsUser / UnixUser) の両方が必要です。どちらか一方でも不足すると AccessDenied になります。

### ステップ 2: Amazon Q Business での検索 (約10分)

1. AWS Console → Amazon Q Business を開く
2. 事前設定済みの Knowledge Base で検索を試行
3. X: ドライブに追加したファイルの内容が検索可能であることを確認

> Amazon Q の設定は `scripts/setup_quick.py` で事前投入。
> 初回同期後、数分でインデックスに反映されます。

### ステップ 3: リアルタイム反映確認 (約5分)

```powershell
# X: ドライブに新規ファイル作成
"New document for Q Business test - $(Get-Date)" | Set-Content X:\q_test_doc.txt

# S3 AP で即時確認
aws s3 ls s3://$S3AP/q_test_doc.txt --region ap-northeast-1
```

---

## 後半: ランサムウェア対策と復旧

> 所要時間: 約30-40分

### ステップ 1: 正常状態の確認 (約3分)

```powershell
# X: ドライブのファイル確認
Get-ChildItem X:\ | Format-Table Name, Length, LastWriteTime

# Y: ドライブ (Snapshot) の確認
Get-ChildItem Y:\ | Format-Table Name
```

### ステップ 2: ONTAP CLI で Snapshot 確認 (約5分)

デスクトップの `command_user01.txt` を参考に、Tera Term または PowerShell SSH で ONTAP に接続:

```bash
ssh fsxadmin@<OntapManagementIp>
# パスワード: Secrets Manager の fsxadmin パスワード

# ページ送り無効化
rows 0

# 現在の Snapshot 一覧
snapshot show -vserver svm01 -volume user01

# Tamperproof Snapshot の状態確認
snapshot show -vserver svm01 -volume user01 -fields snaplock-expiry-time
```

**確認ポイント**: `snaplock-expiry-time` に未来の日時が設定されている Snapshot は削除不可。

> **Tamperproof Snapshot 保持期間に関する補足**: ハンズオンでは短期間 (1時間〜24時間) のロック期間を設定していますが、本番環境ではコンプライアンス要件に基づいて設定します（例: 金融 7年、医療 10年、一般企業 1-3年）。ロック期間は延長のみ可能で、短縮はできません。

> **FlexClone の容量に関する補足**: FlexClone は作成時点ではほぼゼロの追加容量で作成されます（親ボリュームと同じデータブロックを共有）。クローンに書き込みが発生した分だけ追加容量を消費します。ハンズオンのデモでは実質的なストレージ消費は無視できるレベルです。

### ステップ 3: ランサムウェアシミュレーション (約5分)

> **安全性に関する補足**: このスクリプトは教育目的の模擬ツールです。実際の暗号化は行わず、ファイルを `.lckd` 拡張子にリネームするだけです。ファイル内容は変更されません。自己複製や外部通信も行いません。Snapshot からの復旧を体験するためのデモンストレーションです。

デスクトップの `ransomware_simulator.ps1` を実行:

```powershell
# PowerShell を管理者として起動
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# シミュレーター実行 (X: ドライブを対象)
.\ransomware_simulator.ps1 -TargetFolder "X:\"
# "yes" を入力して実行
```

**結果確認**:
```powershell
# ファイルが .lckd にリネームされている (内容は未変更)
Get-ChildItem X:\ | Format-Table Name

# ランサムノート確認
Get-Content X:\RANSOM_NOTE.txt
```

### ステップ 4: 攻撃者による Snapshot 削除試行 (約3分)

ONTAP CLI で攻撃者の行動をシミュレート:

```bash
# 全 Snapshot 削除を試行
set -confirmations off
snapshot delete -vserver svm01 -volume user01 -snapshot *
```

**結果**: Tamperproof Snapshot は削除に失敗する (ロック期間内のため)。

```bash
# 削除結果確認 — Tamperproof Snapshot は残存
snapshot show -vserver svm01 -volume user01 -fields snaplock-expiry-time
```

### ステップ 5: Snapshot Policy 停止 (攻撃者の追加行動) (約2分)

```bash
# 攻撃者が新規 Snapshot 作成を阻止しようとする
volume modify -vserver svm01 -volume user01 -snapshot-policy none
```

### ステップ 6: FlexClone による復旧 (約10分)

> **インシデント対応判断に関する補足**: 本番環境では FlexClone による復旧を実施する前に、以下を確認します: (1) 攻撃の封じ込めが完了しているか、(2) どの Snapshot が「感染前」の状態か、(3) 復旧の承認者は誰か。この判断プロセスはハンズオンでは省略していますが、実運用では不可欠です。

保護された Tamperproof Snapshot から FlexClone を作成:

> **FlexClone セキュリティスタイルに関する補足**: FlexClone のセキュリティスタイル (NTFS/UNIX/MIXED) は親ボリュームから継承され、クローン作成時に指定することはできません。本ハンズオンでは親ボリュームが NTFS のため、クローンも NTFS になります。

```bash
# 保護されている Snapshot 名を確認
snapshot show -vserver svm01 -volume user01 -fields snaplock-expiry-time
# → tamperproof_demo_1 (expiry: 未来日時) を使用

# FlexClone 作成
volume clone create \
  -vserver svm01 \
  -flexclone user01clone \
  -parent-vserver svm01 \
  -parent-volume user01 \
  -parent-snapshot tamperproof_demo_1 \
  -junction-path /user01clone

# SMB 共有作成
cifs share create -share-name user01clone -path /user01clone -vserver svm01
```

### ステップ 7: 復旧データの確認 (約5分)

Windows EC2 で復旧データにアクセス:

```powershell
# クローンボリュームをマッピング
net use Z: \\svm01.handson.local\user01clone /persistent:no

# 復旧されたファイルを確認
Get-ChildItem Z:\ | Format-Table Name, Length, LastWriteTime

# 元のファイルが暗号化前の状態で存在することを確認
Get-Content Z:\sample_doc1.txt
```

### ステップ 8: 事後処理 (復旧完了後) (約5分)

```bash
# Snapshot Policy 復元
volume modify -vserver svm01 -volume user01 -snapshot-policy default

# (オプション) クローン削除
volume delete -vserver svm01 -volume user01clone -f
```

---

## ONTAP CLI コマンドリファレンス

| カテゴリ | コマンド | 説明 |
|----------|---------|------|
| 接続 | `ssh fsxadmin@<IP>` | ONTAP CLI 接続 |
| 表示 | `rows 0` | ページ送り無効化 |
| Volume | `volume show -vserver svm01` | ボリューム一覧 |
| Snapshot | `snapshot show -vserver svm01 -volume user01` | Snapshot 一覧 |
| Tamperproof | `snapshot show ... -fields snaplock-expiry-time` | ロック期限確認 |
| 削除 | `snapshot delete -vserver svm01 -volume user01 -snapshot *` | 全 Snapshot 削除試行 |
| Policy | `volume modify ... -snapshot-policy none/default` | Snapshot Policy 変更 |
| FlexClone | `volume clone create ...` | クローン作成 |
| SMB | `cifs share create/show` | SMB 共有管理 |
| S3 AP | `vserver object-store-server show` | S3 AP 状態確認 |

---

## 学習ポイント

1. **S3 Access Points**: NFS/SMB ファイルを S3 API 経由でアクセスし、AI/ML サービスと連携
2. **Tamperproof Snapshot**: 管理者でも削除不可の保護された Snapshot による確実なデータ保護
3. **FlexClone**: 保護された Snapshot から瞬時にボリュームを複製し、業務継続
4. **統合ストレージ**: NFS + SMB + S3 API のマルチプロトコルアクセスを単一ボリュームで実現

---

## 後片付け

```bash
# ONTAP CLI でクローン削除 (作成した場合)
volume delete -vserver svm01 -volume user01clone -f

# CloudFormation スタック削除
./scripts/cleanup.sh --stack-name fsx-ontap-handson
```
