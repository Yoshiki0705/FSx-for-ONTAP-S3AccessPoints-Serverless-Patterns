# archive-verify-delete: S3 API만으로 복사하고, 대조하고, 승인 후에 삭제하는 아카이브
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **문서**: [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## 개요
Amazon FSx for NetApp ONTAP(이하 FSx for ONTAP) 볼륨에 있는, 거의 읽지 않는 파일을 S3 Glacier 계열 스토리지 클래스로 옮기는 패턴입니다. 볼륨은 마운트하지 않습니다. 사용하는 것은 S3 Access Points의 S3 API뿐입니다.
파일 하나는 다음 순서로 진행되며, 도중에 조건이 어긋난 파일은 삭제 대상에서 제외됩니다.
1. 원장(DynamoDB 테이블)에 크기, ETag, SHA-256, CRC64NVME를 기록한다
2. 스토리지 클래스를 지정하여 `CopyObject`로 아카이브용 버킷에 복사한다
3. 버킷이 반환하는 체크섬을 원장의 값과 비교한다
4. 일치한 파일의 목록을 사람이 승인한다
5. Access Point의 ETag와 크기가 원장과 같은지 확인한 뒤, Access Point의 파일을 삭제한다

복원할 때는 원장에서 찾아 버킷에서 복원을 요청하고, 완료를 기다린 뒤 Access Point로 `CopyObject` 하여 되돌립니다.
이 패턴은 S3 Object Lock, S3 Glacier Vault Lock, AWS Backup Vault Lock, SnapLock, 스냅샷 잠금을 사용하지 않습니다. 템플릿에도 기재하지 않았습니다. 보존 기간은 설정하지 않으므로, 아카이브용 버킷의 오브젝트는 권한이 있으면 삭제할 수 있습니다.
이 패턴의 전제와 다른 방식과의 비교는 [아카이브용 클래스로 옮기는 8가지 방식의 비교](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)(일본어)에 있습니다.
## 측정한 것과 측정하지 않은 것
| 구분 | 내용 |
|---|---|
| 구성 요소를 실제 환경에서 1회씩 확인함(위 비교 자료에 기록, 2026-11-24 및 2026-11-26, ap-northeast-1, 1세대 `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, UNIX 스타일 볼륨, Access Point 사용자는 UNIX root) | `CopyObject`에 `ChecksumAlgorithm=SHA256`을 지정하면 버킷의 `ChecksumSHA256`이 `FULL_OBJECT`로 파일의 SHA-256과 일치했다(8 MiB까지). 5.5 GiB 멀티파트는 SHA-256이 `COMPOSITE`가 되었고, CRC64NVME는 `FULL_OBJECT`로 일치했다. 오래된 ETag의 `--copy-source-if-match`는 `PreconditionFailed`. Access Point의 `DeleteObject`는 `If-Match`를 지원하지 않는다. Step Functions SDK 통합에서 Access Point 별칭을 `Bucket`에 전달할 수 있었다 |
| 이 저장소에서 확인한 것 | moto를 사용한 단위 테스트와 스테이트 머신 및 IAM 구조의 테스트. AWS에는 연결하지 않았습니다. 위의 실기 통합 실행에서 발견한 결함 3건(ONTAP REST 함수의 호출 권한, TLS 검증, 복원 요청 중복 시의 오류 이름)은 재현하는 테스트를 추가하여 고쳤습니다 |
| 실기 통합 실행에서 1회씩 확인했다(2026-11-26, 위와 같은 환경, `selection=ATIME`, `GLACIER`, 파일 7개) | ONTAP REST API에 의한 `accessed_time` 선택과 uid, gid, mode, mtime, atime 취득(루트는 볼륨의 루트이며 경로 앞에 슬래시가 없음. `unix_permissions`는 정수 `640`으로 반환됨). Distributed Map의 `ItemReader`와 `ResultWriter`. Fargate에 의한 5.5 GiB 멀티파트 복사(`CopySourceIfMatch` 지정, CRC64NVME가 원장과 일치). Lambda에서의 5.3 GB(약 4.94 GiB) 해시 계산(69.8초, 메모리 2048 MB 설정, 사용 152 MB). 두 번째 복사. 승인 후의 삭제. 승인 대기 중에 NFS에서 덮어쓴 파일은 `CHANGED`가 되어 삭제되지 않았다. 승인을 거부하자 아무것도 삭제되지 않았다. `Expedited`에 의한 복원(5.5 GiB 포함)과 복원한 6개 파일의 SHA-256 일치(7개 중 남은 1개는 덮어쓴 파일로, 삭제도 복원도 되지 않았다). `reapply.sh`에 의한 uid, gid, mode, mtime의 복원 |
### 환경과 단계별 결과
환경은 ap-northeast-1, FSx for ONTAP 1세대 `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, UNIX 보안 스타일 볼륨이며, Access Point의 파일 시스템 사용자는 UNIX root입니다. 실행일은 2026-11-26(시각은 일본 표준시)이고 각 단계는 1회만 실행했습니다. 구성은 `selection=ATIME`, `GLACIER`, 두 번째 복사 있음, Fargate는 arm64의 2 vCPU와 8 GiB입니다. 데이터는 작은 파일 6개(64 B 3개, 8 MiB 3개. 소유자 1234:5678, 모드 640, mtime과 atime은 2020-01-02)와 5,905,580,032 B 파일 1개입니다.
| 단계 | 결과 | 소요 시간 |
|---|---|---|
| 1. 배포 | 성공. 다만 실행하면서 발견한 결함 2건을 고쳐 다시 배포했다 | 준비부터 배포까지 약 30분(16:19~16:50) |
| 2. dry run(`dryRun=true`) | 수정 후 성공. 7개 파일 모두 `VERIFIED`(SHA-256 일치 6, CRC64NVME 일치 1), 두 번째 복사도 `VERIFIED`. 삭제 0바이트이며 NFS에서는 7개 파일이 모두 남았다 | 244초(승인 대기 약 70초 포함) |
| 3. 승인 대기 중의 덮어쓰기 | NFS에서 파일 1개를 같은 크기로 4 KiB 덮어씀(mtime은 갱신). 승인 후 `CHANGED`(ETag 또는 크기 불일치)가 되어 삭제되지 않았다 | |
| 4. 실제 실행(`dryRun=false`)과 승인 | 6개 `DELETED`, 1개 `CHANGED`. `bytesDeleted`는 5,922,357,440. NFS에서는 6개가 사라지고 덮어쓴 1개만 남았다 | 310초(승인 요청까지 172초, 승인부터 완료까지 약 6초) |
| 5. 복원(`tier=Expedited`, `days=1`) | 6개 `RESTORED`(5.5 GiB 포함). SHA-256은 6개 모두 1단계 전에 NFS에서 기록한 값과 일치. `CHANGED`인 1개는 대상 외 | 287초(작은 파일 5개는 약 2.5분, 5.5 GiB의 Fargate 복사는 2분 38초) |
| 6. 승인 거부(`send-task-failure`) | 실행은 `REJECTED_OR_TIMED_OUT`으로 끝나고 3개 파일은 `VERIFIED` 그대로. `deletedBy`는 비어 있고 NFS에는 3개 모두 남았다 | 16초 |
| 추가: Lambda에서 5.3 GB(약 4.94 GiB) 해시 | `VERIFIED`(SHA-256이 NFS 값과 일치), 두 번째 복사도 `VERIFIED` | `record` 함수 69.8초(메모리 2048 MB 설정, 사용 152 MB) |
| 추가: 복원 요청의 중복 투입 | 두 번째는 HTTP 409 `RestoreAlreadyInProgress`. Step Functions의 SDK 통합은 `S3.S3Exception`으로 반환한다 | |
정리 시에는 모든 리소스를 삭제하고 다시 읽어 확인했습니다.
### 사용량(각 1회 실행, 청구액 아님)
| 실행 | 파일 수 | 소요 시간 | 상태 전이(부모 + 자식 Map 실행) | Fargate 태스크 |
|---|---|---|---|---|
| dry run | 7 | 244초 | 12 + 107 = 119 | 2회(해시와 복사 96초, 두 번째 복사 35초) |
| 실제 실행 | 7 | 310초 | 13 + 114 = 127 | 2회(94초, 35초) |
| 복원 | 6 | 287초 | 4 + 103 = 107 | 1회(156초) |
| 거부 | 3 | 16초 | 10 + 45 = 55 | 0회 |
- Lambda 실행 시간의 합계(CloudWatch. 실패한 실행을 포함하고 4.94 GiB 실행은 제외): `select` 13회 5.9초, `ontap_rest` 11회 13.4초(실패 2회), `record` 17회 11.7초, `ledger` 34회 9.1초, `approval` 6회 4.3초, `delete` 7회 5.6초, `summarize` 5회 5.1초, `restore` 26회 9.2초
- Fargate는 5개 태스크, 합계 약 416초(2 vCPU, 8 GiB, arm64). DynamoDB(온디맨드)는 읽기 68.5 RCU, 쓰기 74 WCU(전체 실행 합계)
- S3 요청 수는 측정하지 않았습니다(요청 메트릭을 활성화하지 않았습니다)
### 실기 통합 실행에서 발견해 고친 결함 3건
모두 재현하는 테스트를 추가하여 고쳤습니다.
| # | 증상 | 원인과 수정 |
|---|---|---|
| 1 | `selection=ATIME` 실행이 선택 단계에서 실패했다 | 아카이브 스테이트 머신의 역할에 ONTAP REST 함수에 대한 `lambda:InvokeFunction`이 없었다. 권한을 추가 |
| 2 | ONTAP REST 함수가 `CERTIFICATE_VERIFY_FAILED`로 실패했다 | 항상 TLS를 검증했지만, FSx for ONTAP 관리 엔드포인트의 인증서는 공인 CA의 서명이 아니다. 파라미터 `OntapVerifySsl`(기본값 `false`)을 추가 |
| 3 | 복원 요청의 중복 투입이 파일 실패가 되었다 | Step Functions의 SDK 통합이 `RestoreAlreadyInProgress`를 `S3.S3Exception`으로 반환하므로 `S3.RestoreAlreadyInProgressException`의 `Catch`와 일치하지 않았다. 진행 중인 복원을 완료 대기로 보내도록 수정 |
### 실기 통합 실행에서 알게 된 동작
결함으로 고치지 않은 동작입니다.
- `selection=ATIME`에서는 이 패턴 자신의 읽기가 `accessed_time`을 갱신합니다. `dryRun=true`로 한 번 돌리면 해시 계산을 위한 읽기로 파일의 atime이 실행 시각이 되어, 같은 입력으로 `dryRun=false`를 돌려도 선택되지 않습니다(0건으로 종료. dry run 직후에 실제 실행을 했을 때 확인). 즉 dry run을 하면 그 파일은 최근에 읽힌 것처럼 보입니다. dry run 직후에 같은 후보로 실제 실행을 하려면 `selection=MTIME`을 사용하세요(`LastModified`는 읽기로 바뀌지 않습니다)
- Access Point의 ETag는 내용이 아니라 mtime과 크기에 연동됩니다. 크기와 mtime이 같고 내용이 다른 파일 3개가 같은 ETag를 반환했습니다. 따라서 삭제 전의 ETag와 크기 확인으로는, 크기와 mtime을 바꾸지 않는 내용 변경을 검출할 수 없습니다. 크기는 같지만 mtime이 갱신된 덮어쓰기는 검출되었습니다(3단계)
- Access Point를 통해 마지막 파일을 삭제하면 비게 된 상위 디렉터리도 함께 사라집니다(`arc-e2e/large/`에서 확인). 복원의 `CopyObject`가 상위 디렉터리를 다시 만듭니다
- 복원된 파일의 소유자는 0:1, 모드는 644, 수정 시각은 복원한 시각이었습니다. NFS로 볼륨을 마운트한 호스트에서 생성된 `reapply.sh`를 root로 실행하면 원래의 uid, gid, mode, mtime(1234:5678, 640, 2020-01-02 03:04:05)으로 돌아왔고 내용의 SHA-256은 바뀌지 않았습니다
- 이 실행에서는 Access Point 정책에서 각 역할(`select`, `record`, `delete`, `restore` 함수의 역할, Fargate 태스크 역할, 두 스테이트 머신의 역할)을 허용했습니다
- 5.5 GiB의 `Expedited` 복원 요청이 접수되었고 약 4분 이내에 완료되었습니다
### 확인하지 않은 것
- 많은 수의 파일에서의 소요 시간과 요금
- `Standard`와 `Bulk` 복원의 완료 대기(실기에서는 `Expedited`만)
- `S3.SlowDownException`의 재시도(SDK 통합이 반환하는 이름을 관측하지 못했습니다. 결함 3과 같은 유형의 불일치가 생길 우려가 있습니다)
- CloudTrail 데이터 이벤트에서의 삭제 기록(계정의 트레일이 대상 Access Point의 데이터 이벤트를 포함하는지 확인하지 않았습니다)
- NTFS 볼륨, root 이외의 사용자, 2세대, Multi-AZ
- Access Point에 정책을 붙이지 않은 경우의 동작
- 복원에서 `CHANGED` 파일을 선택하지 않는 것 이외의 `EXISTS` 경로(NFS에 같은 이름의 파일이 있는 경우)
- 후보가 0건이 된 원인이 설명되지 않은 실행이 1건 있습니다. `touch -d`로 atime을 되돌린 약 10초 뒤의 실행은 후보가 0건이었습니다. 약 17분 뒤의 확인에서는 2020년 값이 반환되었고, `touch` 직후의 다른 확인에서도 6건이 반환되었습니다. 원인은 특정하지 못했고 재현도 하지 못했습니다
### 삭제 전 확인에 남는 쓰기 구간
삭제 전 확인에는 쓰기 구간이 하나 남습니다. Access Point의 `DeleteObject`는 조건부 삭제를 지원하지 않으므로, `HeadObject`로 확인한 뒤 삭제하기까지 사이에 덮어써도 검출되지 않습니다. 이 구간은 API 호출 1회 왕복 분량입니다.
## 처리 흐름
### 아카이브
입력에서 `olderThanDays`는 필수이며, `dryRun`의 기본값은 `true`입니다.
| 단계 | 처리 | 구현 |
|---|---|---|
| 1. 선택 | `MTIME`: Access Point `ListObjectsV2`의 `LastModified`. `ATIME`: ONTAP REST API의 `accessed_time`(VPC 내부 Lambda) | `select`, `ontap_rest` |
| 2. 기록 | 크기, ETag, SHA-256, CRC64NVME, 가져올 수 있으면 uid, gid, mode, mtime, atime을 원장에 기록. 5 GiB 이하는 Lambda, 초과분은 Fargate | `record`, Fargate 태스크 |
| 3. 복사 | 5 GiB 이하는 SDK 통합 `copyObject`(`SHA256`, 원장의 ETag를 `CopySourceIfMatch`에 지정). 초과분은 Fargate 멀티파트 복사(`CRC64NVME`) | Step Functions, Fargate |
| 4. 대조 | 버킷 `HeadObject`(`ChecksumMode=ENABLED`)의 크기와 체크섬을 원장과 비교한다. 일치하지 않으면 `MISMATCH`로 남기고 삭제 대상에서 제외한다 | `ledger` |
| 5. 두 번째 복사(선택) | Access Point에서 같은 리전의 다른 버킷으로 복사하고 같은 대조를 한다. 불일치하면 삭제 대상에서 제외한다 | Step Functions, `ledger` |
| 6. 승인 | 일치한 목록을 `manifests/<runId>.json`에 쓰고, SNS로 알리고, `waitForTaskToken`으로 기다린다 | `approval` |
| 7. 삭제 | `dryRun=false`일 때만. 파일마다 ETag와 크기를 확인하고, 같으면 `DeleteObject`. 다르면 `CHANGED`로 남긴다 | `delete` |
| 8. 기록 | `manifests/<runId>-result.json`과 EMF 메트릭(건수, 바이트 수) | `summarize` |
`dryRun=true`여도 6단계까지는 진행됩니다. 즉 복사는 수행되며, 아카이브용 클래스의 보관 요금(S3 Glacier Deep Archive에는 최소 보관 기간이 있습니다)이 발생합니다. 시험할 때는 `maxFiles`를 작게 하세요. 삭제는 수행되지 않습니다.
원장의 상태는 `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `DELETED`, `RESTORED` 순으로 진행되며, 중간 출구가 `CHANGED`, `MISMATCH`, `FAILED`입니다. 삭제할 수 있는 것은 `VERIFIED`(두 번째 복사를 필수로 한 경우에는 그 대조도 끝난 것)뿐입니다.
### 복원
입력은 `runId`와 `keys` 또는 `prefix` 중 하나입니다. `tier`(기본값 `Bulk`)와 `days`(기본값 7)를 지정할 수 있습니다.
1. 원장에서 `DELETED`인 파일을 선택한다
2. Access Point에 같은 키가 이미 있으면 `EXISTS`로 남기고 덮어쓰지 않는다
3. S3 Glacier Flexible Retrieval과 S3 Glacier Deep Archive의 오브젝트에는 `RestoreObject`를 요청한다(S3 Glacier Instant Retrieval은 불필요)
4. 완료 대기는 폴링입니다(`RestorePollMinutes`마다 `HeadObject`의 `Restore` 헤더를 읽고, `RestoreMaxWaitHours`에서 중단). EventBridge의 `Object Restore Completed`는 사용하지 않습니다. 버킷의 EventBridge 알림은 활성화되어 있으므로 나중에 전환할 수 있습니다
5. 버킷에서 Access Point로 `CopyObject`(5 GiB 초과는 Fargate)
6. 원장을 `RESTORED`로 하고, 속성 재설정용 스크립트 `manifests/<runId>-reapply.sh`를 쓴다

복원된 파일의 소유자는 0:1, 모드는 644, 수정 시각은 복원한 시각이었습니다(위 환경에서의 1회 확인). 원래 값은 `CopyObject`로는 복원되지 않습니다.
## 승인 조작
승인 알림에는 토큰을 포함하지 않습니다. 토큰은 AWS Systems Manager Parameter Store의 SecureString(`/<stack>/approvals/<runId>`)에 있습니다. 승인하는 사람은 그 파라미터를 읽을 권한과 `states:SendTaskSuccess` 권한을 가진 사람입니다.
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output '{"approved": true, "approver": "<your IAM principal ARN>"}'
# 거부:
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
`approver`는 자기 신고입니다. 입력한 값이 원장의 `deletedBy`에 들어가지만, 실제로 승인한 주체를 증명하는 것은 CloudTrail의 `SendTaskSuccess` 이벤트입니다. `approver`가 비어 있거나 `approved`가 `true`가 아니면 삭제는 수행되지 않습니다.
## 속성 재설정
복원의 마지막에 `manifests/<runId>-reapply.sh`가 작성됩니다. NFS로 볼륨을 마운트한 호스트에서 root로 실행합니다.
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
스크립트에는 `chown`, `chmod`, `touch -d`만 포함되며, 원장의 값은 엄격한 형식으로 검사하고, 키는 셸 인용으로 한 단어로 만듭니다. 형식에 맞지 않는 값은 주석이 되어 실행되지 않습니다. ONTAP REST API로 소유자, 그룹, 모드, 수정 시각을 설정할 수 있는지는 확인하지 않았으므로 이 경로는 구현하지 않았습니다.
## 배포
### 전제
- Access Point의 별칭과 ARN 모두(IAM에 두 형식이 모두 필요합니다. 별칭만 있는 정책은 배포할 수 있어도 실행 시 거부됩니다)
- 아카이브용 버킷의 이름(스택이 생성합니다. `DeletionPolicy: Retain`, Block Public Access, 기본 SSE-S3, KMS는 선택, EventBridge 알림 활성화, TLS 필수)
- `selection=ATIME`과 속성 기록을 사용할 때만: VPC, 서브넷, ONTAP 자격 증명을 담은 시크릿, 관리 엔드포인트, 볼륨 UUID, `OntapVerifySsl`. FSx for ONTAP 관리 엔드포인트의 인증서는 공인 CA의 서명이 아니므로 기본값은 `false`(검증하지 않음)이며, 이 경우 ONTAP 자격 증명은 상대를 인증하지 않는 연결로 전송됩니다(경로는 VPC 내부). `true`로 하면 인증서 오류로 선택 단계에서 멈췄습니다(관측). VPC 내 Lambda에서 Secrets Manager와 S3로 가는 경로(VPC 엔드포인트 또는 NAT)가 필요합니다
- 5 GiB를 초과하는 파일을 다룰 때만: ECR에 둔 이미지. Access Point가 인터넷 기점이므로 Fargate의 서브넷에는 NAT 또는 공인 IP가 필요합니다
### 절차
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # <PLACEHOLDER>를 바꾼다
sam build && sam deploy
```
Fargate를 사용하는 경우, 리포지토리 루트에서 이미지를 만들어 자신의 ECR 리포지토리에 push하고 `FargateImageUri`에 지정합니다.
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
실행은 먼저 `dryRun`을 생략한(즉 `true`인) 입력으로 합니다.
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20}'
```
삭제까지 하려면 `"dryRun": false`를 JSON 불리언으로 전달합니다. 문자열 `"false"`는 입력 오류이며 삭제되지 않습니다.
## 디렉터리 구성
```
archive-verify-delete/
├── template.yaml                # SAM: 버킷, 원장, Lambda 8개, 스테이트 머신 2개, Fargate(선택)
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
도메인 로직(체크섬, 입력 검사, 원장)은 [`shared/archive_verify/`](../../../shared/archive_verify/)에 있으며 `shared/tests/`에서 테스트합니다. Access Point에 대한 읽기와 쓰기는 `shared/s3ap_helper.py`를 거칩니다.
## 로컬 테스트
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
삭제 판정이 깨지면 감지되는지 확인하기 위해, ETag 비교를 제거한 스텁으로 `test_does_not_delete_when_etag_changed`와 `test_does_not_delete_when_size_differs_but_etag_equal`을 1회 실행했고, 2건 모두 `assert 'DELETED' == 'CHANGED'`로 실패했습니다. 원래대로 되돌리면 29건이 통과합니다.
## Success Metrics
### Outcome
거의 읽지 않는 파일을 대조와 사람의 승인을 거쳐 S3 Glacier 계열 클래스로 옮겨 볼륨 사용량을 낮춘다. 옮긴 파일은 원장에서 찾아 복원할 수 있다.
### Metrics
목표값은 이용자가 정합니다. 여기에는 수치를 두지 않습니다.
| 구분 | 지표 | 정의 |
|---|---|---|
| Business Outcome | 확보한 용량 | `bytesDeleted`(`-result.json`). 스냅샷이 남아 있는 동안은 볼륨 사용량이 줄지 않는다 |
| Technical KPI | 대조 일치율 | `VERIFIED` ÷ (`VERIFIED` + `MISMATCH`) |
| Technical KPI | 삭제하지 않은 건수 | `CHANGED`, `MISMATCH`, `FAILED`의 합계 |
| Quality KPI | 승인 없이 삭제된 건수 | 0이어야 한다. 원장의 `deletedBy`가 비어 있는 `DELETED`를 센다 |
| Cost KPI | 실행당 Lambda, Fargate, DynamoDB, S3 요청, 아카이브용 클래스의 보관 요금 | 측정하지 않음. `dryRun=true`와 작은 `maxFiles`로 먼저 견적한다 |
| Go / No-Go | 실제 환경의 엔드투엔드 실행에서, 복사한 모든 파일이 `VERIFIED`가 되고, 의도적으로 만든 `CHANGED`가 삭제되지 않으며, 복원한 파일의 SHA-256이 일치할 것 | 충족하기 전에는 운영 볼륨에 `dryRun=false`를 사용하지 않는다 |
### Measurement Method
Step Functions 실행 이력, `manifests/<runId>-result.json`, CloudWatch EMF 메트릭(`FilesVerified`, `FilesDeleted`, `FilesMismatch`, `FilesChanged`, `FilesFailed`, `BytesVerified`, `BytesDeleted`), 원장.
## Performance Considerations
측정하지 않았습니다. 다음은 설계상의 요인입니다.
- 원본 파일은 2회 읽힙니다. 1회째는 해시 계산을 위해 Access Point에서 읽고, 2회째는 `CopyObject`가 서버 측에서 읽습니다. 읽기 요청 요금이 발생하며, 용량 풀에 있는 데이터에는 용량 풀의 읽기 요금도 발생합니다
- 병렬도는 `MapConcurrency`(기본값 10)입니다. Access Point와 ONTAP의 부하에 맞춰 작게 시작하세요
- Lambda의 상한은 15분입니다. Access Point에서의 읽기 속도를 측정하지 못했으므로 `LargeFileThresholdBytes`의 기본값 5 GiB로 충분한지는 알 수 없습니다. 부족하면 낮추세요. Fargate가 맡는 분량이 늘어납니다
- 목록은 `ListObjectsV2`의 전체 결과를 Lambda 하나의 메모리에 올립니다. 수백만 건을 넘으면 `prefix`로 나누세요
- `selection=ATIME`은 디렉터리를 깊이 우선으로 탐색합니다. 탐색 상한은 200,000 엔트리(`ONTAP_SCAN_LIMIT`)이며, 넘으면 도중까지의 결과를 반환합니다
- 복원 대기 시간은 클래스와 `tier`로 정해집니다. S3 Glacier Deep Archive는 Standard에서 12시간 이내, Bulk에서 48시간 이내라고 AWS가 기재하고 있습니다. `RestoreMaxWaitHours`의 기본값은 72입니다
## Governance Note
> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법률, 컴플라이언스, 규제에 관한 조언이 아닙니다. 조직은 적격한 전문가와 상담하십시오.
- 대조 결과와 승인은 사람이 최종 판단을 하기 위한 보조 신호입니다. AI는 사용하지 않습니다
- 보존 기간과 불변성을 충족해야 하는 경우 이 패턴은 대응하지 않습니다. Object Lock 등을 사용하지 않으므로 권한이 있으면 삭제할 수 있습니다
- 출력 분류: 원장과 매니페스트에는 파일 경로, 크기, 해시, 속성이 들어갑니다(`dataClassification: operational-metadata`). 파일 내용은 아카이브용 버킷에 들어가므로 원본 데이터와 같은 분류로 취급하세요
- Human Review: 승인은 모든 실행에 필수입니다. 신뢰도에 의한 자동 승인은 없습니다
- IAM: `s3:DeleteObject`를 가진 것은 `delete` 함수의 역할뿐입니다. Fargate 태스크는 복사만 하며 삭제 권한이 없습니다. 원장 항목을 삭제할 권한은 누구에게도 부여하지 않았습니다
- 감사: 승인과 삭제는 원장(`deletedBy`, `deletedAt`), Step Functions 실행 이력, CloudTrail에 남습니다
## 제약과 미확인 사항
- Access Point에서 다른 리전의 버킷으로의 직접 복사는 `AccessDenied`였습니다(Access Point 1개, 1회). 두 번째 복사는 같은 리전의 버킷만 대상으로 합니다
- UNIX 스타일 볼륨에서의 확인입니다. 크기와 mtime을 바꾸지 않는 내용 변경은 ETag와 크기 확인으로 검출되지 않습니다(위의 "실기 통합 실행에서 알게 된 동작"). `chown`이 ETag를 바꾸는지는 확인하지 않았습니다
- 속성은 디렉터리 목록으로 가져옵니다. 파일 하나를 위해 부모 디렉터리 전체를 읽으므로, 큰 디렉터리에서는 느려집니다
- 아카이브용 버킷의 버저닝은 Object Lock이 아닙니다. 버전은 남지만 권한이 있으면 버전도 삭제할 수 있습니다
## 관련 문서
- [Architecture (EN)](docs/architecture.en.md)
- [S3 Access Points 호환성 메모](../../../docs/s3ap-compatibility-notes.md)
- [아카이브용 클래스로 옮기는 8가지 방식의 비교](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)(일본어)

---

<!-- playbook-reading:start -->
## 프로덕션 적용 전에 읽을 것

배포 후에 부딪히는 제약을 설계 판단으로 어떻게 옮기는지는 [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook)에 정리되어 있습니다. 같은 내용을 두 곳에 두면 갱신이 멈춘 쪽이 더 오래 남기 때문입니다.

- [데이터 활용](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — 액세스 포인트 경유의 제약 (모든 패턴 공통)
- [데이터 보호](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-protection) — 이 패턴에서 판단이 집중되는 곳
- [구축](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — 프로덕션 전에 확인 (모든 패턴 공통)
<!-- playbook-reading:end -->
