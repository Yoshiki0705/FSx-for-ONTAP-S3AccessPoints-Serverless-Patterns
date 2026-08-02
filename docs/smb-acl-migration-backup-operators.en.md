# Windows File Server Migration: ACL-Preserving Copy via Backup Operators

> 🌐 Language: [日本語](./smb-acl-migration-backup-operators.md) | **English**

When migrating from an existing Windows file server to Amazon FSx for NetApp ONTAP (SMB / NTFS
security style), the hard part is handling **files the copy account itself has no NTFS ACL rights to**.

This document records the behaviour that was raised with AWS Support and **confirmed in their reply**.

## The underlying problem

A Windows file server will typically contain files and folders that the administrator account is not
granted read access to in the NTFS ACL, even when that account is a member of Domain Admins. Home
directories still owned by individual accounts, and department-specific restricted folders, are the
usual examples.

If ACLs must be preserved, a plain robocopy run skips those files with access denied. Differential
runs hit the mirror-image problem: no write permission on the existing files at the destination.

## Confirmed behaviour

AWS Support confirmed all three points below as correct.

| Scope | Mechanism | Confirmed behaviour |
|-------|-----------|--------------------|
| Source (Windows) | Backup Operators + `SeBackupPrivilege` | robocopy `/B` (backup mode) reads files including their ACLs even without ACL read rights |
| Destination (FSx for ONTAP) | `BUILTIN\Backup Operators` + `SeRestorePrivilege` | Differential runs can overwrite (restore) files including ACLs without ACL write rights |
| AWS DataSync | Membership in both | With the service account in the source Backup Operators and in `BUILTIN\Backup Operators` on the FSx for ONTAP SVM, initial and differential copies behave the same way |

### Why it works

`SeBackupPrivilege` and `SeRestorePrivilege` are Windows privileges that **bypass** NTFS ACL
evaluation. They exist so that backup software can read and write every file.

On the ONTAP side, the `BUILTIN\Backup Operators` group already holds both privileges **by default**
([NetApp: assigning SMB privileges](https://docs.netapp.com/us-en/ontap/smb-admin/assign-privileges-concept.html)),
so adding the copy account to that group on the SVM is all that is required.

The important detail is that robocopy `/B` **does not use the privilege unless explicitly requested**.
Group membership alone is not enough; the `/B` flag is required.

## Migration setup

```
Windows file server                        FSx for ONTAP
(source)                                   (destination / NTFS security style)
  │                                          │
  │ copy account:                            │ same account added to
  │   Domain Admins                          │   BUILTIN\Backup Operators on the SVM
  │   + Backup Operators ← SeBackupPrivilege │   ← SeRestorePrivilege
  │                                          │
  └──── robocopy /B /COPY:DATSOU /MIR ──────▶│
        or AWS DataSync                      │  SVM is joined to the AD domain
```

### Configuration steps

**1. Source**: add the copy account to the local or domain Backup Operators group.

**2. FSx for ONTAP**: add the same account to `BUILTIN\Backup Operators` on the SVM.

```
vserver cifs users-and-groups local-group add-members \
  -vserver <svm-name> \
  -group-name "BUILTIN\Backup Operators" \
  -member-names <DOMAIN>\<user>
```

**3. Run the copy**: with robocopy, always pass `/B`.

```
robocopy <source> <dest> /B /COPY:DATSOU /MIR /R:1 /W:1 /LOG+:migrate.log
```

The `/COPY:DATSOU` flags mean Data, Attributes, Timestamps, Security (NTFS ACL), Owner, and aUditing
information. `S` and `O` are the ones that matter for preserving ACLs and ownership.

## Operational notes

> **Privilege handling note**: because `SeBackupPrivilege` and `SeRestorePrivilege` bypass ACL
> evaluation, grant them only for the migration window and remove them promptly after cutover.
> Leaving them in place permanently leaves an account for which ACL-based separation is effectively
> disabled.

> **Auditing note**: including `U` (aUditing information) in `/COPY` also replicates SACLs. Where
> auditing requirements apply, verify after migration that SACLs carried over as intended.

> **Security style note**: this procedure assumes NTFS security style volumes. UNIX and MIXED
> security styles handle ACLs differently, so also review the identity discussion in the
> [ONTAP integration notes](./ontap-integration-notes.en.md).

> **Scope of verification note**: the three points above were confirmed by AWS Support, but this
> project has not run an end-to-end measurement on real hardware. Before a production migration,
> pilot the copy against a subset of the data and confirm that ACLs and ownership are preserved as
> expected.

## References

- [NetApp ONTAP: assigning SMB privileges](https://docs.netapp.com/us-en/ontap/smb-admin/assign-privileges-concept.html) — default privileges of `BUILTIN\Backup Operators`
- [AWS: FSx for ONTAP SMB file shares](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/smb-config.html)
- [Microsoft: Backup Operators group](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-security-groups#backup-operators)
- [Microsoft: robocopy](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/robocopy)

## Related documents

- [ONTAP integration notes](./ontap-integration-notes.en.md) — NAS coexistence, identity, data protection
- [S3 AP prerequisites on AD-joined SVMs](./en/ad-joined-svm-s3ap-prerequisites.md) — considerations specific to AD-joined SVMs
