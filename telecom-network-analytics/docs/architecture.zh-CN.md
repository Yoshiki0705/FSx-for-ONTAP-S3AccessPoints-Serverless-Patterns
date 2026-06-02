# UC18: 电信 / 网络分析 — CDR/网络日志异常检测与合规报告

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | 简体中文 | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## 端到端架构（输入 → 输出）

---

## 架构图

```mermaid
flowchart TB
    subgraph INPUT["📥 输入 — FSx for ONTAP"]
        DATA["电信数据<br/>.csv/.asn1/.parquet (CDR 文件)<br/>syslog / SNMP trap (网络设备日志)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ 触发器"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — 每日 00:00 UTC"]
    end

    subgraph SFN["⚙️ Step Functions 工作流"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 内执行<br/>• CDR/syslog 文件检测<br/>• 后缀过滤器应用<br/>• Manifest 生成"]
        CA["2️⃣ CDR Analyzer Lambda<br/>• 通过 S3 AP 获取 CDR<br/>• 通话元数据提取<br/>（主叫ID、被叫ID、通话时长、时间戳、基站ID）<br/>• Athena 流量统计查询<br/>（时段通话量、平均时长、峰值并发通话数）"]
        LA["3️⃣ Log Analyzer Lambda<br/>• Syslog RFC 5424 解析<br/>• SNMP trap 分析<br/>• 设备故障检测<br/>（link-down、硬件错误、进程崩溃）<br/>• 容量阈值超出检测（默认 80%）"]
        AD["4️⃣ Anomaly Detector Lambda<br/>• Bedrock InvokeModel<br/>• 7天滚动基线比较<br/>• 3σ阈值异常标记<br/>• 异常评分"]
        RL["5️⃣ Report Lambda<br/>• 每日网络健康摘要生成<br/>• 异常告警报告生成<br/>• S3 输出（reports/daily/{YYYY-MM-DD}/）<br/>• SNS 通知<br/>• CloudWatch EMF 指标"]
    end

    subgraph OUTPUT["📤 输出 — S3 存储桶"]
        CDROUT["reports/daily/{YYYY-MM-DD}/cdr-stats.json<br/>CDR 流量统计"]
        LOGOUT["reports/daily/{YYYY-MM-DD}/log-analysis.json<br/>设备故障分析结果"]
        ANOMOUT["reports/daily/{YYYY-MM-DD}/anomalies.json<br/>异常检测结果"]
        ERROUT["errors/cdr/{filename}.json<br/>CDR 解析错误记录"]
    end

    subgraph NOTIFY["📧 通知"]
        SNS["Amazon SNS<br/>电邮 / Slack<br/>（重大异常和设备故障告警）"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> CA
    DISC --> LA
    CA --> AD
    LA --> AD
    AD --> RL
    CA --> CDROUT
    LA --> LOGOUT
    AD --> ANOMOUT
    RL --> ERROUT
    RL --> SNS
```

---

## 关键设计决策

1. **CDR 和 syslog 并行处理** — CDR 分析和日志分析可以独立执行。通过 Step Functions Map State 并行化提升吞吐量
2. **通过 Athena 进行大规模 CDR 聚合** — 使用无服务器 SQL 高效聚合海量 CDR 记录
3. **7天滚动基线** — 考虑工作日特征的统计异常检测
4. **3σ阈值异常标记** — 仅检测统计显著的异常。最小化误报
5. **错误隔离** — CDR 解析失败记录在 `errors/cdr/` 下，不中断整个批次
6. **基于轮询** — S3 AP 不支持事件通知，因此使用 EventBridge Scheduler 每日执行

---

## 使用的 AWS 服务

| 服务 | 角色 |
|------|------|
| FSx for ONTAP | CDR/网络日志存储 |
| S3 Access Points | 对 ONTAP 卷的无服务器访问 |
| EventBridge Scheduler | 每日触发（00:00 UTC） |
| Step Functions | 工作流编排（并行 Map State） |
| Lambda | 计算（Discovery, CDR Analyzer, Log Analyzer, Anomaly Detector, Report） |
| Amazon Athena | CDR 流量统计 SQL 查询 |
| Amazon Bedrock | 异常检测推理（Claude / Nova） |
| SNS | 重大异常和设备故障告警通知 |
| Secrets Manager | ONTAP REST API 凭证管理 |
| CloudWatch + X-Ray | 可观测性（EMF 指标、链路追踪） |
