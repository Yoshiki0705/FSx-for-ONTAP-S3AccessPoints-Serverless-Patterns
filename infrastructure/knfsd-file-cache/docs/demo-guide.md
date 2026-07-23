# KNFSD File Cache デモガイド — FSx for ONTAP NFS Read Acceleration

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md)

> **検証済み**: 2026-07-22, ap-northeast-1, arm64 (Graviton), FSx for ONTAP 9.17.1
> **実測結果**: Cache miss 55ms → Cache hit 2ms (**32x speedup**)

---

## 前提条件

### 必須ツール

| ツール | バージョン | インストール | 確認コマンド |
|--------|-----------|-------------|-------------|
| AWS CLI | >= 2.x | `brew install awscli` | `aws --version` |
| Terraform | >= 1.5 | `brew install hashicorp/tap/terraform` | `terraform version` |
| Packer | >= 1.9 | `brew install hashicorp/tap/packer` | `packer version` |
| jq | any | `brew install jq` | `jq --version` |
| Git | any | (pre-installed) | `git --version` |

### 必須 AWS リソース (事前に存在していること)

| リソース | 確認コマンド | 例 |
|---------|------------|-----|
| FSx for ONTAP (AVAILABLE) | `aws fsx describe-file-systems --query 'FileSystems[?FileSystemType==\`ONTAP\`].{Id:FileSystemId,State:Lifecycle}'` | `fs-0123...` |
| SVM (NFS LIF IP) | `aws fsx describe-storage-virtual-machines --query 'StorageVirtualMachines[].{Name:Name,NFS:Endpoints.Nfs.IpAddresses[0]}'` | `10.0.1.50` |
| Volume (junction path) | `aws fsx describe-volumes --query 'Volumes[].{Name:Name,Path:OntapConfiguration.JunctionPath}'` | `/vol1` |
| VPC + Subnet | `aws ec2 describe-subnets --query 'Subnets[].{Id:SubnetId,AZ:AvailabilityZone}'` | `subnet-0abc...` |
| IAM 権限 | EC2, IAM, SSM, SecretsManager の操作権限 | — |

### ネットワーク要件

```
┌─────────────────────────────────────────────────────┐
│ VPC                                                 │
│                                                     │
│  ┌── Subnet (FSx for ONTAP と同じ AZ を推奨) ───┐  │
│  │                                               │  │
│  │  FSx for ONTAP ◄──NFS──► KNFSD Proxy         │  │
│  │  (10.0.1.50)              (Public IP 必要)    │  │
│  │                              ▲                │  │
│  │                              │ NFS            │  │
│  │                              ▼                │  │
│  │                           Compute Clients     │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  Internet Gateway ← KNFSD が EC2 API にアクセスする │
└─────────────────────────────────────────────────────┘
```

> **重要**: KNFSD proxy には Public IP (または NAT/EC2 VPC Endpoint) が必要です。
> `proxy-startup.sh` が EC2 API (`ec2.{region}.amazonaws.com`) にアクセスしてステータスタグを更新します。
>
> **セキュリティ note**: Public IP があっても NFS ポートはインターネットに公開されません。
> Security Group が VPC CIDR からのみ NFS アクセスを許可するため、外部からの NFS 接続は不可能です。

### FSx for ONTAP export-policy 確認

KNFSD proxy が FSx for ONTAP に NFS mount するには、ボリュームの export-policy で KNFSD のサブネットからのアクセスが許可されている必要があります。

```bash
# ONTAP REST API で確認 (fsxadmin 経由)
# デフォルト export-policy は 0.0.0.0/0 (全 IP) を許可 → 通常は追加設定不要
# 制限されている場合は KNFSD proxy のサブネット CIDR を許可ルールに追加
```

> デフォルト構成（新規作成した volume）では追加設定不要です。export-policy をカスタマイズしている場合のみ確認してください。

---

## デプロイ手順 (所要時間: ~40 分)

### Step 1: KNFSD リポジトリ取得 (2 分)

```bash
git clone https://github.com/awslabs/knfsd-file-cache.git /tmp/knfsd-file-cache
cd /tmp/knfsd-file-cache
```

### Step 2: AMI ビルド (~25 分)

```bash
cd /tmp/knfsd-file-cache/image
packer init .
packer build \
  -var 'REGION=ap-northeast-1' \
  -var 'SUBNET=subnet-0123456789abcdef0' \
  -var 'ARCH=["arm64"]' \
  -var 'ASSOCIATE_PUBLIC_IP_ADDRESS=true' \
  .
```

**出力される AMI ID をメモ**: `ami-0xxxxxxxxxxxxxxxxx`

> **注意点 (検証で確認済み)**:
> - `ASSOCIATE_PUBLIC_IP_ADDRESS=true` は `MapPublicIpOnLaunch=false` のサブネットで必要
> - ビルドは Spot インスタンスを使用 (コスト: ~$0.30)
> - arm64 (Graviton) 推奨 (コスト効率が高い)
> - 1 回ビルドすれば AMI を何度でも再利用可能

### Step 3: Terraform 設定 (3 分)

```bash
cd /path/to/fsxn-s3ap-serverless-patterns/infrastructure/knfsd-file-cache/terraform

# 設定ファイル作成
cp terraform.tfvars.example terraform.tfvars
```

**`terraform.tfvars` を編集** — 最低限以下を変更:

```hcl
# 実環境の値に変更
vpc_id       = "vpc-0abc..."       # aws ec2 describe-vpcs
subnet_ids   = ["subnet-0def..."]  # FSx for ONTAP と同じサブネット
knfsd_ami_id = "ami-0xxx..."       # Step 2 で取得した AMI ID

source_mounts = [
  {
    host   = "10.0.1.50"   # SVM NFS LIF IP
    export = "/vol1"        # Volume junction path
    mount  = "/vol1"
  }
]
```

### Step 4: デプロイ (~3 分)

```bash
terraform init
terraform plan     # 作成されるリソースを確認
terraform apply    # "yes" で実行
```

**出力例**:
```
knfsd_private_ips = ["10.0.8.66"]
nfs_mount_commands = ["sudo mount -t nfs -o vers=4.1 10.0.8.66:/vol1 /mnt/knfsd/vol1"]
```

### Step 5: 起動確認 (~2 分)

```bash
# インスタンス状態
aws ec2 describe-instances \
  --instance-ids $(terraform output -json knfsd_instance_ids | jq -r '.[0]') \
  --query 'Reservations[0].Instances[0].State.Name'

# SSM 接続確認
aws ssm describe-instance-information \
  --filters "Key=InstanceIds,Values=$(terraform output -json knfsd_instance_ids | jq -r '.[0]')" \
  --query 'InstanceInformationList[0].PingStatus'

# NFS export 確認 (SSM 経由)
aws ssm send-command \
  --instance-ids $(terraform output -json knfsd_instance_ids | jq -r '.[0]') \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["exportfs -v","mount | grep nfs"]'
```

### Step 6: クライアントからマウント

```bash
# テスト用 EC2 インスタンスから (同一 VPC 内)
sudo mkdir -p /mnt/knfsd
sudo mount -t nfs -o vers=4.1 <KNFSD_IP>:/vol1 /mnt/knfsd

# ファイル確認
ls /mnt/knfsd/
```

### Step 7: キャッシュ動作テスト

```bash
# テストファイル作成 (10 MB)
dd if=/dev/urandom of=/mnt/knfsd/cache_test.dat bs=1M count=10
sync

# Cache MISS (1回目: FSx for ONTAP から取得)
sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
time cat /mnt/knfsd/cache_test.dat > /dev/null
# → 実測: ~55-64ms

# Cache HIT (2回目: KNFSD キャッシュから)
time cat /mnt/knfsd/cache_test.dat > /dev/null
# → 実測: ~2ms (28-32x 高速化)

# クリーンアップ
rm /mnt/knfsd/cache_test.dat
sudo umount /mnt/knfsd
```

---

## クリーンアップ

```bash
cd infrastructure/knfsd-file-cache/terraform
terraform destroy   # "yes" で実行

# AMI も不要なら
aws ec2 deregister-image --image-id ami-0xxx... --region ap-northeast-1
```

---

## コスト目安

| フェーズ | リソース | コスト |
|---------|---------|--------|
| AMI ビルド | Spot c6g.16xlarge × 25分 | ~$0.30 |
| テスト (1時間) | m6gd.xlarge | ~$0.29 |
| テスト (1時間) | Elastic IP (付与中) | ~$0.005 |
| **合計** | | **< $1 (KNFSD 増分のみ)** |

> **前提条件のコスト**: 上記は既存の FSx for ONTAP 環境 (~$194/月) + VPC が稼働中であることを前提としています。ゼロから検証環境を構築する場合、FSx for ONTAP の最小構成 (128 MBps / 1 TB SSD) で ~$194/月が別途必要です。
| 本番 (月額) | im4gn.16xlarge × 24h × 30d | ~$4,190 |

---

## 既存ツールとの比較: いつ KNFSD を選ぶか

以下のようなワークロードを持つ方に特に適しています:

| 現在の状況 | KNFSD が解決すること |
|-----------|-------------------|
| FSx for ONTAP の throughput 上限に近い | キャッシュにより実効帯域を数倍に拡大 |
| 同一ファイルを多数のコンピュートノードが繰り返し読取る | 2回目以降は NVMe から配信（FSx 帯域消費なし） |
| Spot インスタンスで HPC バーストを実行したい | Spot 回収されてもキャッシュは warm 維持 |
| オンプレミス NFS + FSx for ONTAP の両方を使っている | 複数ソースを 1 つのキャッシュ層で統合可能 |
| FlexCache を使いたいが書込みが不要 | FlexCache なしで読取り最適化のみ実現 |

FlexCache / Amazon File Cache / EFS との選択ガイドは [比較ドキュメント](../../../docs/comparison-alternatives.md) を参照。

---

## よくある質問

**Q: KNFSD を使うと FSx for ONTAP のデータが二重になる？**
A: いいえ。KNFSD は NFS プロトコルレベルの透過的キャッシュです。データの正本は FSx for ONTAP に 1 つだけ存在し、KNFSD は読取りの高速化のみを行います。

**Q: KNFSD 経由で書込みもできる？**
A: はい。Write-through（書込みは即座にソースに送られる）で動作します。ただし書込みデータはキャッシュされません。読取り集中ワークロードで効果を発揮します。

**Q: 複数の KNFSD プロキシを並列で使える？**
A: はい。`cluster_size=2+` に設定し、DNS round-robin または NLB で負荷分散できます。本番運用では 2+ 台を推奨。

**Q: KNFSD を停止するとクライアントはどうなる？**
A: NFS マウントがハングします（`hard` mount の場合）。プロキシ復旧後に自動回復します。可用性のために 2 台以上の構成を推奨。

**Q: KNFSD がうまくいかない場合のロールバック方法は？**
A: クライアントの mount 先を KNFSD IP から FSx for ONTAP の NFS LIF IP に戻すだけです。データは FSx for ONTAP に正本があるため、KNFSD を削除してもデータは失われません。`terraform destroy` でリソースを完全に削除できます。

**Q: レンダーファームの全ノードに KNFSD マウントを自動設定するには？**
A: Golden AMI の `/etc/fstab` に追加するか、cloud-init で設定します:

```bash
# /etc/fstab に追加 (Golden AMI)
<KNFSD_IP>:/vol1  /mnt/assets  nfs  vers=4.1,hard,bg  0  0

# または cloud-init (UserData)
#!/bin/bash
mkdir -p /mnt/assets
mount -t nfs -o vers=4.1,hard,bg <KNFSD_IP>:/vol1 /mnt/assets
```

> `bg` オプションにより、KNFSD が未起動でもノードの起動がブロックされません。バックグラウンドで再試行します。

**Q: Compute ノードに Spot インスタンスを使える？**
A: はい。KNFSD proxy は On-Demand で常時稼働し、compute クライアントは Spot で実行するのが推奨パターンです。Spot 回収されても KNFSD のキャッシュは warm のまま維持されるため、新しい Spot ノードが即座にキャッシュ済みデータにアクセスできます。

---

---

## NFS Re-export の制限事項 (Linux Kernel 7.1)

[公式カーネルドキュメント](https://docs.kernel.org/7.1/filesystems/nfs/reexport.html) に基づく:

| 制限 | 影響 | 対策 |
|------|------|------|
| ファイルロック非対応 | advisory lock が "operation not supported" で失敗 | アプリケーションレベルのロック or 同時書込みを回避 |
| NFSv4 delegation 不可 | re-export サーバーから delegation を取得できない | NFSv3 では元々 delegation がないため影響なし |
| ファイルハンドル +22 bytes | カスケード（多段 proxy）は不可 | 単一プロキシ構成で十分 |
| Proxy 再起動で stale handle | 全クライアントの remount が必要 | ローリングアップデートで影響最小化 |
| crossmnt が fsid を伝播しない | サブマウントには明示的 export + 固有 fsid が必要 | proxy-startup.sh が自動対応 |

---

## 関連ドキュメント

- [FSID Backend 選択ガイド](fsid-backend-options.md) — FSID 管理方式の比較と選択
- [KNFSD + S3 AP Dual-Path Architecture](../../../docs/knfsd-s3ap-dual-path-architecture.md)
- [比較: FlexCache / KNFSD / Amazon File Cache](../../../docs/comparison-alternatives.md)
- [トラブルシューティング](troubleshooting.md)
- [KNFSD File Cache 公式リポジトリ](https://github.com/awslabs/knfsd-file-cache)
- [AWS Solutions Guidance](https://docs.aws.amazon.com/solutions/knfsd-file-cache-on-aws/)
