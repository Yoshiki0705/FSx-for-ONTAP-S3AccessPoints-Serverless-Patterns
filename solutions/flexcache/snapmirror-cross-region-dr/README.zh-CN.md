# SnapMirror Cross-Region DR + S3 Access Points 模式

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

一种灾难恢复模式，通过 SnapMirror Asynchronous 将经 S3 Access Points 收集的数据复制到跨区域目标，并在目标卷上自动挂载新的 S3 AP 实现自动故障转移。

正常运营期间，数据通过源卷上的 S3 AP 进行摄入。当 DR 事件发生时，Lambda 函数在约 3 分钟内编排故障转移：SnapMirror break → junction path → S3 AP 创建。

## 架构

```mermaid
graph TB
    subgraph "正常运营 (Region A)"
        WRITER[Writer Lambda]
        S3AP_SRC[S3 Access Point<br/>源]
        SRC_VOL[源卷<br/>vol_sm_dr_source]
    end
    subgraph "复制"
        SM[SnapMirror Async<br/>调度: 5分钟间隔]
    end
    subgraph "DR 故障转移 (Region B)"
        FAILOVER[Failover Lambda]
        S3AP_DST[S3 Access Point<br/>目标<br/>(故障转移时创建)]
        DST_VOL[目标卷 (DP)<br/>vol_sm_dr_dest]
        SNS[SNS 通知]
        CLIENT[应用程序<br/>(切换到新 S3 AP)]
    end

    WRITER -->|PutObject| S3AP_SRC
    S3AP_SRC --> SRC_VOL
    SRC_VOL -->|增量<br/>复制| SM
    SM --> DST_VOL
    FAILOVER -->|1. Break SM<br/>2. Set junction<br/>3. Create AP| DST_VOL
    FAILOVER --> S3AP_DST
    FAILOVER --> SNS
    SNS --> CLIENT
    CLIENT -->|S3 API| S3AP_DST
```

## 关键组件

| 组件 | 说明 |
|------|------|
| 源卷 + S3 AP | 数据摄入点 (Region A)。正常运营时使用 |
| SnapMirror Async | 卷级增量复制 (RPO = 调度间隔) |
| 目标卷 (DP) | 数据保护卷（break 前为只读）。通过 FSx API 创建 (SM-VAL-009) |
| Failover Lambda | 自动化: break → junction → S3 AP 创建。RTO ~3分钟 |
| SNS Topic | 故障转移后向应用程序通知新 S3 AP 端点 |

## RTO / RPO

| 指标 | 值 | 备注 |
|------|:---:|------|
| **RTO** | ~3分钟 | SnapMirror break（即时）+ junction 传播（~2分钟）+ S3 AP 创建（~30秒） |
| **RPO** | ≤ SnapMirror 调度 | 默认 5 分钟调度。最后一次传输后的数据可能丢失 |

## 前提条件

- 位于不同区域的 2 个 FSx for ONTAP 集群
- VPC Peering 及 Cluster/SVM Peering 已建立
- 通过 `aws fsx create-volume` 创建 DP 目标卷（仅 ONTAP REST API 不可 — SM-VAL-009）
- SnapMirror 关系已初始化且处于 `snapmirrored` 状态
- Secrets Manager 中的 fsxadmin 凭证（两个区域）
- Lambda 可通过 VPC 访问目标 ONTAP 管理 IP（端口 443）

## 部署

```bash
# 1. 部署堆栈（创建源卷、目标 DP 卷、Failover Lambda、SNS）
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-sm-dr \
  --parameter-overrides file://params.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 2. 创建源 S3 AP + SnapMirror 关系
#    （参见堆栈输出中的 PostDeployInstructions）

# 3. 测试故障转移（试运行）
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{"dry_run": true}' \
  /tmp/dr-dryrun.json
```

## 执行故障转移

```bash
# 触发 DR 故障转移
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{}' \
  /tmp/dr-result.json

# 检查结果
cat /tmp/dr-result.json
# → {"s3_access_point": {"arn": "...", "alias": "..."}, ...}
```

## 验证

```bash
# 故障转移后，从目标 S3 AP 读取
aws s3api list-objects-v2 \
  --bucket <dest-s3-ap-alias>

aws s3api get-object \
  --bucket <dest-s3-ap-alias> \
  --key test/sample.txt \
  /tmp/recovered.txt
```

## 技术约束

| 约束 | 详情 |
|------|------|
| 仅 SnapMirror Asynchronous | S3 NAS bucket 卷不支持 Synchronous 模式 |
| 不支持 SVM-DR | 包含 S3 NAS bucket 的 SVM 会阻止 SVM-DR。仅支持卷级 SnapMirror |
| 通过 FSx API 创建 DP 卷 | SM-VAL-009: 仅通过 ONTAP REST API 创建的卷对 FSx API 不可见，阻止 S3 AP |
| S3 AP 不随复制传输 | SM-002: S3 AP 是 AWS 层资源。目标需创建新 AP |
| 客户端应用程序更新 | 新 AP 具有不同的 ARN/alias。应用程序必须切换端点 |
| SnapMirror 调度 | FSx for ONTAP 最小间隔: 5分钟 |

## 清理（顺序关键 — SM-VAL-011）

```bash
# ⚠️ 严格按照顺序执行以防止孤立资源

# 1. 删除 SnapMirror 关系（从目标集群）
#    ONTAP REST: DELETE /api/snapmirror/relationships/<uuid>?destination_only=true
#    然后从源: snapmirror release (ONTAP CLI)

# 2. 删除 SVM Peers（两个集群）— 轮询两侧直到 num_records: 0

# 3. 删除 Cluster Peers（两个集群）

# 4. 删除 VPC Peering（仅在步骤 2 确认后）

# 5. 分离/删除 S3 Access Points（源和目标，如已创建）
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <src-arn>
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <dest-arn>

# 6. 删除 CloudFormation 堆栈
aws cloudformation delete-stack --stack-name fsxn-sm-dr
```

## 参考资料

- [NetApp Docs: S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp KB: SVM DR of S3 buckets](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)
- [AWS Docs: FSx for ONTAP SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)
- [AWS Docs: FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)
