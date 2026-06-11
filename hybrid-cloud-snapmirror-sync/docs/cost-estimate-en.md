# Cost Estimate

[日本語](cost-estimate-ja.md) | [English](cost-estimate-en.md)

Estimated costs for the demo environment (Tokyo region, based on published pricing as of June 2026).

> **Note**: Pricing may change. Refer to the official pricing page for each service for the latest rates.

---

## Amazon Quick Pricing

Amazon Quick offers 4 plans ([official pricing page](https://aws.amazon.com/quicksuite/pricing/)):

| Plan | Monthly | Features | AWS Account |
|------|---------|----------|-------------|
| **Free** | $0 | AI chat, research, Flows, app creation, external app integrations | Not required (sign up via email/SNS) |
| **Plus** | $20/user/month | Free + desktop app, shared spaces, org knowledge base sharing, browser extension | Not required |
| **Professional** | Contact sales | Plus + enterprise identity management, governance, Quick Sight BI | Required |
| **Enterprise** | $40/user/month | All features + advanced governance, audit, large-scale deployment | Required |

### Plan Required for Demo

To connect FSx ONTAP data to Amazon Quick via S3 Access Points, **Professional or higher** (AWS account integration, S3 data source connectivity) is required.

- Quick Sight (BI dashboard feature) included in Professional/Enterprise
- Quick Index (document search) can connect S3 data sources
- 30-day free trial available (Plus-level features)

### Quick Sight Standalone Pricing

Quick Sight as part of Amazon Quick also has the following pricing:

| Type | Monthly |
|------|---------|
| Reader (view only) | $3+/user/month (session-based pricing also available) |
| Author (create) | $24/user/month |
| Admin | $24/user/month |

※ Existing Quick Sight users on Enterprise plan can upgrade to full Quick features at no additional cost

---

## FSx for NetApp ONTAP Pricing

| Item | Unit Price (Tokyo region estimate) | Demo Config | Monthly Estimate |
|------|-----------------------------------|-------------|-----------------|
| SSD Storage | ~$0.120/GiB-month | 1,024 GiB | ~$123 |
| Throughput Capacity | ~$1.536/MBps-month (Single-AZ) | 128 MBps | ~$197 |
| SSD IOPS (above provisioned) | ~$0.036/IOPS-month | Included in base | $0 |
| Capacity Pool | ~$0.021/GiB-month | Not used | $0 |
| Backup | ~$0.025/GiB-month | Optional | - |

**FSx ONTAP monthly estimate: ~$320/month** (Single-AZ, 1TB, 128MBps)

> ※ For demo-only usage, costs are prorated by usage days (hourly billing)

---

## VPN Pricing (Site-to-Site VPN)

| Item | Unit Price | Monthly Estimate |
|------|-----------|-----------------|
| VPN Connection | ~$0.048/hour | ~$35/month |
| Data Transfer (OUT) | ~$0.114/GB | A few dollars at demo scale |

**VPN monthly estimate: ~$37/month**

---

## Overall Demo Cost Estimate

### Minimum Configuration (1-week demo period)

| Component | Estimate |
|-----------|----------|
| FSx for ONTAP (1 week) | ~$80 |
| VPN (1 week) | ~$9 |
| Amazon Quick (Professional, 1 user, trial) | $0 (30-day free trial) |
| Sync Server (runs on local PC) | $0 |
| **Total** | **~$89** |

### Full Configuration (1-month operation)

| Component | Monthly Estimate |
|-----------|-----------------|
| FSx for ONTAP | ~$320 |
| VPN | ~$37 |
| Amazon Quick (Professional, 2 users) | ~$80 (estimated) |
| Data Transfer | ~$5 |
| **Total** | **~$442/month** |

---

## Cost Optimization Tips

1. **Run FSx only during demo period**: Create/delete via CloudFormation
2. **Use Single-AZ**: ~50% cost reduction; HA not needed for demos
3. **Minimum throughput (128 MBps)**: Sufficient for demo data volumes
4. **Amazon Quick free trial**: Plus features free for 30 days
5. **VPN alternatives**: AWS Client VPN or WireGuard at event venues

---

## References

- [Amazon Quick Pricing](https://aws.amazon.com/quicksuite/pricing/)
- [Amazon Quick Sight Pricing](https://aws.amazon.com/quick/quicksight/pricing/)
- [FSx for NetApp ONTAP Pricing](https://aws.amazon.com/fsx/netapp-ontap/pricing/)
- [AWS VPN Pricing](https://aws.amazon.com/vpn/pricing/)
