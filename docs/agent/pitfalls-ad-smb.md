# AD / SMB の罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/pitfalls-ad-smb.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

| Pitfall | Solution |
|---------|----------|
| `SsmAssociations` + `aws:domainJoin` → schema error | Use separate `AWS::SSM::Association` resource with `AWS-JoinDirectoryServiceDomain` document (see below) |
| WINDOWS S3 AP `AccessDenied` on data-plane | `WindowsUser.Name` must be username only (`Admin`), NOT `DOMAIN\Admin` — domain prefix silently breaks data-plane |
| WINDOWS S3 AP creation fails | SVM must be AD-joined first; use `scripts/demo-ad-join-svm.sh` |
| AD-joined SVM + S3 AP data ops → `AccessDenied`（HeadBucket は成功する） | AD DC がすべてのデータ操作（ListObjectsV2 / GetObject / PutObject）で到達可能である必要がある。CIFS が有効な SVM では ONTAP がデータ操作ごとに `unix→win` の逆引き name-mapping を行うため。HeadBucket は S3 レイヤのメタデータのみを見るので成功する = **偽陽性**。IAM・AP ポリシー・ネットワークもすべて通るため、間違ったレイヤを調べに行きやすい。事前チェック: `GET /api/protocols/cifs/domains?svm.name=<svm>&fields=discovered_servers` で `discovered_servers == []` なら AD DC に到達できていない。プログラムからは `shared/ad_health_check.py` を使う |
| Existing SVM with stale AD → "SVM is already joined to a domain" | Cannot re-join via FSx API. Either unjoin via ONTAP CLI (`vserver cifs delete`) or create a new SVM with AD config |
| Re-join to a **different** domain fails with "unable to communicate with your Active Directory" even after `vserver cifs delete` | **The SVM's ONTAP-level DNS still points at the old domain's DCs.** `update-storage-virtual-machine` does not replace it. Patch it first: `PATCH /name-services/dns/{svm.uuid}` with the new domain and DC IPs, then re-join. Measured 2026-08-19: EMS showed `_ldap._tcp.dc._msdcs.<NEW.DOMAIN>` timing out against the *old* DNS servers |
| Restoring a recorded DNS config fails with "cannot be reached … Host is down" | ONTAP validates DNS reachability on write. To restore a recorded value whose servers are gone, use `PATCH /name-services/dns/{svm.uuid}?skip_config_validation=true` |
| AD join → `MISCONFIGURED`, EMS `Specifed OU '…' does not exist` | For **AWS Managed AD the intermediate OU is the directory's NetBIOS name**, not the domain label. `OU=Computers,OU=<NETBIOS>,DC=…` works; `OU=Computers,OU=<domain-label>,DC=…` does not |
| S3 AP creation → `FAILED`, "existing ONTAP object storage server on SVM" | The SVM runs a **native ONTAP S3 service** (its buckets appear as `fg_oss_*` FlexGroups). FSx for ONTAP S3 APs cannot coexist with it on the same SVM. Check `GET /protocols/s3/services?svm.name=<svm>` before creating; use a different SVM |
| Audit log shows `SubjectUserName: Not Present` on an AD-joined SVM | **Expected.** An AD join does not make it resolve — measured with a real domain account and a reachable DC. Only the SID remains; correlate with CloudTrail. `SubjectIP` is an AWS service address (6 requests → 5 distinct values). `EventID 4719` (management ops) *does* keep the real subject |
| robocopy で ACL 権限のないファイルがスキップされる | Backup Operators への追加だけでは不足。robocopy に `/B`（バックアップモード）が必要。コピー先は SVM の `BUILTIN\Backup Operators` にも追加（`SeRestorePrivilege` で差分上書き）。詳細は [smb-acl-migration-backup-operators.md](../smb-acl-migration-backup-operators.md) |

## SSM Domain Join — Correct Pattern for Windows EC2 AD Join

```yaml
# ❌ FAILS: EC2 SsmAssociations + aws:domainJoin (any schemaVersion)
# Error: "Document schema version, 2.2, is not supported by association
#         that is created with instance id"
WindowsInstance:
  SsmAssociations:
    - DocumentName: !Ref MyCustomDoc  # ← NEVER do this for AD join

# ✅ CORRECT: Separate AWS::SSM::Association resource
DomainJoinAssociation:
  Type: AWS::SSM::Association
  Properties:
    Name: AWS-JoinDirectoryServiceDomain  # AWS-managed document
    Targets:
      - Key: InstanceIds
        Values:
          - !Ref WindowsInstance
    Parameters:
      directoryId:
        - !Ref ManagedAd
      directoryName:
        - !Ref DomainName
      dnsIpAddresses:
        - !Select [0, !GetAtt ManagedAd.DnsIpAddresses]
        - !Select [1, !GetAtt ManagedAd.DnsIpAddresses]
```

EC2 IAM role requires: `AmazonSSMManagedInstanceCore` + `AmazonSSMDirectoryServiceAccess`.

## WINDOWS User Type S3 Access Point — AD Requirements

- SVM must be AD-joined before creating WINDOWS-type S3 AP (fails immediately if not)
- `WindowsUser.Name` = username only (`Admin`), NEVER `DOMAIN\Admin`
- Domain prefix is accepted at API level but causes `AccessDenied` on data-plane (ListObjects/GetObject/PutObject)
- Infrastructure template: `infrastructure/demo-ad-environment.yaml` (3 AD modes)
- Join script: `scripts/demo-ad-join-svm.sh` (auto-resolves from CFn stack outputs)
- Parameter file: `params/demo-ad-environment.example.json`
