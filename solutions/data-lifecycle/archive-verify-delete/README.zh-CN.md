# archive-verify-delete：仅用 S3 API 复制、核对，并在批准后删除的归档
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **文档**: [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## 概述
本模式把 Amazon FSx for NetApp ONTAP（以下简称 FSx for ONTAP）卷上很少被读取的文件，转移到 S3 Glacier 系列的存储类别。不挂载卷，只使用 S3 Access Points 的 S3 API。
一个文件按下列顺序处理，中途条件不成立的文件会被排除在删除对象之外。
1. 在台账（DynamoDB 表）中记录大小、ETag、SHA-256 和 CRC64NVME
2. 指定存储类别，用 `CopyObject` 复制到归档用存储桶
3. 把存储桶返回的校验和与台账中的值进行比较
4. 由人批准一致文件的清单
5. 确认 Access Point 的 ETag 和大小与台账相同后，删除 Access Point 上的文件

恢复时，先在台账中查找，在存储桶中请求恢复，等待完成后用 `CopyObject` 复制回 Access Point。
本模式不使用 S3 Object Lock、S3 Glacier Vault Lock、AWS Backup Vault Lock、SnapLock 和快照锁定，模板中也没有写入。因为不设置保留期限，所以对归档用存储桶中的对象，只要有权限就可以删除。
本模式的前提，以及与其他方式的比较，见[转移到归档类别的 8 种机制的比较](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)（日文）。
## 已测量和未测量的内容
| 类别 | 内容 |
|---|---|
| 各组成部分已在实际环境中各确认 1 次（记录在上述比较资料中，2026-11-24 和 2026-11-26，ap-northeast-1，第 1 代 `SINGLE_AZ_1`，ONTAP 9.19.1P4D1，UNIX 样式卷，Access Point 用户为 UNIX root） | 给 `CopyObject` 指定 `ChecksumAlgorithm=SHA256` 后，存储桶的 `ChecksumSHA256` 为 `FULL_OBJECT`，与文件的 SHA-256 一致（最大 8 MiB）。5.5 GiB 的分段上传中 SHA-256 变为 `COMPOSITE`，CRC64NVME 为 `FULL_OBJECT` 且一致。使用旧 ETag 的 `--copy-source-if-match` 返回 `PreconditionFailed`。Access Point 的 `DeleteObject` 不支持 `If-Match`。在 Step Functions 的 SDK 集成中，可以把 Access Point 别名传给 `Bucket` |
| 在本仓库中已确认 | 使用 moto 的单元测试，以及状态机和 IAM 结构的测试。未连接 AWS |
| 尚未确认 | 整个模式在实际环境中的端到端运行。大量文件时的耗时和费用。Lambda 对接近 5 GiB 的文件计算哈希的时间。Fargate 分段复制在实际环境中的表现。ONTAP REST API 中根目录的指定方式和 `unix_permissions` 的表示。Distributed Map 的 `ItemReader` 和 `ResultWriter` 在实际环境中的表现。需要恢复的 2 个类别的恢复。NTFS 卷、非 root 用户、第 2 代、Multi-AZ |
删除前的确认仍留有一个写入窗口。Access Point 的 `DeleteObject` 不支持条件删除，因此在用 `HeadObject` 确认之后到删除之前这段时间内发生的写入无法被检测到。这个窗口相当于一次 API 调用的往返。
## 处理流程
### 归档
输入中 `olderThanDays` 为必填，`dryRun` 的默认值为 `true`。
| 步骤 | 处理 | 实现 |
|---|---|---|
| 1. 选择 | `MTIME`：Access Point `ListObjectsV2` 的 `LastModified`。`ATIME`：ONTAP REST API 的 `accessed_time`（VPC 内的 Lambda） | `select`、`ontap_rest` |
| 2. 记录 | 把大小、ETag、SHA-256、CRC64NVME，以及可获取时的 uid、gid、mode、mtime、atime 写入台账。5 GiB 以下用 Lambda，超出部分用 Fargate | `record`、Fargate 任务 |
| 3. 复制 | 5 GiB 以下用 SDK 集成的 `copyObject`（`SHA256`，把台账的 ETag 作为 `CopySourceIfMatch`）。超出部分用 Fargate 的分段复制（`CRC64NVME`） | Step Functions、Fargate |
| 4. 核对 | 把存储桶 `HeadObject`（`ChecksumMode=ENABLED`）的大小和校验和与台账比较。不一致则保留为 `MISMATCH`，并排除在删除对象之外 | `ledger` |
| 5. 第二份副本（可选） | 从 Access Point 复制到同一区域的另一个存储桶，并做同样的核对。不一致则排除在删除对象之外 | Step Functions、`ledger` |
| 6. 批准 | 把一致的清单写入 `manifests/<runId>.json`，通过 SNS 通知，并用 `waitForTaskToken` 等待 | `approval` |
| 7. 删除 | 仅在 `dryRun=false` 时执行。逐个文件确认 ETag 和大小，相同则 `DeleteObject`。不同则保留为 `CHANGED` | `delete` |
| 8. 记录 | `manifests/<runId>-result.json` 和 EMF 指标（件数、字节数） | `summarize` |
即使 `dryRun=true`，也会执行到第 6 步。也就是说会进行复制，并产生归档类别的存储费用（S3 Glacier Deep Archive 有最短存储期限）。试用时请把 `maxFiles` 设小。不会执行删除。
台账的状态按 `SELECTED`、`RECORDED`、`COPIED`、`VERIFIED`、`DELETED`、`RESTORED` 的顺序推进，中途的出口是 `CHANGED`、`MISMATCH`、`FAILED`。只有 `VERIFIED`（要求第二份副本时，还须完成其核对）的文件才能被删除。
### 恢复
输入为 `runId`，以及 `keys` 或 `prefix` 中的一个。可以指定 `tier`（默认 `Bulk`）和 `days`（默认 7）。
1. 在台账中选择 `DELETED` 的文件
2. 如果 Access Point 上已存在相同的键，则保留为 `EXISTS`，不覆盖
3. 对 S3 Glacier Flexible Retrieval 和 S3 Glacier Deep Archive 的对象请求 `RestoreObject`（S3 Glacier Instant Retrieval 不需要）
4. 完成等待采用轮询（每隔 `RestorePollMinutes` 读取 `HeadObject` 的 `Restore` 头，到 `RestoreMaxWaitHours` 时终止）。不使用 EventBridge 的 `Object Restore Completed`。存储桶的 EventBridge 通知已启用，因此以后可以切换
5. 从存储桶向 Access Point 执行 `CopyObject`（超过 5 GiB 用 Fargate）
6. 把台账设为 `RESTORED`，并写出用于重新设置属性的脚本 `manifests/<runId>-reapply.sh`

恢复后的文件，所有者为 0:1，模式为 644，修改时间为恢复的时刻（上述环境中的 1 次确认）。原来的值无法通过 `CopyObject` 恢复。
## 批准操作
批准通知中不包含令牌。令牌在 AWS Systems Manager Parameter Store 的 SecureString（`/<stack>/approvals/<runId>`）中。批准的人需要具有读取该参数的权限和 `states:SendTaskSuccess` 权限。
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output '{"approved": true, "approver": "<your IAM principal ARN>"}'
# 拒绝：
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
`approver` 是自行申报的值。输入的值会写入台账的 `deletedBy`，但证明实际批准主体的是 CloudTrail 的 `SendTaskSuccess` 事件。如果 `approver` 为空，或 `approved` 不是 `true`，则不会执行删除。
## 重新设置属性
恢复的最后会写出 `manifests/<runId>-reapply.sh`。在通过 NFS 挂载了该卷的主机上，以 root 身份执行。
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
脚本只包含 `chown`、`chmod` 和 `touch -d`，台账中的值按严格的格式检查，键通过 shell 引用成为一个单词。不符合格式的值会变成注释，不会被执行。ONTAP REST API 能否设置所有者、组、模式和修改时间尚未确认，因此未实现这条路径。
## 部署
### 前提
- Access Point 的别名和 ARN 两者都需要（IAM 需要两种形式。仅有别名的策略可以部署，但运行时会被拒绝）
- 归档用存储桶的名称（由堆栈创建。`DeletionPolicy: Retain`、Block Public Access、默认 SSE-S3、KMS 可选、启用 EventBridge 通知、必须使用 TLS）
- 仅在使用 `selection=ATIME` 和记录属性时需要：VPC、子网、ONTAP 凭据的密钥、管理端点、卷的 UUID。需要从 VPC 内的 Lambda 到 Secrets Manager 和 S3 的路径（VPC 端点或 NAT）
- 仅在处理超过 5 GiB 的文件时需要：放在 ECR 中的镜像。Access Point 是 Internet-origin，因此 Fargate 的子网需要 NAT 或公网 IP
### 步骤
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # 替换 <PLACEHOLDER>
sam build && sam deploy
```
使用 Fargate 时，在仓库根目录构建镜像，push 到自己的 ECR 仓库，并指定给 `FargateImageUri`。
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
运行时，先用省略 `dryRun`（即为 `true`）的输入执行。
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20}'
```
要执行到删除，请把 `"dryRun": false` 作为 JSON 布尔值传入。字符串 `"false"` 会成为输入错误，不会执行删除。
## 目录结构
```
archive-verify-delete/
├── template.yaml                # SAM：存储桶、台账、8 个 Lambda、2 个状态机、Fargate（可选）
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
领域逻辑（校验和、输入检查、台账）位于 [`shared/archive_verify/`](../../../shared/archive_verify/)，在 `shared/tests/` 中测试。对 Access Point 的读写都经过 `shared/s3ap_helper.py`。
## 本地测试
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
为了确认删除判定被破坏时能够被检测到，用去掉 ETag 比较的桩代码把 `test_does_not_delete_when_etag_changed` 和 `test_does_not_delete_when_size_differs_but_etag_equal` 运行了 1 次，2 个测试都以 `assert 'DELETED' == 'CHANGED'` 失败。恢复原状后，29 个测试通过。
## Success Metrics
### Outcome
把很少被读取的文件，经过核对和人的批准后转移到 S3 Glacier 系列的类别，降低卷的使用量。转移后的文件可以从台账中查找并恢复。
### Metrics
目标值由使用者决定。这里不给出数值。
| 类别 | 指标 | 定义 |
|---|---|---|
| Business Outcome | 释放的容量 | `bytesDeleted`（`-result.json`）。只要快照还在，卷的使用量就不会下降 |
| Technical KPI | 核对一致率 | `VERIFIED` ÷（`VERIFIED` + `MISMATCH`） |
| Technical KPI | 未删除的件数 | `CHANGED`、`MISMATCH` 和 `FAILED` 的合计 |
| Quality KPI | 未经批准而被删除的件数 | 必须为 0。统计台账中 `deletedBy` 为空的 `DELETED` |
| Cost KPI | 每次运行的 Lambda、Fargate、DynamoDB、S3 请求、归档类别的存储费用 | 未测量。先用 `dryRun=true` 和较小的 `maxFiles` 估算 |
| Go / No-Go | 在实际环境的端到端运行中，所有已复制的文件都变为 `VERIFIED`，有意制造的 `CHANGED` 不会被删除，恢复后文件的 SHA-256 一致 | 在满足之前，不要对生产卷使用 `dryRun=false` |
### Measurement Method
Step Functions 的执行历史、`manifests/<runId>-result.json`、CloudWatch 的 EMF 指标（`FilesVerified`、`FilesDeleted`、`FilesMismatch`、`FilesChanged`、`FilesFailed`、`BytesVerified`、`BytesDeleted`）、台账。
## Performance Considerations
未测量。以下是设计上的因素。
- 源文件会被读取 2 次。第 1 次是为计算哈希而通过 Access Point 读取，第 2 次是 `CopyObject` 在服务器端读取。会产生读取请求费用，位于容量池中的数据还会产生容量池的读取费用
- 并行度为 `MapConcurrency`（默认 10）。请根据 Access Point 和 ONTAP 的负载，从较小的值开始
- Lambda 的上限为 15 分钟。由于没有测量从 Access Point 的读取速度，无法确定默认的 5 GiB（`LargeFileThresholdBytes`）是否足够。如果不够，请调低；由 Fargate 处理的部分会增加
- 清单会把 `ListObjectsV2` 的全部结果载入一个 Lambda 的内存。超过数百万件时，请用 `prefix` 分开处理
- `selection=ATIME` 以深度优先遍历目录。扫描上限为 200,000 个条目（`ONTAP_SCAN_LIMIT`），超出时返回到中途为止的结果
- 恢复的等待时间由类别和 `tier` 决定。AWS 记载 S3 Glacier Deep Archive 在 Standard 下 12 小时以内，在 Bulk 下 48 小时以内。`RestoreMaxWaitHours` 的默认值为 72
## Governance Note
> 本模式提供技术架构方面的指导。它不是法律、合规或监管方面的建议。请组织咨询合格的专业人士。
- 核对结果和批准是供人做最终判断的辅助信号。未使用 AI
- 如果需要满足保留期限和不可变性，本模式不支持。因为没有使用 Object Lock 等，所以有权限就可以删除
- 输出分类：台账和清单包含文件路径、大小、哈希、属性（`dataClassification: operational-metadata`）。文件内容会进入归档用存储桶，因此请按与原始数据相同的分类处理
- Human Review：每次运行都必须批准。没有基于置信度的自动批准
- IAM：持有 `s3:DeleteObject` 的只有 `delete` 函数的角色。Fargate 任务只负责复制，没有删除权限。没有授予任何人删除台账条目的权限
- 审计：批准和删除会记录在台账（`deletedBy`、`deletedAt`）、Step Functions 的执行历史和 CloudTrail 中
## 限制与未确认事项
- 从 Access Point 直接复制到其他区域的存储桶时返回了 `AccessDenied`（1 个 Access Point，1 次）。第二份副本仅以同一区域的存储桶为对象
- 这是在 UNIX 样式卷上的确认。把修改时间改回原值后再改动内容的操作，以及 `chown`，能否通过 ETag 检测到，尚未确认
- 属性是通过目录清单获取的。为了一个文件要读取整个父目录，因此对大目录会变慢
- 归档用存储桶的版本控制不是 Object Lock。版本会保留，但有权限就可以删除版本
## 相关文档
- [Architecture (EN)](docs/architecture.en.md)
- [S3 Access Points 兼容性备忘](../../../docs/s3ap-compatibility-notes.md)
- [转移到归档类别的 8 种机制的比较](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)（日文）
