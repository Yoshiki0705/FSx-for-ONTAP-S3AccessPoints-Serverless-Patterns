# KNFSD File Cache — トラブルシューティング

🌐 **Language / 言語**: [日本語](troubleshooting.md) | [English](troubleshooting.en.md)

> 2026-07-22 の実環境検証で発見した問題と対策を網羅。
> 全て ap-northeast-1 + FSx for ONTAP + arm64 で検証済み。

---

## デプロイ時の問題

### proxy-startup.sh が `Connect timeout on endpoint URL` で失敗

```
aws: [ERROR]: Connect timeout on endpoint URL: "https://ec2.ap-northeast-1.amazonaws.com/"
ERROR: Failed to start proxy
```

| 原因 | KNFSD インスタンスが EC2 API に到達できない |
|------|------|
| 対策 | 以下のいずれかを実施: |

1. **Public IP を割り当て** (推奨 — Terraform で `assign_public_ip = true`)
2. EC2 VPC Interface Endpoint (`com.amazonaws.{region}.ec2`) を追加
3. NAT Gateway 経由でインターネットアクセスを確保

> `proxy-startup.sh` は初期化時に `aws ec2 create-tags` でステータスタグを更新する。
> この呼び出しが失敗するとスクリプト全体が中断する。

---

### `Detected 0 devices: ERROR: No storage devices found`

```
---- RUNNING: create fs-cache
Detecting EBS volumes for FS-Cache...
Detected 0 devices:
ERROR: No storage devices found
```

| 原因 | SSM パラメータ `CACHEFILESD_DISK_TYPE` が未設定 or 値が間違っている |
|------|------|
| 対策 | `CACHEFILESD_DISK_TYPE = "local-nvme"` を設定（**ハイフン**。`local_nvme` は不可） |

有効な値:
- `local-nvme` — m6gd, im4gn, i3en, i7ie, i8g 等のインスタンスストア NVMe
- `ebs` — 追加 EBS ボリュームをアタッチした場合

---

### `mount.nfs: an incorrect mount option was specified`

```
(Attempt 1/3) Mounting NFS share: 10.0.3.133:/vol1...
mount.nfs: an incorrect mount option was specified for /srv/nfs/vol1
```

| 原因 | SSM パラメータの NFS mount 関連値が空文字列 |
|------|------|
| 対策 | `NCONNECT`, `ACDIRMIN`, `ACDIRMAX`, `ACREGMIN`, `ACREGMAX`, `RSIZE`, `WSIZE` に数値を設定 |

空文字列は mount オプション `nconnect=,acdirmin=,...` となり不正。Terraform の `main.tf` でデフォルト値を設定済み。手動設定の場合:

```bash
aws ssm put-parameter --name "/knfsd/fsxn-knfsd/NCONNECT" --value "1" --type String --overwrite
aws ssm put-parameter --name "/knfsd/fsxn-knfsd/ACREGMAX" --value "60" --type String --overwrite
# ... (全パラメータに値を設定)
```

---

### Packer ビルドで SSH タイムアウト

| 原因 | サブネットに `MapPublicIpOnLaunch=false` で Packer が SSH できない |
|------|------|
| 対策 | `-var 'ASSOCIATE_PUBLIC_IP_ADDRESS=true'` を追加 |

```bash
packer build \
  -var 'REGION=ap-northeast-1' \
  -var 'SUBNET=subnet-xxx' \
  -var 'ARCH=["arm64"]' \
  -var 'ASSOCIATE_PUBLIC_IP_ADDRESS=true' \
  .
```

---

## NFS マウントの問題

### `mount.nfs: mounting failed, reason given by server: No such file or directory`

```
mount.nfs: trying 10.0.8.66 prog 100005 vers 3 prot UDP port 20048
mount.nfs: mount(2): No such file or directory
```

| 原因 | `fsidd` が未起動。NFS re-export では FSID デーモンが必要 |
|------|------|
| 対策 | `fsid_mode = "local"` (推奨) を設定し、`proxy-startup.sh` を正常に完了させる。`fsid_mode = "static"` は**使用しないこと** — Stale file handle の根本原因になる |

`fsid_mode` の選択肢と設定方法は [FSID Backend 選択ガイド](fsid-backend-options.md) を参照。

---

### `mount.nfs: access denied by server`

| 原因候補 | 確認方法 | 対策 |
|---------|---------|------|
| Security Group に UDP ポートなし | SG ルール確認 | UDP 111, 2049, 20048 を追加 |
| export CIDR が不一致 | `exportfs -v` で確認 | SSM パラメータ `EXPORT_CIDR` を修正 |
| `secure` オプション + 非特権ポート | `exportfs -v` で `insecure` 確認 | export に `insecure` を追加 |

**NFSv3 に必要な全ポート (TCP + UDP)**:

| ポート | プロトコル | 用途 |
|:---:|:---:|------|
| 111 | TCP + UDP | portmapper (rpcbind) |
| 2049 | TCP + UDP | NFS |
| 20048 | TCP + UDP | mountd |

---

### `Stale file handle` エラー

```
cat: /mnt/knfsd/file.txt: Stale file handle
mkdir: cannot create directory: Stale file handle
```

| 原因 | KNFSD proxy の NFS サーバーが再起動され、FSID が変更された |
|------|------|
| 対策 | クライアント側で `umount -l` → `mount` し直す |

**重要**: KNFSD proxy を再起動・再構成した場合、全クライアントの remount が必要。
本番環境ではプロキシの再起動を rolling update で行い、クライアントへの影響を最小化する。

```bash
# クライアント側の対処
sudo umount -l /mnt/knfsd    # lazy unmount (即座に完了)
sudo mount -t nfs -o vers=3 <KNFSD_IP>:/vol1 /mnt/knfsd
```

---

## キャッシュの問題

### Cache hit で速度向上が見られない

| 確認項目 | コマンド | 期待値 |
|---------|---------|--------|
| インスタンスタイプに NVMe があるか | `lsblk \| grep nvme` | NVMe ディスクが見える |
| NVMe が /var/cache/fscache にマウント | `mount \| grep fscache` | マウントあり |
| ソースに `fsc` オプション | `mount \| grep fsc` | `fsc` が含まれる |
| Page Cache をドロップしたか | — | テスト前に `echo 3 > /proc/sys/vm/drop_caches` |

> **注意**: `t3`, `m6i`, `c7g` 等 NVMe なしインスタンスでは L2 キャッシュ (FS-Cache) が機能しません。
> ただし **L1 (Page Cache = RAM) だけでも 32x の speedup** は確認されています (16 GB RAM で 10 MB ファイル)。

---

### FS-Cache 統計が全て 0

```
Cookies: n=0 v=0 vcol=0 voom=0
IO: rd=0 wr=0 mis=0
```

| 原因 | ソース NFS マウントに `fsc` オプションが付いていない |
|------|------|
| 確認 | `mount \| grep "/srv/nfs"` → `fsc` が含まれるか |
| 対策 | `proxy-startup.sh` が自動的に `fsc` を含む mount options を構成する。手動マウントの場合: `mount -o vers=3,fsc ...` |

---

## Dual-Path (KNFSD + S3 AP) の問題

### S3 AP で書いたファイルが KNFSD から見えない

| 原因 | NFS 属性キャッシュ (acregmax) の遅延 |
|------|------|
| 遅延 | デフォルト最大 60 秒 |
| 対策 | `acregmax` を短くする (Terraform: `acregmax = 10`) |

```hcl
# terraform.tfvars
acregmax = 10   # S3 AP writes を 10 秒以内に NFS から見えるようにする
```

> **設計指針**: KNFSD は「入力データを繰り返し読取る」ワークロードに最適化。
> 頻繁に更新されるファイルには向かない。
> 典型的なパターン: 入力データは KNFSD、結果書込みは FSx for ONTAP 直接 → S3 AP で後処理。

---

### KNFSD で書いたファイルが S3 AP から見えない

| 原因 | Write-through の同期タイミング |
|------|------|
| 対策 | NFS 書込み後に `sync` コマンドを実行し、2-3 秒待機してから S3 AP で GetObject |

---

## パフォーマンスの問題

### 期待したスループットが出ない

| ボトルネック | 確認方法 | 対策 |
|------------|---------|------|
| FSx throughput 上限 | CloudWatch `DataReadBytes` | throughput capacity 増加 or KNFSD ヒット率改善 |
| KNFSD インスタンスの NW 帯域 | `sar -n DEV 1 5` (SSM) | 上位インスタンスにスケールアップ |
| NFS スレッド不足 | `cat /proc/fs/nfsd/threads` | `nfs_threads` を 64-128 に増加 |
| クライアント数 > NFS スレッド | 上記 | スレッド増加 or プロキシ台数追加 |
| NVMe IOPS 上限 | `iostat -x 1 5` (SSM) | i8g (最新 NVMe) を検討 |

---

## 既知の制限事項 (Preview)

| 項目 | 内容 |
|------|------|
| SLA | Preview のため SLA なし |
| 機能変更 | GA までに API/構成が変更される可能性 |
| サポート | GitHub Issues (knfsd-file-cache@amazon.com) |
| NFS バージョン | v3 推奨 (re-export の安定性)。v4.x も動作するが検証が少ない |
| 公式モジュール | 内部パス参照問題あり (`module.fsid_database` のローカルパス)。Terraform remote source としての利用は制限あり (2026-07 時点) |
| NVMe 暗号化 | インスタンスストア NVMe は hardware-level encryption のみ。ソフトウェアレベル (dm-crypt) は AMI カスタマイズが必要。インスタンス終了時にハードウェアワイプされる |
| キャッシュ残留 | ジョブ終了後もキャッシュにデータが残る。規制データの場合はインスタンス terminate で NVMe を消去 |

---

## NFS バージョン選択ガイド

| 観点 | NFSv3 | NFSv4.1 |
|------|-------|---------|
| re-export 安定性 | ✅ 実績豊富 | △ エッジケースあり |
| ファイルロック | statd/lockd (別デーモン) | プロトコル内蔵 |
| ポート要件 | 111 + 2049 + 20048 (TCP+UDP) | 2049 のみ (TCP) |
| パフォーマンス | 十分 | セッションオーバーヘッドあり |
| 暗号化 | なし | krb5p (Kerberos) 利用可能 |

**推奨**: KNFSD re-export 用途では **NFSv3** を選択。暗号化が必要な環境では VPC 内のみで運用し、規制要件に応じて NFSv4.1 + krb5p を検討。

---

## NFS スレッドチューニング

| クライアント数 | 推奨スレッド数 | Terraform 設定 |
|:---:|:---:|------|
| 1-10 | 16 | `nfs_threads = 16` (デフォルト) |
| 10-50 | 64 | `nfs_threads = 64` |
| 50-200 | 128 | `nfs_threads = 128` |
| 200+ | 256 | `nfs_threads = 256` + プロキシ台数追加 |
