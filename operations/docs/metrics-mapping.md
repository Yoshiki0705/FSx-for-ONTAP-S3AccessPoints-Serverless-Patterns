# メトリクス対応表 — CloudWatch ↔ ONTAP REST API ↔ CLI

> FSx for ONTAP の運用メトリクスを取得する3つの手段の対応関係を整理します。

---

## ファイルシステムレベル (CloudWatch)

| CloudWatch メトリクス | ONTAP CLI 相当 | ONTAP REST API | 粒度 | 備考 |
|---------------------|---------------|----------------|------|------|
| `StorageCapacity` | — | — | FS | SSD 総容量 (bytes) |
| `StorageUsed` | — | — | FS | SSD 使用量 (bytes) |
| `StorageCapacityUtilization` | — | — | FS | SSD 使用率 (%) |
| `CPUUtilization` | `sysstat` | `/api/cluster/metrics` | FS | |
| `NetworkThroughputUtilization` | — | — | FS | Gen2 のみ |
| `DiskIOPSUtilization` | — | — | FS | Gen2 のみ |
| `NetworkSentBytes` | — | — | FS | |
| `NetworkReceivedBytes` | — | — | FS | |
| `DiskReadBytes` / `DiskWriteBytes` | — | — | FS | |
| `DiskReadOperations` / `DiskWriteOperations` | — | — | FS | |

## ボリュームレベル (CloudWatch)

| CloudWatch メトリクス | ONTAP REST API | 粒度 |
|---------------------|----------------|------|
| `StorageCapacity` | `/api/storage/volumes` → `space.size` | Volume |
| `StorageUsed` | `/api/storage/volumes` → `space.used` | Volume |
| `StorageCapacityUtilization` | 計算: `used / size * 100` | Volume |
| `FilesUsed` / `FilesCapacity` | `space.logical_space` | Volume |

## ONTAP REST API 専用 (CloudWatch にない)

| メトリクス | REST API エンドポイント | fields パラメータ | 用途 |
|-----------|----------------------|-----------------|------|
| ボリューム autosize 状態 | `GET /api/storage/volumes` | `autosize` | OPS1 |
| 重複排除/圧縮効率 | `GET /api/storage/volumes` | `space.efficiency_without_snapshots,efficiency` | OPS2 |
| ティアリングポリシー | `GET /api/storage/volumes` | `tiering` | OPS3 |
| コールドデータ率 | `GET /api/storage/volumes` | `statistics.cloud` | OPS3 |
| スナップショット一覧 | `GET /api/storage/volumes/{uuid}/snapshots` | `create_time,size` | OPS4 |
| Snapshot Policy | `GET /api/storage/snapshot-policies` | `*` | OPS4 |
| QoS ポリシー | `GET /api/storage/qos/policies` | `*` | OPS6 |
| QoS ワークロード | `GET /api/storage/qos/workloads` | `*` | OPS6 |
| アグリゲート容量 | `GET /api/storage/aggregates` | `space,block_storage` | OPS1 |

## ONTAP CLI → REST API 変換表

| CLI コマンド | REST API | 備考 |
|------------|---------|------|
| `volume show -fields space` | `GET /api/storage/volumes?fields=space` | |
| `volume show -fields autosize` | `GET /api/storage/volumes?fields=autosize` | |
| `storage aggregate show-efficiency` | `GET /api/storage/aggregates?fields=space` | |
| `volume show -fields performance-tier-inactive-user-data-percent` | `GET /api/storage/volumes?fields=statistics.cloud` | 9.14+ |
| `volume snapshot show` | `GET /api/storage/volumes/{uuid}/snapshots` | |
| `qos policy-group show` | `GET /api/storage/qos/policies` | |
| `qos workload show` | `GET /api/storage/qos/workloads` | |

---

## Gen1 vs Gen2 メトリクスの差異

| メトリクス | Gen1 | Gen2 | 取得方法 (Gen1 代替) |
|-----------|:----:|:----:|-------------------|
| `NetworkThroughputUtilization` | ❌ | ✅ | Gen1: `NetworkSentBytes + NetworkReceivedBytes` を手動計算 |
| `DiskIOPSUtilization` | ❌ | ✅ | Gen1: `DiskReadOps + DiskWriteOps` をスループット上限と比較 |

**判別方法**: `aws fsx describe-file-systems` → `FileSystem.OntapConfiguration.DeploymentType`
- `MULTI_AZ_1` / `SINGLE_AZ_1` = Gen1
- `MULTI_AZ_2` / `SINGLE_AZ_2` = Gen2
