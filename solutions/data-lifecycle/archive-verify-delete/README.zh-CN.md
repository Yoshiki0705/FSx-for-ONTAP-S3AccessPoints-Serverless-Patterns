# archive-verify-delete：仅用 S3 API 复制、核对，并在批准后删除的归档
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **文档**: [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## 概述
本模式把 Amazon FSx for NetApp ONTAP（以下简称 FSx for ONTAP）卷上很少被读取的文件，转移到 S3 Glacier 系列的存储类别。文件的读取、写入和删除使用 S3 Access Points 的 S3 API，不为此挂载 NFS。但有两件事需要更多条件：按最后访问时间选择（`selection=ATIME`）和获取属性要使用 ONTAP REST API（VPC 内的 Lambda 函数、ONTAP 凭据、管理端点）；恢复后把所有者、模式和修改时间放回原值，则需要通过 NFS 挂载该卷的主机。
一个文件按下列顺序处理。在任何一步中条件不再成立的文件，会被排除在删除对象之外。
1. 在台账（DynamoDB 表）中记录大小、ETag、SHA-256 和 CRC64NVME
2. 指定存储类别，用 `CopyObject` 复制到归档用存储桶（键为 `<prefix><runId>/<original key>`）
3. 把存储桶返回的校验和与台账中的值进行比较
4. 由人批准一致文件的清单。批准会在台账中记录为 `APPROVED`；批准者与启动运行的主体相同时会被拒绝（默认；比较的是申报的值，不是主体的证明）
5. 确认 Access Point 的 ETag 和大小仍与台账相同后，只删除台账中为 `APPROVED` 的文件

恢复时，本模式先在台账中查找文件，在存储桶中请求恢复，等待完成后用 `CopyObject` 复制回 Access Point，然后把恢复的每个文件读回，与台账中的 SHA-256 和 CRC64NVME 比较。
本模式不使用 S3 Object Lock、S3 Glacier Vault Lock、AWS Backup Vault Lock、SnapLock 和快照锁定，模板中也没有写入。因为不设置保留期限，所以对归档用存储桶中的对象，只要有权限就可以删除。
本模式的前提，以及与其他方式的比较，见[转移到归档类别的 9 种机制的比较](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)（日文）。
## 已测量和未测量的内容
| 类别 | 内容 |
|---|---|
| 各组成部分已在实际环境中各确认 1 次（记录在上述比较资料中，2026-11-24 和 2026-11-26，ap-northeast-1，第 1 代 `SINGLE_AZ_1`，ONTAP 9.19.1P4D1，UNIX 样式卷，Access Point 用户为 UNIX root） | 给 `CopyObject` 指定 `ChecksumAlgorithm=SHA256` 后，存储桶的 `ChecksumSHA256` 为 `FULL_OBJECT`，与文件的 SHA-256 一致（最大 8 MiB）。5.5 GiB 的分段上传中 SHA-256 变为 `COMPOSITE`，CRC64NVME 为 `FULL_OBJECT` 且一致。使用旧 ETag 的 `--copy-source-if-match` 返回 `PreconditionFailed`。Access Point 的 `DeleteObject` 不支持 `If-Match`。在 Step Functions 的 SDK 集成中，可以把 Access Point 别名传给 `Bucket` |
| 在本仓库中确认 | 使用 moto 的单元测试，以及状态机和 IAM 结构的测试。未连接 AWS。实机端到端运行中发现的 7 个缺陷（ONTAP REST 函数的调用权限、TLS 验证、重复恢复请求的错误名称、状态机的日志权限、`HeadObject` 返回的 403、告警的发布权限）已通过能够复现它们的测试修复 |
| 在包含 5.5 GiB 的 7 个文件的运行中各确认 1 次（2026-11-26，与上述相同的环境，`selection=ATIME`，`GLACIER`，7 个文件） | 通过 ONTAP REST API 按 `accessed_time` 选择，并获取 uid、gid、mode、mtime、atime（根是卷的根，路径开头没有斜杠；`unix_permissions` 以整数 `640` 返回）。Distributed Map 的 `ItemReader` 和 `ResultWriter`。用 Fargate 进行 5.5 GiB 的分段复制（带 `CopySourceIfMatch`，CRC64NVME 与台账一致）。在 Lambda 中对 5.3 GB（约 4.94 GiB）计算哈希（69.8 秒，配置内存 2048 MB，使用 152 MB）。第二份副本。批准后的删除。等待批准期间在 NFS 上改写的文件变为 `CHANGED`，没有被删除。拒绝批准后什么都没有被删除。用 `Expedited` 恢复（含 5.5 GiB），恢复的 6 个文件 SHA-256 一致（7 个文件中剩下的 1 个已被改写，既没有被删除也没有被恢复）。用 `reapply.sh` 恢复 uid、gid、mode、mtime |
| 在确认排除与批准的运行中各确认 1 次（2026-11-26，同一环境，`GLACIER`，开启第二份副本。dry run 使用 `selection=ATIME`，正式运行使用 `selection=MTIME`，属性来自 ONTAP REST。文件为 64 B 至 1 MiB，另有 1 个 51 GiB 的稀疏文件） | 7 个文件的运行中没有的项目的确认。在 `maxFiles=50` 下，3 个 64 B 的文件和 1 个 131,071 B 的文件低于最小大小，131,073 B 的文件被保留。`*.vmdk` 和法律保留前缀被排除。51 GiB 的稀疏文件被记录为 `SKIPPED_TOO_LARGE`，没有被复制。重复使用的 `runId`，以及没有 `requestedBy` 的正式运行输入，都作为输入错误而停止。批准者 ARN 与启动者相同的批准以 `APPROVAL_REFUSED` 结束，没有任何删除。在没有批准的情况下直接调用 `delete` 函数，返回 `NOT_APPROVED` 且没有删除。批准者不同时，删除了 3 个文件，等待期间被改写的 1 个文件保留为 `CHANGED`。对为模拟中断而设为 `DELETING` 的条目，同一执行的重试记录为 `DELETED`（`already gone on retry`），另一个执行被拒绝，`reconcile` 记录为 `DELETED`（该确认使用的是加入执行状态检查之前的代码；在当前代码上，重试和恢复路径只有单元测试覆盖，没有在实机上运行过）。恢复后，3 个文件为 `RESTORE_VERIFIED`。告警已发布到 KMS 加密的主题（修复之后） |
| 在确认直接调用的检查中各确认 1 次（2026-11-26，同一账户和 Access Point，`selection=MTIME`，`GLACIER`，无 Fargate，8 个 256 KiB 的文件，`MapConcurrency=1`） | 批准之后立即停止执行，留下了 7 个 `APPROVED` 条目。用其他执行的 `claim` 直接调用 `delete` 函数，返回 `NOT_APPROVED`（`approval not current`）。修复之前，把已停止执行自身的 ARN 作为 `claim` 的调用，使 1 个文件变为 `DELETED`。加入执行状态的检查之后，同样的调用返回 `NOT_APPROVED`（`claiming execution is not running`）。`reconcile` 把 7 个条目恢复为 `VERIFIED`。在运行中的执行里正常删除，7 个文件变为 `DELETED`。批准之后和拒绝之后，任务令牌的参数都已被删除。令牌使用堆栈的 KMS 密钥加密 |
### 环境与各步骤的结果
环境为 ap-northeast-1、FSx for ONTAP 第 1 代 `SINGLE_AZ_1`、ONTAP 9.19.1P4D1、UNIX 安全样式的卷，Access Point 的文件系统用户为 UNIX root。运行日期为 2026-11-26（时间为日本标准时间），每个步骤只运行了 1 次。配置为 `selection=ATIME`、`GLACIER`、有第二份副本，Fargate 为 arm64 的 2 vCPU 和 8 GiB。数据为 6 个小文件（3 个 64 B、3 个 8 MiB，所有者 1234:5678，模式 640，mtime 和 atime 为 2020-01-02）和 1 个 5,905,580,032 B 的文件。
| 步骤 | 结果 | 耗时 |
|---|---|---|
| 1. 部署 | 成功。但运行中发现 2 个缺陷，修复后重新部署 | 从准备到部署约 30 分钟（16:19 至 16:50） |
| 2. dry run（`dryRun=true`） | 修复后成功。7 个文件全部 `VERIFIED`（SHA-256 一致 6 个，CRC64NVME 一致 1 个），第二份副本也是 `VERIFIED`。删除 0 字节，NFS 上 7 个文件全部保留 | 244 秒（含等待批准约 70 秒） |
| 3. 等待批准期间的改写 | 在 NFS 上把 1 个文件以相同大小覆盖写入 4 KiB（mtime 更新）。批准后变为 `CHANGED`（ETag 或大小不一致），没有被删除 | |
| 4. 正式运行（`dryRun=false`）与批准 | 6 个 `DELETED`，1 个 `CHANGED`。`bytesDeleted` 为 5,922,357,440。NFS 上 6 个文件消失，只剩被改写的 1 个 | 310 秒（到发出批准请求 172 秒，从批准到完成约 6 秒） |
| 5. 恢复（`tier=Expedited`，`days=1`） | 6 个 `RESTORED`（含 5.5 GiB）。6 个文件的 SHA-256 都与步骤 1 之前在 NFS 上记录的值一致。`CHANGED` 的 1 个不在对象内 | 287 秒（5 个小文件约 2.5 分钟，5.5 GiB 的 Fargate 复制用时 2 分 38 秒） |
| 6. 拒绝批准（`send-task-failure`） | 执行以 `REJECTED_OR_TIMED_OUT` 结束，3 个文件仍为 `VERIFIED`。`deletedBy` 为空，NFS 上 3 个文件都保留 | 16 秒 |
| 追加：在 Lambda 中对 5.3 GB（约 4.94 GiB）计算哈希 | `VERIFIED`（SHA-256 与 NFS 的值一致），第二份副本也是 `VERIFIED` | `record` 函数 69.8 秒（配置内存 2048 MB，使用 152 MB） |
| 追加：重复提交恢复请求 | 第二次返回 HTTP 409 `RestoreAlreadyInProgress`。Step Functions 的 SDK 集成以 `S3.S3Exception` 返回 | |
之后已删除全部资源，并通过回读确认。
### 使用量（各运行 1 次，不是账单）
| 运行 | 文件数 | 耗时 | 状态转换（父 + 子 Map 执行） | Fargate 任务 |
|---|---|---|---|---|
| dry run | 7 | 244 秒 | 12 + 107 = 119 | 2 次（哈希与复制 96 秒，第二份副本 35 秒） |
| 正式运行 | 7 | 310 秒 | 13 + 114 = 127 | 2 次（94 秒，35 秒） |
| 恢复 | 6 | 287 秒 | 4 + 103 = 107 | 1 次（156 秒） |
| 拒绝 | 3 | 16 秒 | 10 + 45 = 55 | 0 次 |
- Lambda 执行时间合计（CloudWatch。含失败的调用，不含 4.94 GiB 的运行）：`select` 13 次 5.9 秒，`ontap_rest` 11 次 13.4 秒（失败 2 次），`record` 17 次 11.7 秒，`ledger` 34 次 9.1 秒，`approval` 6 次 4.3 秒，`delete` 7 次 5.6 秒，`summarize` 5 次 5.1 秒，`restore` 26 次 9.2 秒
- Fargate 共 5 个任务，合计约 416 秒（2 vCPU、8 GiB、arm64）。DynamoDB（按需）读取 68.5 RCU、写入 74 WCU（全部运行合计）
- 未测量 S3 请求数（未启用请求指标）
确认排除与批准的运行中的状态转换（2026-11-26，小文件，开启第二份副本，`MapConcurrency=2`），各运行 1 次；会随文件大小和路径而变化。

| 执行 | 文件数 | 耗时 | 状态转换（父 + 子 Map 执行） | 每个文件 |
|---|---|---|---|---|
| dry run `e2e2-dry1` | 4 | 66 秒（含约 20 秒的批准等待） | 12 + 60 = 72 | 18 |
| 正式运行 `e2e2-real2`（删除 3 个，`CHANGED` 1 个） | 4 | 45 秒（含批准等待） | 14 + 64 = 78 | 19.5 |
| 恢复 `e2e2-rest2`（Expedited，含核对，`EXISTS` 1 个） | 4 | 192 秒 | 4 + 52 = 56 | 14 |
### 端到端运行中发现并修复的缺陷
均已通过能够复现的测试修复。
| # | 现象 | 原因与修复 |
|---|---|---|
| 1 | `selection=ATIME` 的运行在选择阶段失败 | 归档状态机的角色没有对 ONTAP REST 函数的 `lambda:InvokeFunction`。已添加权限 |
| 2 | ONTAP REST 函数因 `CERTIFICATE_VERIFY_FAILED` 失败 | 始终验证 TLS，但 FSx for ONTAP 管理端点的证书不是由公共 CA 签发。已添加参数 `OntapVerifySsl`（默认 `false`） |
| 3 | 重复提交恢复请求被当作文件失败 | Step Functions 的 SDK 集成把 `RestoreAlreadyInProgress` 以 `S3.S3Exception` 返回，因此与 `S3.RestoreAlreadyInProgressException` 的 `Catch` 不匹配。已改为把进行中的恢复送入等待完成的循环 |
确认排除与批准的运行（2026-11-26）又发现并修复了 3 个缺陷。

| # | 现象 | 原因与修复 |
|---|---|---|
| 4 | 部署失败，提示 `The state machine IAM Role is not authorized to access the Log Destination` | 状态机的角色缺少执行日志所需的 `logs:CreateLogDelivery` 及相关权限。已添加 |
| 5 | 对已删除文件的删除重试和 `reconcile` 在 `HeadObject` 上收到 403 | 对没有 `s3:ListBucket` 的调用方，对不存在的键执行 `HeadObject` 返回 403 而不是 404。已在 IAM 和 Access Point 策略中给 `delete` 和 `restore` 函数添加 `s3:ListBucket` |
| 6 | CloudWatch 告警通知失败，提示 `CloudWatch Alarms is not authorized to perform: SNS:Publish` | 密钥策略允许了 CloudWatch，但主题策略只允许 EventBridge。已添加 `cloudwatch.amazonaws.com` 的语句 |
| 7 | 不使用 Fargate（`FargateImageUri` 为空）的部署因 `is not authorized to create managed-rule` 失败（确认直接调用的检查） | 两个定义都含有 `ecs:runTask.sync` 状态，创建状态机时会检查角色的 `events:PutRule` 等权限。该权限位于 `UseFargate` 条件之内。已去掉该条件 |
### 端到端运行中得知的行为
这些行为没有作为缺陷处理。
- 在 `selection=ATIME` 下，本模式自身的读取会更新 `accessed_time`。用 `dryRun=true` 运行一次后，计算哈希的读取使每个文件的 atime 变为运行时间，因此用相同输入运行 `dryRun=false` 不会选中任何文件（在 dry run 之后立即正式运行时，以 0 个文件结束）。若要在 dry run 之后立即对相同的候选正式运行，请使用 `selection=MTIME`（`LastModified` 不会因读取而改变）
- 关于 ETag，官方的表述和本环境的测量如下。官方页面（[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)，2026-11-26 阅读）写道 "The ETag reflects changes only to the contents of an object, not its metadata"。在本环境的 1 次测量中，大小和 mtime 相同、内容不同的 3 个文件返回了相同的 ETag。因此本模式认为，删除前对 ETag 和大小的确认，无法发现大小和 mtime 都不变的内容变更。大小相同但在等待批准期间 mtime 更新的改写被检测到了（第一次运行的步骤 3，以及第二次正式运行） [E-023]
- 通过 Access Point 删除目录中的最后一个文件时，变空的上级目录也会一并消失（在 `arc-e2e/large/` 上确认）。恢复时的 `CopyObject` 会重新创建该目录
- 恢复后的文件所有者为 0:1，模式为 644，修改时间为恢复的时间。在通过 NFS 挂载了卷的主机上，以 root 运行生成的 `reapply.sh` 后，恢复为原来的 uid、gid、mode、mtime（1234:5678、640、2020-01-02 03:04:05），内容的 SHA-256 没有变化
- 当归档用存储桶中有副本时，恢复状态机也会选择保留为 `CHANGED` 的文件。如果 Access Point 上已存在该键，则保留为 `EXISTS`，不覆盖（在确认排除与批准的运行的恢复中确认过 1 次）
- 5.5 GiB 文件的 `Expedited` 恢复请求被接受，并在约 4 分钟内完成
### 未确认的事项
- 大量文件时的耗时和费用。其他并行度设置下的文件系统吞吐量和客户端延迟
- `Standard` 和 `Bulk` 恢复的完成等待（只运行了 `Expedited`）
- `S3.SlowDownException` 的重试（未观察到 SDK 集成返回的名称，可能出现与缺陷 3 同类的不匹配）
- CloudTrail 数据事件中的删除和批准记录。S3 数据事件（`DeleteObject` 等）只有在跟踪启用了数据事件时才会记录。本次运行未确认账户的跟踪是否包含此 Access Point 的数据事件。`SendTaskSuccess` 是管理事件，其记录同样未确认
- 批准的拒绝和接受，是用同一个 SSO 主体在批准输出中声明不同的 ARN 来比较的。`approver` 的值是自行申报的，所以换成不同的 IAM 主体应该得到相同的结果，但没有使用真正的第二个主体
- 超过 50 GiB 的文件的复制和恢复（只用稀疏文件确认了将其排除在选择之外）
- NTFS 卷、非 root 用户、第 2 代、Multi-AZ
- 恢复中除了不选择 `CHANGED` 文件之外的 `EXISTS` 路径（NFS 上已有同名文件的情况）
- 等到 `ApprovalPendingAlarm` 实际变为 `ALARM`（只确认了指标已发布）
- 有 1 次候选为 0 个的情况原因不明。在用 `touch -d` 还原 atime 约 10 秒后的运行中没有候选。约 17 分钟后的确认返回了 2020 年的值，其他确认也返回了 6 个文件。未能确定原因，也没有再次出现
- 在实机上运行删除的重试和恢复路径（`DELETING`，相同的 `claimedBy`）。上面的重试确认使用的是加入执行状态检查之前的代码。在当前代码上，该路径只有单元测试覆盖
### 删除前确认中残留的写入窗口
删除前的确认中仍残留一个写入窗口。Access Point 的 `DeleteObject` 不支持条件删除，因此在用 `HeadObject` 确认之后到删除之前被改写的情况无法检测。该窗口相当于一次 API 调用往返。
## 处理流程
### 归档
`olderThanDays` 为必填，`dryRun` 的默认值为 `true`。当 `RequireSeparateApprover=true`（默认）时，`dryRun=false` 的运行需要在 `requestedBy` 中给出启动主体的 ARN。
| 步骤 | 处理 | 实现 |
|---|---|---|
| 1. 选择 | `MTIME`：Access Point `ListObjectsV2` 的 `LastModified`。`ATIME`：ONTAP REST API 的 `accessed_time`（VPC 内的 Lambda）。应用排除条件（见下表） | `select`、`ontap_rest` |
| 2. 记录 | 把大小、ETag、SHA-256、CRC64NVME，以及可获取时的 uid、gid、mode、mtime、atime 写入台账。5 GiB 以下用 Lambda，超出部分用 Fargate | `record`、Fargate 任务 |
| 3. 复制 | 5 GiB 以下用 SDK 集成的 `copyObject`（`SHA256`，把台账的 ETag 作为 `CopySourceIfMatch`）。超出部分用 Fargate 的分段复制（`CRC64NVME`） | Step Functions、Fargate |
| 4. 核对 | 把存储桶 `HeadObject`（`ChecksumMode=ENABLED`）的大小和校验和与台账比较。不一致则保留为 `MISMATCH`，并排除在删除对象之外 | `ledger` |
| 5. 第二份副本（可选） | 从 Access Point 复制到同一区域的另一个存储桶，并做同样的核对。不一致则排除在删除对象之外 | Step Functions、`ledger` |
| 6. 批准 | 把一致的清单写入 `manifests/<runId>.json`，通过 SNS 通知，并用 `waitForTaskToken` 等待。只有一份副本时，以及文件无法恢复时，通知中会写明 | `approval` |
| 7. 记录批准 | 仅在 `dryRun=false` 时执行。批准者与启动者相同则拒绝。否则在台账中把清单中的每个文件从 `VERIFIED` 改为 `APPROVED`，并写入 `manifests/<runId>-approval.json` | `approval` |
| 8. 删除 | 仅限台账中为 `APPROVED` 的文件。逐个文件确认 ETag 和大小，相同则 `DeleteObject`，不同则保留为 `CHANGED` | `delete` |
| 9. 记录 | `manifests/<runId>-result.json` 和 EMF 指标（件数、字节数、排除数）。仍有 `DELETING` 或 `APPROVED` 的条目时为 `COMPLETED_WITH_ERRORS` | `summarize` |
即使 `dryRun=true`，也会执行到第 6 步。也就是说会进行复制，并产生归档类别的存储费用（有最短存储期限）。试用时请把 `maxFiles` 设小。不会执行删除。
台账的状态按 `SELECTED`、`RECORDED`、`COPIED`、`VERIFIED`、`APPROVED`、`DELETING`、`DELETED`、`RESTORED`、`RESTORE_VERIFIED` 的顺序推进，中途的出口是 `CHANGED`、`MISMATCH`、`FAILED`、`SKIPPED_TOO_LARGE` 和 `RESTORE_MISMATCH`。只有 `APPROVED` 的文件（要求第二份副本时，还须其第二份副本也已核对）才能被删除。

已使用过的 `runId` 会成为输入错误。要继续中断的运行，请给出相同的 `runId` 并加上 `"resume": true`（见下文“从中断的删除中恢复”）。归档键中带有 `runId`，因此 dry run 与正式运行之间，或改写后的重新归档，都不会互相覆盖对象。未启用版本控制时，覆盖会删除先前的对象，在有最短存储期限的类别中，这可能产生提前删除费用。

选择时排除的内容：

| 条件 | 默认 | 原因 |
|---|---|---|
| 超过 50 GiB | 排除，并在台账中记录为 `SKIPPED_TOO_LARGE`。`allowOversize: true` 会将其包含在内 | 官方页面（[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)，2026-11-26 阅读）写道 "Maximum object size is 50 GiB for uploads, but you can download objects larger than that"。恢复是通过 Access Point 写入的，因此本模式无法把更大的文件恢复到那里（可以直接从存储桶下载） [E-021] |
| 小于 `MinFileSizeBytes` | 131,072 字节（128 KiB）。可用输入的 `minSizeBytes` 更改 | 根据[Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare)（2026-11-26 阅读），Standard-IA 和 Glacier Instant Retrieval 每个对象至少按 128 KB 计费，Glacier Flexible Retrieval 和 Deep Archive 每个对象另加 40 KB 的元数据（32 KB 按该类别的价格，8 KB 按 Standard 的价格）。对小文件来说，这比数据本身还大 |
| `ExcludePatterns`（glob）、`ExcludePrefixes` | `ExcludePatterns` 为下面的列表，`ExcludePrefixes` 为空 | 堆栈的值始终适用；输入的 `excludePatterns` 和 `excludePrefixes` 只能追加。请把法律保留的前缀放在这里 |

Iceberg、Delta 或 Hive 表的数据文件、运行中的数据库的文件、虚拟机磁盘镜像（`*.vmdk`、`*.vhd`、`*.qcow2` 等）一律排除。本模式逐个文件移动，不了解表的元数据，也不了解持有文件打开状态的进程。请用表自身的功能（分离分区、让快照过期）整理表，只以整理后剩下的路径为对象。是否处于法律保留，由贵方的法务部门判断，本模式不做这个判断。
`ExcludePatterns` 的默认值是起点而不是完整列表，列出的是容易造成实际事故的文件类型。虚拟机磁盘镜像（`*.vmdk`、`*.vhd`、`*.vhdx`、`*.vdi`、`*.qcow2`）在虚拟机打开期间持续写入，逐个文件复制会得到损坏的副本。数据库的数据和日志文件（SQL Server 的 `*.mdf`、`*.ndf`、`*.ldf`，MySQL InnoDB 的 `*.ibd`，Oracle 的 `*.dbf`）由数据库打开并写入。表格式的元数据目录（Delta 的 `_delta_log/`、Hudi 的 `.hoodie/`、Iceberg 的 `metadata/`）保存数据文件的清单，只移动数据文件会破坏表。匹配区分大小写（`*.VMDK` 不匹配）。名为 `metadata/` 但不是 Iceberg 的目录也会被排除。`*.parquet` 这类表的数据文件不在默认值中，请添加适合您环境的模式。只有卷上完全没有这类文件时，才可以设为空。
### 恢复
输入为 `runId`，以及 `keys` 或 `prefix` 中的一个。可以指定 `tier`（默认 `Bulk`）和 `days`（默认 7）。
1. 在台账中选择 `DELETED` 的文件。当归档用存储桶中有副本时，`DELETING` 和 `CHANGED` 的文件也会被选择（因此可以恢复中断的删除所留下的条目）
2. 如果 Access Point 上已存在相同的键，则保留为 `EXISTS`，不覆盖
3. 对 S3 Glacier Flexible Retrieval 和 S3 Glacier Deep Archive 的对象请求 `RestoreObject`（S3 Glacier Instant Retrieval 不需要）
4. 完成等待采用轮询（每隔 `RestorePollMinutes` 读取 `HeadObject` 的 `Restore` 头，到 `RestoreMaxWaitHours` 时放弃）。不使用 EventBridge 的 `Object Restore Completed`。存储桶的 EventBridge 通知已启用，因此以后可以切换
5. 从存储桶向 Access Point 执行 `CopyObject`（超过 5 GiB 用 Fargate）。台账设为 `RESTORED`
6. 通过 Access Point 把恢复的文件读回，计算哈希，并与台账中的 SHA-256、CRC64NVME 和大小比较（超过 5 GiB 用 Fargate）。一致为 `RESTORE_VERIFIED`，不一致为 `RESTORE_MISMATCH`
7. 仅针对 `RESTORE_VERIFIED` 的文件，写出用于重新设置属性的脚本 `manifests/<runId>-reapply.sh`

恢复后的文件，所有者为 0:1，模式为 644，修改时间为恢复的时刻（上述环境中的确认）。原来的值无法通过 `CopyObject` 恢复。
`RESTORE_MISMATCH` 的文件默认不会被选为恢复对象：Access Point 上的副本与台账不一致，若直接选中会作为 `EXISTS` 保留。要重做时，在恢复输入中加上 `"retryMismatched": true`（JSON 布尔值）。只有此时，该 `runId` 的台账当前为 `RESTORE_MISMATCH` 的条目才会被选中，并用存储桶中的副本覆盖 Access Point 上不一致的副本。其他状态的条目即使指定了该标志，也不会覆盖已有文件。覆盖之后，同样的回读会得到 `RESTORE_VERIFIED` 或 `RESTORE_MISMATCH`。
### 从中断的删除中恢复
Lambda 在删除中途停止，或重试次数用尽，可能使台账中的条目留在 `DELETING` 或 `APPROVED`。结果中会显示为 `COMPLETED_WITH_ERRORS`、`stuckDeleting` 和 `notDeleted`，并且 `FilesStuckDeletingAlarm` 会触发。用相同的 `runId` 和 `"resume": true` 启动归档状态机，会运行 `reconcile`，按下表处理这些条目，然后对剩下的文件重新请求批准。
| 台账 | Access Point | 结果 |
|---|---|---|
| `DELETING` | 没有文件 | `DELETED`（删除已经发生；`reconciled: true`） |
| `DELETING`、`APPROVED` | 文件存在，ETag 和大小与台账相同 | 回到 `VERIFIED`；删除需要重新批准 |
| `DELETING`、`APPROVED` | 文件存在，与台账不同 | `CHANGED` |
| 任一 | 持有该条目的执行仍在运行 | 不处理 |
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"runId": "<runId>", "olderThanDays": 0, "resume": true, "dryRun": false, "requestedBy": "<your IAM principal ARN>"}'
```
需要把留在 `DELETING` 的条目找回来时，恢复状态机会从归档用存储桶中的副本恢复它。
## 批准操作
批准通知中不包含令牌。令牌在 Systems Manager Parameter Store 的 SecureString（`/<stack>/approvals/<runId>`）中。批准的人需要具有读取该参数的权限和 `states:SendTaskSuccess` 权限。
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output "{\"approved\": true, \"approver\": \"$(aws sts get-caller-identity --query Arn --output text)\"}"
# 拒绝：
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
批准之后，`approval` 函数会把 `approver` 与启动输入中的 `requestedBy` 比较（`RequireSeparateApprover=true`，默认）。相同的主体会以 `APPROVAL_REFUSED` 结束运行，不会把任何文件标记为 `APPROVED`。角色的 ARN 和该角色的会话 ARN 视为同一主体。否则，清单中的每个文件都会在台账中变为 `APPROVED`，并带有 `approvedBy`、`approvedAt` 和执行 ARN。`delete` 函数只删除带有这条记录的文件；直接调用它，也不会删除没有这条记录的文件。

`approver` 和 `requestedBy` 都是调用方自行申报的值。台账的 `deletedBy` 取自其 `approvedBy`。实际启动和批准的主体，记录在 CloudTrail 的 `StartExecution` 和 `SendTaskSuccess` 事件中。若要按主体保证职责分离，请在 IAM 中把启动和批准的角色分开。 启动者与批准者的比较，是对两个自行申报的值的比较。它不强制由其他主体批准，本文档也不声称它能强制。事后的控制是 CloudTrail 的 `userIdentity`：核对执行 `StartExecution` 和 `SendTaskSuccess` 的主体。
### 批准的有效范围与令牌的处理
`delete` 函数只删除这样的条目：台账为 `APPROVED`，`approvalExecutionArn` 与当前执行相同，且 `approvedAt` 在 `ApprovalValidityHours`（默认 24 小时）以内。批准之后停止执行会留下 `APPROVED` 条目，但它们与其他执行的 `claim` 不一致，因此直接调用 `delete` 函数也会得到 `NOT_APPROVED`。超过期限的批准同样被拒绝。留下的条目由 `reconcile` 恢复为 `VERIFIED`。 即使 `claim` 是已停止的执行自身的 ARN（台账中有记录），只要该执行不是 `RUNNING`，也会被拒绝。无法读取执行状态时同样拒绝。

任务令牌在批准成立时（`approval` 函数）、拒绝与启动者相同主体的批准时，以及批准被拒绝、超时或执行失败之后（`summarize`）删除。没有到达 `summarize` 而残留的令牌，由 `watchdog` 在超过批准超时加 1 小时后删除。令牌使用堆栈的客户管理 KMS 密钥（输出 `ApprovalTokenKeyArn`）加密，因此读取它需要 `ssm:GetParameter`，以及该密钥的 `kms:Decrypt`。

批准者角色的 IAM 策略示例。IAM 无法为 `states:SendTaskSuccess` 和 `states:SendTaskFailure` 指定资源（[Step Functions 授权参考](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsstepfunctions.html)，2026-11-26 查阅），所以不能把它们限定在此状态机的执行上。持有令牌的人就能回应该执行，因此能收窄的是读取令牌的途径。不要给这个角色授予 `StartExecution`。
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadApprovalToken",
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:<region>:<account>:parameter/<stack>/approvals/*"
    },
    {
      "Sid": "DecryptApprovalToken",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "<ApprovalTokenKeyArn>",
      "Condition": {"StringEquals": {"kms:ViaService": "ssm.<region>.amazonaws.com"}}
    },
    {
      "Sid": "ReportApproval",
      "Effect": "Allow",
      "Action": ["states:SendTaskSuccess", "states:SendTaskFailure"],
      "Resource": "*"
    }
  ]
}
```
## 重新设置属性
恢复的最后会写出 `manifests/<runId>-reapply.sh`。在通过 NFS 挂载了该卷的主机上，以 root 身份执行。
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
脚本只包含 `chown`、`chmod` 和 `touch -d`，台账中的值按严格的格式检查，键通过 shell 引用成为一个单词。不符合格式的值会变成注释，不会被执行。ONTAP REST API 能否设置所有者、组、模式和修改时间尚未确认，因此未实现这条路径。
## 部署
### 前提
- Access Point 的别名和 ARN 两者都需要（IAM 需要两种形式。仅有别名的策略可以部署，但运行时会被拒绝）
- Access Point 策略。此堆栈不创建 Access Point（通过参数接收已有的 Access Point），也不管理其策略，因此在部署后按下面的步骤附加。不附加时，第一次 S3 调用会在运行时被拒绝
- 归档用存储桶的名称（由堆栈创建。`DeletionPolicy: Retain`、Block Public Access、默认 SSE-S3、KMS 可选、启用 EventBridge 通知、必须使用 TLS）
- 仅在使用 `selection=ATIME` 和属性记录时需要：VPC、子网、保存 ONTAP 凭据的密钥、管理端点、卷 UUID、`OntapVerifySsl`。FSx for ONTAP 管理端点的证书不是由公共 CA 签发，因此默认值为 `false`（不验证）。此时 ONTAP 凭据会通过不对对端进行认证的连接发送（路径在 VPC 内）。设为 `true` 时验证会失败，运行在选择阶段停止（在实机上观察到）。需要从 VPC 内的 Lambda 到 Secrets Manager 和 S3 的路径（VPC 端点或 NAT）
- 仅在处理超过 5 GiB 的文件时需要：放在 ECR 中的镜像。Access Point 是 Internet-origin，因此 Fargate 的子网需要 NAT 网关或公网 IP
- 已确认的通知订阅。SNS 的电子邮件订阅在收件人点击确认链接之前不会生效；没有确认，就没有人会看到批准请求
### 步骤
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # 替换所有 <PLACEHOLDER>
sam build && sam deploy
```
部署后，附加 Access Point 策略。该脚本根据堆栈输出中的角色 ARN 生成策略：只把 `s3:DeleteObject` 授予 `delete` 函数的角色，只把 `s3:PutObject` 授予恢复用的角色。
```bash
aws cloudformation describe-stacks --stack-name <stack> --query 'Stacks[0].Outputs' > outputs.json
python3 tools/render_access_point_policy.py --outputs outputs.json \
  --access-point-arn arn:aws:s3:<region>:<account>:accesspoint/<name> > ap-policy.json
aws s3control put-access-point-policy --account-id <account> --name <name> --policy file://ap-policy.json
aws sns list-subscriptions-by-topic --topic-arn <NotificationTopicArn> \
  --query 'Subscriptions[].SubscriptionArn'   # 不再有 PendingConfirmation
```
如果 Access Point 已有策略，这样做会替换它；请先合并已有的语句。
使用 Fargate 时，在仓库根目录构建镜像，push 到自己的 ECR 仓库，并指定给 `FargateImageUri`。
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
运行时，先用省略 `dryRun`（即为 `true`）的输入执行。
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20, "excludePatterns": ["*.vmdk"]}'
```
要执行到删除，请把 `"dryRun": false` 作为 JSON 布尔值传入，并在 `requestedBy` 中填写启动主体。字符串 `"false"` 会成为输入错误，不会执行删除。
## 目录结构
```
archive-verify-delete/
├── template.yaml                # SAM：存储桶、台账、9 个 Lambda、2 个状态机、Fargate（可选）、告警
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore,watchdog}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tools/render_access_point_policy.py
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
领域逻辑（校验和、输入检查、台账、恢复后的核对）位于 [`shared/archive_verify/`](../../../shared/archive_verify/)，在 `shared/tests/` 中测试。对 Access Point 的读写都经过 `shared/s3ap_helper.py`。
## 本地测试
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
为了确认删除判定被破坏时能够被检测到，用去掉 ETag 比较的桩代码把 `test_does_not_delete_when_etag_changed` 和 `test_does_not_delete_when_size_differs_but_etag_equal` 运行了 1 次，2 个测试都以 `assert 'DELETED' == 'CHANGED'` 失败。批准记录的检查和 50 GiB 的排除，是先写测试的：在实现之前，对更早的代码运行了 1 次，分别以 `assert 'DELETED' != 'DELETED'` 和 `KeyError: 'skippedTooLarge'` 失败。
## Success Metrics
### Outcome
把很少被读取的文件，经过核对和人的批准后转移到 S3 Glacier 系列的类别，降低卷的使用量。转移后的文件可以从台账中查找并恢复。
### Metrics
目标值由使用者决定。这里不给出数值。
| 类别 | 指标 | 定义 |
|---|---|---|
| Business Outcome | 释放的容量 | 运行前后卷已用空间的差值（在整理快照之后）。`bytesDeleted`（`-result.json`）是被删除文件的总大小，不是释放的空间：只要快照还在，卷的使用量就不会下降；对于压缩或去重的数据，释放的空间小于逻辑大小 |
| Business Outcome | 预期的每月存储节省额 | （移出容量池的 GB 数 × 价格差）−（归档类别的存储费用、每个对象的额外开销、取回费用）。价格见下文“费用估算” |
| Technical KPI | 核对一致率 | `VERIFIED` ÷（`VERIFIED` + `MISMATCH`） |
| Technical KPI | 未删除的件数 | `CHANGED`、`MISMATCH` 和 `FAILED` 的合计 |
| Technical KPI | 恢复核对一致率 | `RESTORE_VERIFIED` ÷（`RESTORE_VERIFIED` + `RESTORE_MISMATCH`） |
| Quality KPI | 未经批准而被删除的件数 | 必须为 0。统计 `approvedBy` 或 `approvedAt` 为空的 `DELETED` 条目 |
| Cost KPI | 每次运行的 Lambda、Fargate、DynamoDB、S3 请求、状态转换和归档类别的存储费用 | 根据用较小的 `maxFiles` 实测的 `dryRun=true` 运行，用“费用估算”中的公式估算 |
| Go / No-Go | 技术方面：在实际环境的运行中，所有已复制的文件都变为 `VERIFIED`，有意制造的 `CHANGED` 文件不会被删除，启动者的自我批准被拒绝，恢复后的文件为 `RESTORE_VERIFIED`。业务方面：预期的节省额超过运营成本（批准的工作量、处理恢复请求）；已确定恢复请求的入口和目标响应时间（包括该类别的恢复时间）；已通知用户 | 在全部满足之前，不要对生产卷使用 `dryRun=false`。请先确定每一项由谁决定（数据所有者、批准者、运营负责人） |

PoC 的规划和上生产前的确认，见 FSx for ONTAP Adoption Playbook 的[上生产前评审检查清单](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/04-build/checklists/pre-production-review.md)和[迁移前盘点](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/01-assess/checklists/inventory.md)（均为日文）。对本模式的 PoC，把 `maxFiles` 依次提高到 20、200、2,000，同时记录父执行的耗时、状态转换和 Fargate 秒数，就能得到每个文件的值。 PoC 规划表见 Playbook 的[在自己的环境中开始](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/domains/data-utilization/notes/archive-use-cases-and-integrations.md#自環境での始め方)（日文）。
### Measurement Method
Step Functions 的执行历史和日志（`/aws/vendedlogs/states/<stack>-archive` 和 `-restore`，不含执行数据）、`manifests/<runId>-result.json`、`manifests/<runId>-approval.json`、CloudWatch 的 EMF 指标（`FilesVerified`、`FilesDeleted`、`FilesMismatch`、`FilesChanged`、`FilesFailed`、`FilesStuckDeleting`、`BytesVerified`、`BytesDeleted`、`RestoreVerified`、`RestoreMismatch`、`ApprovalPendingHours`）、台账。

告警（全部发送到通知主题）：

| 告警 | 条件 |
|---|---|
| `ArchiveExecutionsFailedAlarm`、`RestoreExecutionsFailedAlarm` | 5 分钟内有 1 次以上失败、超时或中止的执行 |
| `ApprovalPendingAlarm` | 某个批准请求的等待时间超过 `ApprovalAlarmHours`（默认 24） |
| `FilesStuckDeletingAlarm` | 某次运行结束时仍有 `DELETING` 或 `APPROVED` 的条目 |
| `FilesMismatchAlarm` | 归档的副本不一致（`MISMATCH`） |
| `RestoreMismatchAlarm` | 恢复的文件与台账不一致 |
通知主题使用客户管理的 KMS 密钥加密。AWS 托管密钥（`alias/aws/sns`）的密钥策略无法编辑，而 EventBridge 和 CloudWatch 告警只有在客户管理的密钥允许服务主体使用 `kms:GenerateDataKey*` 和 `kms:Decrypt` 时，才能向加密的主题发布（[Amazon SNS key management](https://docs.aws.amazon.com/sns/latest/dg/sns-key-management.html)，2026-11-26 阅读）。第二次运行确认，EventBridge 的失败通知和告警通知都能送达。 [E-022]
## Performance Considerations
默认并行度依据下面的 1 次测量。其余是设计上的因素，未测量。
- 源文件会被读取 2 次。第 1 次是为计算哈希而通过 Access Point 读取，第 2 次是 `CopyObject` 在服务器端读取。会产生读取请求费用，位于容量池中的数据还会产生容量池的读取费用
- 并行度为 `MapConcurrency`（默认 1，归档和恢复相同）。在 1 次测量中，一个 Lambda 函数通过 Access Point 用 69.8 秒读取了 5.3 GB（约 4.94 GiB），单个流约 76 MB/s，约为本环境 128 MBps 吞吐量容量的 60%。2 个流约为 152 MB/s，超过该容量。每个文件会被读取 2 次，而且同一个卷还要服务用户，所以默认值为 1。并行读取未测量。调高之前，请在运行期间观察文件系统的 `DataReadBytes` 和客户端延迟
- `LargeFileThresholdBytes` 的默认值 5 GiB，来自单个请求 `CopyObject` 的上限。按上述速度，Lambda 的 15 分钟大约可覆盖 63 GiB，但这只是 1 个数据点
- 清单会把 `ListObjectsV2` 的全部结果载入一个 Lambda 的内存。超过数百万个对象时，请用 `prefix` 分开处理
- `selection=ATIME` 以深度优先遍历目录。扫描上限为 200,000 个条目（`ONTAP_SCAN_LIMIT`），超出时返回到中途为止的结果
- 恢复的等待时间由类别和 `tier` 决定。AWS 记载 S3 Glacier Deep Archive 在 Standard 下 12 小时以内，在 Bulk 下 48 小时以内。`RestoreMaxWaitHours` 的默认值为 72。对于等待时间长的类别，把 `RestorePollMinutes` 调大，可以减少轮询产生的状态转换
- Fargate 任务受 `FargateTimeoutSeconds`（默认 7200 秒）限制。每个 Task 都有 `TimeoutSeconds`，超时会重试
## 费用估算
没有测量账单。下面是用于估算的实测使用量和已公布的每个对象的条款。
两次运行中每个文件的状态转换（各运行 1 次）：

| 执行 | 每个文件的状态转换 | 来源 |
|---|---|---|
| 归档 dry run | 17（119 ÷ 7）、18（72 ÷ 4） | 包含 5.5 GiB 的 7 个文件的运行、确认排除与批准的运行 |
| 归档正式运行（含删除） | 18（127 ÷ 7）、19.5（78 ÷ 4） | 同上 |
| 恢复（`Expedited`；确认排除与批准的运行含核对） | 18（107 ÷ 6）、14（56 ÷ 4） | 同上 |
等待时间长的类别，每次轮询都会增加状态转换。
每个对象的存储条款（[Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare)，2026-11-26 阅读）：

| 类别 | 最短存储期限 | 每个对象的额外开销、最小计费大小 |
|---|---|---|
| S3 Glacier Instant Retrieval | 90 天 | 最小计费对象大小 128 KB |
| S3 Glacier Flexible Retrieval | 90 天 | 40 KB 元数据（32 KB 按该类别的价格，8 KB 按 S3 Standard 的价格） |
| S3 Glacier Deep Archive | 180 天 | 40 KB 元数据（拆分相同） |
公式：每月费用 ≈ 文件数 × 每个文件的状态转换 × 每次转换的价格 + Lambda 和 Fargate 的运行时间 × 价格 + 文件数 ×（`CopyObject`、`HeadObject`、`DeleteObject` 等的请求价格）+（数据 + 文件数 × 额外开销）× 类别价格 + 恢复时的取回费用。价格请按您的区域和日期，从 [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/) 和 [AWS Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) 获取；这里不写价格。
## Governance Note
> 本模式提供技术架构方面的指导。它不是法律、合规或监管方面的建议。请咨询合格的专业人士。
- 核对结果和批准是供人做最终判断的辅助信号。未使用 AI
- 本模式不满足保留期限和不可变性的要求。因为没有使用 Object Lock 等功能，所以有权限就可以删除
- 输出分类：台账和清单包含文件路径、大小、哈希、属性。路径中可能包含个人的姓名，或患者、案件的标识符，因此输出默认带有 `data_classification` 为 `RESTRICTED`（`shared/data_classification.py` 中的 "Restricted — Limited access"）。当数据本身的分类更严格时，请把 `DataClassification` 参数设为该分类。分类由您决定。文件内容会进入归档用存储桶，请按与原始数据相同的分类处理
- Human Review：每次运行都必须批准。没有基于置信度的自动批准。默认情况下，启动者和批准者是同一主体时，不会删除任何文件。这是对申报值的比较，不是主体的证明；事后的控制手段是 CloudTrail 的 `userIdentity`
- IAM：在 Access Point 上持有 `s3:DeleteObject` 的只有 `delete` 函数的角色；在那里持有 `s3:PutObject` 的只有恢复状态机和恢复用 Fargate 任务的角色。归档用的 Fargate 任务只负责复制，既不能删除也不能覆盖源文件。没有任何主体可以删除台账条目
- 审计：批准和删除会记录在台账（`approvedBy`、`approvedAt`、`requestedBy`、`deletedBy`、`deletedAt`）、`manifests/<runId>-approval.json`，以及 Step Functions 的执行历史和日志中。只有跟踪启用了 S3 数据事件时，CloudTrail 才会记录删除；本次运行未确认这一点
- 副本数量：没有第二份副本时，删除之后归档用存储桶中的对象就是唯一的副本。批准通知中会写明这一点
## 限制与未确认事项
- 从 Access Point 直接复制到其他区域的存储桶时返回了 `AccessDenied`（1 个 Access Point，1 次）。第二份副本仅以同一区域的存储桶为对象
- 在 UNIX 样式的卷上确认。大小和 mtime 都不变的内容变更，无法通过 ETag 和大小的确认检测到（参见“端到端运行中得知的行为”）。`chown` 是否会改变 ETag 尚未确认
- 属性是通过目录清单获取的。为了一个文件要读取整个父目录，因此对大目录会变慢
- 归档用存储桶的版本控制不是 Object Lock。版本会保留，但有权限就可以删除版本
- 超过 50 GiB 的文件默认不会被选择。若用 `allowOversize: true` 将其包含在内，则无法把它们恢复到 Access Point；请从存储桶下载
- `requestedBy` 和 `approver` 是自行申报的值。请用 IAM 和 CloudTrail 按主体确认职责分离
## 相关文档
- [Architecture (EN)](docs/architecture.en.md)
- [S3 Access Points 兼容性备忘](../../../docs/s3ap-compatibility-notes.md)
- [转移到归档类别的 9 种机制的比较](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)（日文）

---

<!-- playbook-reading:start -->
## 上生产前需要阅读的内容

部署后才会遇到的约束如何转化为设计决策，记录在 [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook)。同一内容放在两处时，停止更新的那份会比已修正的那份存留更久。

- [数据利用](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — 通过访问点访问数据的约束（所有模式通用）
- [数据保护](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-protection) — 该模式的决策集中之处
- [构建](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — 上生产前通读（所有模式通用）
<!-- playbook-reading:end -->
