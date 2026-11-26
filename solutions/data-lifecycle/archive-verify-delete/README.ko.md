# archive-verify-delete: S3 API만으로 복사하고, 대조하고, 승인 후에 삭제하는 아카이브
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **문서**: [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## 개요
Amazon FSx for NetApp ONTAP(이하 FSx for ONTAP) 볼륨에 있는, 거의 읽지 않는 파일을 S3 Glacier 계열 스토리지 클래스로 옮기는 패턴입니다. 파일의 읽기, 쓰기, 삭제에는 S3 Access Points의 S3 API를 사용하며 NFS 마운트는 사용하지 않습니다. 다만 두 가지에는 추가 요소가 필요합니다. 마지막 액세스 시각으로 선택하는 것(`selection=ATIME`)과 속성의 취득에는 ONTAP REST API(VPC 내부의 Lambda 함수, ONTAP 자격 증명, 관리 엔드포인트)를 사용하고, 복원 후에 소유자, 모드, 수정 시각을 되돌리려면 NFS로 볼륨을 마운트한 호스트가 필요합니다.
파일 하나는 다음 순서로 진행되며, 도중에 조건이 어긋난 파일은 삭제 대상에서 제외됩니다.
1. 원장(DynamoDB 테이블)에 크기, ETag, SHA-256, CRC64NVME를 기록한다
2. 스토리지 클래스를 지정하여 `CopyObject`로 아카이브용 버킷에 복사한다(키는 `<prefix><runId>/<원래 키>`)
3. 버킷이 반환하는 체크섬을 원장의 값과 비교한다
4. 일치한 파일의 목록을 사람이 승인한다. 승인은 원장에 `APPROVED`로 기록되며, 승인자가 실행을 시작한 주체와 같으면 거부된다(기본값)
5. 원장에서 `APPROVED`인 파일만, Access Point의 ETag와 크기가 원장과 같은지 확인한 뒤 삭제한다

복원할 때는 원장에서 파일을 찾아 버킷에서 복원을 요청하고, 완료를 기다린 뒤 Access Point로 `CopyObject` 하여 되돌립니다. 그 후 복원된 파일을 다시 읽어 원장의 SHA-256 및 CRC64NVME와 비교합니다.
이 패턴은 S3 Object Lock, S3 Glacier Vault Lock, AWS Backup Vault Lock, SnapLock, 스냅샷 잠금을 사용하지 않습니다. 템플릿에도 기재하지 않았습니다. 보존 기간은 설정하지 않으므로, 아카이브용 버킷의 오브젝트는 권한이 있으면 누구나 삭제할 수 있습니다.
이 패턴의 전제와 다른 방식과의 비교는 [Comparing 8 kinds of mechanisms for moving files to archive classes](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/reference/comparison/archive-tiering-library-options.md)(영어)에 있습니다.
## 측정한 것과 측정하지 않은 것
| 구분 | 내용 |
|---|---|
| 구성 요소를 실제 환경에서 1회씩 확인함(위 비교 자료에 기록, 2026-11-24 및 2026-11-26, ap-northeast-1, 1세대 `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, UNIX 스타일 볼륨, Access Point 사용자는 UNIX root) | `CopyObject`에 `ChecksumAlgorithm=SHA256`을 지정하면 버킷의 `ChecksumSHA256`이 `FULL_OBJECT`로 파일의 SHA-256과 일치했다(8 MiB까지). 5.5 GiB 멀티파트는 SHA-256이 `COMPOSITE`가 되었고, CRC64NVME는 `FULL_OBJECT`로 일치했다. 오래된 ETag의 `--copy-source-if-match`는 `PreconditionFailed`. Access Point의 `DeleteObject`는 `If-Match`를 지원하지 않는다. Step Functions SDK 통합에서 Access Point 별칭을 `Bucket`에 전달할 수 있었다 |
| 이 저장소에서 확인한 것 | moto를 사용한 단위 테스트와 스테이트 머신 및 IAM 구조의 테스트. AWS에는 연결하지 않았습니다. 위의 실기 통합 실행에서 발견한 결함 6건(ONTAP REST 함수의 호출 권한, TLS 검증, 복원 요청 중복 시의 오류 이름, 스테이트 머신의 로그 출력 권한, `HeadObject`의 403, 알람의 게시 권한)은 재현하는 테스트를 추가하여 고쳤습니다 |
| 실기 통합 실행에서 1회씩 확인했다(2026-11-26, 위와 같은 환경, `selection=ATIME`, `GLACIER`, 파일 7개) | ONTAP REST API에 의한 `accessed_time` 선택과 uid, gid, mode, mtime, atime 취득(루트는 볼륨의 루트이며 경로 앞에 슬래시가 없음. `unix_permissions`는 정수 `640`으로 반환됨). Distributed Map의 `ItemReader`와 `ResultWriter`. Fargate에 의한 5.5 GiB 멀티파트 복사(`CopySourceIfMatch` 지정, CRC64NVME가 원장과 일치). Lambda에서의 5.3 GB(약 4.94 GiB) 해시 계산(69.8초, 메모리 2048 MB 설정, 사용 152 MB). 두 번째 복사. 승인 후의 삭제. 승인 대기 중에 NFS에서 덮어쓴 파일은 `CHANGED`가 되어 삭제되지 않았다. 승인을 거부하자 아무것도 삭제되지 않았다. `Expedited`에 의한 복원(5.5 GiB 포함)과 복원한 6개 파일의 SHA-256 일치(7개 중 남은 1개는 덮어쓴 파일로, 삭제도 복원도 되지 않았다). `reapply.sh`에 의한 uid, gid, mode, mtime의 복원 |
| 두 번째 엔드투엔드 실행에서 1회씩 확인함(2026-11-26, 같은 환경, `GLACIER`, 두 번째 복사 있음. `selection=ATIME`으로 dry run, `selection=MTIME`과 ONTAP REST에서 가져온 속성으로 실제 실행. 64 B에서 1 MiB까지의 파일과 51 GiB 스파스 파일 1개) | 검토 후에 동작이 바뀌었다. `maxFiles=50`일 때 64 B 파일 3개와 131,071 B 파일 1개는 최소 크기 미만이어서 제외되었고, 131,073 B 파일은 남았다. `*.vmdk`와 법적 보존용 prefix는 제외되었다. 51 GiB 스파스 파일은 `SKIPPED_TOO_LARGE`로 기록되고 복사되지 않았다. 이미 사용한 `runId`와 `requestedBy`가 없는 실제 실행 입력은 입력 오류로 멈췄다. 시작한 주체와 같은 ARN의 승인은 `APPROVAL_REFUSED`로 끝났고 아무것도 삭제되지 않았다. 승인 없이 `delete` 함수를 직접 호출하면 `NOT_APPROVED`를 반환하고 아무것도 삭제하지 않았다. 다른 승인자로 파일 3개가 삭제되었고, 승인 대기 중에 덮어쓴 1개는 `CHANGED`로 남았다. 중단을 모의하기 위해 `DELETING`으로 만든 항목은, 같은 실행의 재시도에서 `DELETED`(`already gone on retry`)로 기록되었고, 다른 실행은 거부되었으며, `reconcile`이 `DELETED`로 기록했다. 복원 후 3개 파일이 `RESTORE_VERIFIED`가 되었다. 알람이 KMS로 암호화된 토픽에 게시되었다(수정 후) |
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
두 번째 실행(2026-11-26, 작은 파일, 두 번째 복사 있음, `MapConcurrency=2`)의 상태 전이입니다. 각 1회 실행이며 파일 크기와 경로에 따라 달라집니다.

| 실행 | 파일 수 | 소요 시간 | 상태 전이(부모 + 자식 Map 실행) | 파일당 |
|---|---|---|---|---|
| dry run `e2e2-dry1` | 4 | 66초(승인 대기 약 20초 포함) | 12 + 60 = 72 | 18 |
| 실제 실행 `e2e2-real2`(3개 삭제, 1개 `CHANGED`) | 4 | 45초(승인 대기 포함) | 14 + 64 = 78 | 19.5 |
| 복원 `e2e2-rest2`(Expedited, 검증 포함, 1개 `EXISTS`) | 4 | 192초 | 4 + 52 = 56 | 14 |
### 엔드투엔드 실행에서 발견해 고친 결함
모두 재현하는 테스트를 추가하여 고쳤습니다.
| # | 증상 | 원인과 수정 |
|---|---|---|
| 1 | `selection=ATIME` 실행이 선택 단계에서 실패했다 | 아카이브 스테이트 머신의 역할에 ONTAP REST 함수에 대한 `lambda:InvokeFunction`이 없었다. 권한을 추가 |
| 2 | ONTAP REST 함수가 `CERTIFICATE_VERIFY_FAILED`로 실패했다 | 항상 TLS를 검증했지만, FSx for ONTAP 관리 엔드포인트의 인증서는 공인 CA의 서명이 아니다. 파라미터 `OntapVerifySsl`(기본값 `false`)을 추가 |
| 3 | 복원 요청의 중복 투입이 파일 실패가 되었다 | Step Functions의 SDK 통합이 `RestoreAlreadyInProgress`를 `S3.S3Exception`으로 반환하므로 `S3.RestoreAlreadyInProgressException`의 `Catch`와 일치하지 않았다. 진행 중인 복원을 완료 대기로 보내도록 수정 |
두 번째 실행(2026-11-26)에서 3건을 더 발견해 고쳤습니다.

| # | 증상 | 원인과 수정 |
|---|---|---|
| 4 | 배포가 `The state machine IAM Role is not authorized to access the Log Destination`로 실패했다 | 스테이트 머신의 역할에 실행 로그에 필요한 `logs:CreateLogDelivery`와 관련 권한이 없었다. 권한을 추가 |
| 5 | 삭제 재시도와 `reconcile`에서, 삭제된 파일에 대한 `HeadObject`가 403을 받았다 | `s3:ListBucket` 권한이 없는 호출자는 존재하지 않는 키에 대한 `HeadObject`에서 404가 아니라 403을 받는다. `delete`와 `restore` 함수에 `s3:ListBucket`을 IAM과 Access Point 정책 양쪽에 추가 |
| 6 | CloudWatch 알람의 알림이 `CloudWatch Alarms is not authorized to perform: SNS:Publish`로 실패했다 | 키 정책은 CloudWatch를 허용했지만 토픽 정책은 EventBridge만 허용했다. `cloudwatch.amazonaws.com`의 스테이트먼트를 추가 |
### 실기 통합 실행에서 알게 된 동작
결함으로 고치지 않은 동작입니다.
- `selection=ATIME`에서는 이 패턴 자신의 읽기가 `accessed_time`을 갱신합니다. `dryRun=true`로 한 번 돌리면 해시 계산을 위한 읽기로 파일의 atime이 실행 시각이 되어, 같은 입력으로 `dryRun=false`를 돌려도 아무것도 선택되지 않습니다(dry run 직후에 실제 실행을 했을 때 0건으로 종료). dry run 직후에 같은 후보로 실제 실행을 하려면 `selection=MTIME`을 사용하세요(`LastModified`는 읽기로 바뀌지 않습니다)
- ETag에 대해, 공식 기재와 이 환경에서의 측정은 다음과 같습니다. 공식 페이지([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html), 2026-11-26 열람)에는 "The ETag reflects changes only to the contents of an object, not its metadata"라고 되어 있습니다. 이 환경에서의 1회 측정에서는 크기와 mtime이 같고 내용이 다른 파일 3개가 같은 ETag를 반환했습니다. 따라서 이 패턴은 삭제 전의 ETag와 크기 확인으로는, 크기와 mtime을 바꾸지 않는 내용 변경을 검출할 수 없는 것으로 취급합니다. 크기는 같지만 mtime이 갱신된 덮어쓰기는 승인 대기 중에 검출되었습니다(첫 번째 실행의 3단계와 두 번째 실제 실행)
- Access Point를 통해 디렉터리의 마지막 파일을 삭제하면 비게 된 상위 디렉터리도 함께 사라집니다(`arc-e2e/large/`에서 확인). 복원의 `CopyObject`가 상위 디렉터리를 다시 만듭니다
- 복원된 파일의 소유자는 0:1, 모드는 644, 수정 시각은 복원한 시각이었습니다. NFS로 볼륨을 마운트한 호스트에서 생성된 `reapply.sh`를 root로 실행하면 원래의 uid, gid, mode, mtime(1234:5678, 640, 2020-01-02 03:04:05)으로 돌아왔고 내용의 SHA-256은 바뀌지 않았습니다
- 복원 스테이트 머신은, 아카이브용 버킷에 사본이 있으면 `CHANGED`로 남은 파일도 선택합니다. Access Point에 같은 키가 이미 있으면 `EXISTS`로 남기고 덮어쓰지 않습니다(두 번째 복원에서 1회 확인)
- 5.5 GiB 파일의 `Expedited` 복원 요청이 접수되었고 약 4분 이내에 완료되었습니다
### 확인하지 않은 것
- 많은 수의 파일에서의 소요 시간과 요금. 다른 병렬도에서의 파일 시스템 처리량과 클라이언트 지연
- `Standard`와 `Bulk` 복원의 완료 대기(실기에서는 `Expedited`만)
- `S3.SlowDownException`의 재시도(SDK 통합이 반환하는 이름을 관측하지 못했습니다. 결함 3과 같은 유형의 불일치가 생길 우려가 있습니다)
- CloudTrail 데이터 이벤트에서의 삭제와 승인 기록. S3 데이터 이벤트(`DeleteObject` 등)는 트레일에서 데이터 이벤트를 활성화한 경우에만 기록됩니다. 이 실행에서는 계정의 트레일이 대상 Access Point의 데이터 이벤트를 포함하는지 확인하지 않았습니다. `SendTaskSuccess`는 관리 이벤트이며, 그 기록도 확인하지 않았습니다
- 승인의 거부와 수락은, 같은 SSO 주체가 승인 출력에서 서로 다른 ARN을 신고하는 방식으로 비교했습니다. approver 값은 신고된 값이므로 다른 IAM 주체여도 같은 결과가 되리라고 생각하지만, 실제의 두 번째 주체는 사용하지 않았습니다
- 50 GiB를 넘는 파일의 복사와 복원(스파스 파일로 선택에서 제외되는 것만 확인)
- NTFS 볼륨, root 이외의 사용자, 2세대, Multi-AZ
- 복원에서 `CHANGED` 파일을 선택하지 않는 것 이외의 `EXISTS` 경로(NFS에 같은 이름의 파일이 있는 경우)
- `ApprovalPendingAlarm`이 실제로 `ALARM`이 될 때까지의 대기(메트릭이 게시되는 것만 확인)
- 후보가 0건이 된 원인이 설명되지 않은 실행이 1건 있습니다. `touch -d`로 atime을 되돌린 약 10초 뒤의 실행은 후보가 0건이었습니다. 약 17분 뒤의 확인에서는 2020년 값이 반환되었고, 다른 확인에서도 6건이 반환되었습니다. 원인은 특정하지 못했고 재현도 하지 못했습니다
### 삭제 전 확인에 남는 쓰기 구간
삭제 전 확인에는 쓰기 구간이 하나 남습니다. Access Point의 `DeleteObject`는 조건부 삭제를 지원하지 않으므로, `HeadObject`로 확인한 뒤 삭제하기까지 사이에 덮어써도 검출되지 않습니다. 이 구간은 API 호출 1회 왕복 분량입니다.
## 처리 흐름
### 아카이브
입력에서 `olderThanDays`는 필수이며, `dryRun`의 기본값은 `true`입니다. `RequireSeparateApprover=true`(기본값)일 때 `dryRun=false` 실행에는 `requestedBy`에 시작한 주체의 ARN이 필요합니다.
| 단계 | 처리 | 구현 |
|---|---|---|
| 1. 선택 | `MTIME`: Access Point `ListObjectsV2`의 `LastModified`. `ATIME`: ONTAP REST API의 `accessed_time`(VPC 내부 Lambda). 제외 조건을 적용한다(아래 표) | `select`, `ontap_rest` |
| 2. 기록 | 크기, ETag, SHA-256, CRC64NVME, 가져올 수 있으면 uid, gid, mode, mtime, atime을 원장에 기록. 5 GiB 이하는 Lambda, 초과분은 Fargate | `record`, Fargate 태스크 |
| 3. 복사 | 5 GiB 이하는 SDK 통합 `copyObject`(`SHA256`, 원장의 ETag를 `CopySourceIfMatch`에 지정). 초과분은 Fargate 멀티파트 복사(`CRC64NVME`) | Step Functions, Fargate |
| 4. 대조 | 버킷 `HeadObject`(`ChecksumMode=ENABLED`)의 크기와 체크섬을 원장과 비교한다. 일치하지 않으면 `MISMATCH`로 남기고 삭제 대상에서 제외한다 | `ledger` |
| 5. 두 번째 복사(선택) | Access Point에서 같은 리전의 다른 버킷으로 복사하고 같은 대조를 한다. 불일치하면 삭제 대상에서 제외한다 | Step Functions, `ledger` |
| 6. 승인 요청 | 일치한 목록을 `manifests/<runId>.json`에 쓰고, SNS로 알리고, `waitForTaskToken`으로 기다린다. 사본이 하나뿐인 경우와 복원할 수 없는 파일이 있는 경우에는 알림에 그 내용이 기재된다 | `approval` |
| 7. 승인 기록 | `dryRun=false`일 때만. 승인자가 시작한 주체와 같으면 거부한다. 그렇지 않으면 목록의 각 파일을 원장에서 `VERIFIED`에서 `APPROVED`로 옮기고 `manifests/<runId>-approval.json`을 쓴다 | `approval` |
| 8. 삭제 | 원장에서 `APPROVED`인 파일만. 파일마다 ETag와 크기를 확인하고, 같으면 `DeleteObject`. 다르면 `CHANGED`로 남긴다 | `delete` |
| 9. 기록 | `manifests/<runId>-result.json`과 EMF 메트릭(건수, 바이트 수, 제외 건수). `DELETING` 또는 `APPROVED` 항목이 남아 있으면 `COMPLETED_WITH_ERRORS` | `summarize` |
`dryRun=true`여도 6단계까지는 진행됩니다. 즉 복사는 수행되며, 아카이브용 클래스의 보관 요금(최소 보관 기간이 있습니다)이 발생합니다. 시험할 때는 `maxFiles`를 작게 하세요. 삭제는 수행되지 않습니다.
원장의 상태는 `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `APPROVED`, `DELETING`, `DELETED`, `RESTORED`, `RESTORE_VERIFIED` 순으로 진행되며, 중간 출구가 `CHANGED`, `MISMATCH`, `FAILED`, `SKIPPED_TOO_LARGE`, `RESTORE_MISMATCH`입니다. 삭제할 수 있는 것은 `APPROVED`인 파일(두 번째 복사를 필수로 한 경우에는 그 대조도 끝난 것)뿐입니다.

이미 사용한 `runId`는 입력 오류입니다. 중단된 실행을 이어서 하려면 같은 `runId`와 `"resume": true`를 지정합니다(아래의 "중단된 삭제로부터의 복구" 참조). 아카이브 키에 `runId`가 들어 있으므로, dry run과 실제 실행, 또는 덮어쓴 뒤의 재아카이브가 서로의 오브젝트를 덮어쓰지 않습니다. 버저닝이 없으면 덮어쓰기는 이전 오브젝트를 삭제하며, 최소 보관 기간이 있는 클래스에서는 조기 삭제 요금이 될 수 있습니다.

선택에서 제외되는 것:

| 조건 | 기본값 | 이유 |
|---|---|---|
| 50 GiB 초과 | 제외하고 원장에 `SKIPPED_TOO_LARGE`로 기록한다. `allowOversize: true`로 포함할 수 있다 | 공식 페이지([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html), 2026-11-26 열람)에는 "Maximum object size is 50 GiB for uploads, but you can download objects larger than that"라고 되어 있다. 복원은 Access Point를 통해 쓰기 때문에, 이 패턴은 그보다 큰 파일을 Access Point로 복원할 수 없다(버킷에서 직접 다운로드할 수 있다) |
| `MinFileSizeBytes` 미만 | 131,072 바이트(128 KiB). 입력의 `minSizeBytes`로 바꿀 수 있다 | [Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare)(2026-11-26 열람)에 따르면 Standard-IA와 Glacier Instant Retrieval은 오브젝트당 최소 128 KB로 청구되고, Glacier Flexible Retrieval과 Deep Archive는 오브젝트당 40 KB의 메타데이터가 더해진다(32 KB는 해당 클래스의 요율, 8 KB는 Standard의 요율). 작은 파일에서는 데이터 자체보다 커진다 |
| `ExcludePatterns`(glob), `ExcludePrefixes` | 비어 있음 | 스택의 값은 항상 적용되며, 입력의 `excludePatterns`와 `excludePrefixes`는 추가만 할 수 있다. 법적 보존 대상의 prefix는 여기에 넣는다 |

Iceberg, Delta, Hive 테이블의 데이터 파일, 가동 중인 데이터베이스의 파일, VM 디스크 이미지(`*.vmdk`, `*.vhd`, `*.qcow2` 등)는 항상 제외하세요. 이 패턴은 파일을 하나씩 옮기며, 테이블 메타데이터나 파일을 열어 둔 프로세스에 대해서는 아무것도 알지 못합니다. 테이블은 테이블 자체의 기능(파티션 분리, 스냅샷 만료)으로 정리하고, 그 후에 남은 경로만 대상으로 하세요. 법적 보존 대상인지는 법무 담당 부서가 판단할 일이며, 이 패턴은 판단하지 않습니다.
### 복원
입력은 `runId`와 `keys` 또는 `prefix` 중 정확히 하나입니다. `tier`(기본값 `Bulk`)와 `days`(기본값 7)를 지정할 수 있습니다.
1. 원장에서 `DELETED`인 파일을 선택한다. 아카이브용 버킷에 사본이 있으면 `DELETING`과 `CHANGED`인 파일도 선택한다(중단된 삭제로 남은 항목을 복원할 수 있도록)
2. Access Point에 같은 키가 이미 있으면 `EXISTS`로 남기고 덮어쓰지 않는다
3. S3 Glacier Flexible Retrieval과 S3 Glacier Deep Archive의 오브젝트에는 `RestoreObject`를 요청한다(S3 Glacier Instant Retrieval은 불필요)
4. 완료 대기는 폴링입니다(`RestorePollMinutes`마다 `HeadObject`의 `Restore` 헤더를 읽고, `RestoreMaxWaitHours`에서 중단). EventBridge의 `Object Restore Completed`는 사용하지 않습니다. 버킷의 EventBridge 알림은 활성화되어 있으므로 나중에 전환할 수 있습니다
5. 버킷에서 Access Point로 `CopyObject`(5 GiB 초과는 Fargate). 원장을 `RESTORED`로 한다
6. 복원된 파일을 Access Point를 통해 다시 읽어 해시를 계산하고, 원장의 SHA-256, CRC64NVME, 크기와 비교한다(5 GiB 초과는 Fargate). 일치하면 `RESTORE_VERIFIED`, 다르면 `RESTORE_MISMATCH`
7. `RESTORE_VERIFIED`인 파일만을 대상으로, 속성 재설정용 스크립트 `manifests/<runId>-reapply.sh`를 쓴다

복원된 파일의 소유자는 0:1, 모드는 644, 수정 시각은 복원한 시각이었습니다(위 환경에서 확인). 원래 값은 `CopyObject`로는 복원되지 않습니다.
### 중단된 삭제로부터의 복구
삭제 도중에 Lambda가 멈추거나 재시도를 다 써 버리면, 원장에 `DELETING` 또는 `APPROVED` 항목이 남을 수 있습니다. 결과에는 `COMPLETED_WITH_ERRORS`, `stuckDeleting`, `notDeleted`로 표시되고 `FilesStuckDeletingAlarm`이 울립니다. 같은 `runId`와 `"resume": true`로 아카이브 스테이트 머신을 시작하면 `reconcile`이 실행되어 아래와 같이 항목을 정리하고, 남은 파일에 대해 새로운 승인을 요청합니다.
| 원장 | Access Point | 결과 |
|---|---|---|
| `DELETING` | 파일 없음 | `DELETED`(삭제는 이루어졌다. `reconciled: true`) |
| `DELETING`, `APPROVED` | 파일 있음, ETag와 크기가 원장과 같음 | `VERIFIED`로 되돌림. 삭제하려면 새로운 승인이 필요 |
| `DELETING`, `APPROVED` | 파일 있음, 원장과 다름 | `CHANGED` |
| 둘 중 하나 | 그 항목을 쥐고 있는 실행이 아직 실행 중 | 손대지 않음 |
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"runId": "<runId>", "olderThanDays": 0, "resume": true, "dryRun": false, "requestedBy": "<your IAM principal ARN>"}'
```
`DELETING`으로 남은 항목을 되돌려야 할 때는, 복원 스테이트 머신이 아카이브용 버킷의 사본에서 복원합니다.
## 승인 조작
승인 알림에는 태스크 토큰을 포함하지 않습니다. 토큰은 AWS Systems Manager Parameter Store의 SecureString(`/<stack>/approvals/<runId>`)에 있습니다. 승인하는 사람은 그 파라미터를 읽을 권한과 `states:SendTaskSuccess` 권한을 가진 사람입니다.
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output "{\"approved\": true, \"approver\": \"$(aws sts get-caller-identity --query Arn --output text)\"}"
# 거부:
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
승인 후에 `approval` 함수가 `approver`와 시작 입력의 `requestedBy`를 비교합니다(`RequireSeparateApprover=true`, 기본값). 같은 주체이면 아무것도 `APPROVED`로 하지 않고 `APPROVAL_REFUSED`로 실행을 끝냅니다. 역할의 ARN과 그 역할의 세션 ARN은 같은 주체로 취급합니다. 그렇지 않으면 목록의 각 파일이 원장에서 `approvedBy`, `approvedAt`, 실행 ARN과 함께 `APPROVED`가 됩니다. `delete` 함수는 이 기록이 있는 파일만 삭제하며, 직접 호출해도 기록이 없는 파일은 삭제하지 않습니다.

`approver`와 `requestedBy`는 모두 호출자가 신고하는 값입니다. 원장의 `deletedBy`는 `approvedBy`에서 가져옵니다. 실제로 시작하고 승인한 주체는 CloudTrail의 `StartExecution`과 `SendTaskSuccess` 이벤트에 남습니다. 주체 단위로 직무 분리를 보장하려면 IAM에서 시작하는 역할과 승인하는 역할을 분리하세요.
## 속성 재설정
복원의 마지막에 `manifests/<runId>-reapply.sh`가 작성됩니다. NFS로 볼륨을 마운트한 호스트에서 root로 실행합니다.
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
스크립트에는 `chown`, `chmod`, `touch -d`만 포함되며, 원장의 값은 엄격한 형식으로 검사하고, 키는 셸 인용으로 한 단어로 만듭니다. 형식에 맞지 않는 값은 주석이 되어 실행되지 않습니다. ONTAP REST API로 소유자, 그룹, 모드, 수정 시각을 설정할 수 있는지는 확인하지 않았으므로 이 경로는 구현하지 않았습니다.
## 배포
### 전제
- Access Point의 별칭과 ARN 모두(IAM에 두 형식이 모두 필요합니다. 별칭만 있는 정책은 배포할 수 있어도 실행 시 거부됩니다)
- Access Point 정책. 템플릿으로는 붙일 수 없으므로 아래와 같이 배포 후에 붙입니다. 없으면 실행 시 첫 번째 S3 호출이 거부됩니다
- 아카이브용 버킷의 이름(스택이 생성합니다. `DeletionPolicy: Retain`, Block Public Access, 기본 SSE-S3, KMS는 선택, EventBridge 알림 활성화, TLS 필수)
- `selection=ATIME`과 속성 기록을 사용할 때만: VPC, 서브넷, ONTAP 자격 증명을 담은 시크릿, 관리 엔드포인트, 볼륨 UUID, `OntapVerifySsl`. FSx for ONTAP 관리 엔드포인트의 인증서는 공인 CA의 서명이 아니므로 기본값은 `false`(검증하지 않음)이며, 이 경우 ONTAP 자격 증명은 상대를 인증하지 않는 연결로 전송됩니다(경로는 VPC 내부). `true`로 하면 검증에 실패하여 선택 단계에서 멈췄습니다(실기에서 관측). VPC 내 Lambda에서 Secrets Manager와 S3로 가는 경로(VPC 엔드포인트 또는 NAT)가 필요합니다
- 5 GiB를 초과하는 파일을 다룰 때만: ECR에 둔 이미지. Access Point가 인터넷 기점이므로 Fargate의 서브넷에는 NAT 게이트웨이 또는 공인 IP가 필요합니다
- 확인이 끝난 알림 구독. SNS 이메일 구독은 수신자가 확인 링크를 클릭하기 전에는 아무것도 하지 않으며, 확인하지 않으면 아무도 승인 요청을 볼 수 없습니다
### 절차
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # 모든 <PLACEHOLDER>를 바꾼다
sam build && sam deploy
```
배포 후에 Access Point 정책을 붙입니다. 스크립트가 스택 출력의 역할 ARN으로, `delete` 함수의 역할에만 `s3:DeleteObject`를, 복원 역할에만 `s3:PutObject`를 허용하는 정책을 생성합니다.
```bash
aws cloudformation describe-stacks --stack-name <stack> --query 'Stacks[0].Outputs' > outputs.json
python3 tools/render_access_point_policy.py --outputs outputs.json \
  --access-point-arn arn:aws:s3:<region>:<account>:accesspoint/<name> > ap-policy.json
aws s3control put-access-point-policy --account-id <account> --name <name> --policy file://ap-policy.json
aws sns list-subscriptions-by-topic --topic-arn <NotificationTopicArn> \
  --query 'Subscriptions[].SubscriptionArn'   # PendingConfirmation이 남아 있지 않을 것
```
Access Point에 이미 정책이 있으면 이것으로 대체되므로, 기존 스테이트먼트를 먼저 병합하세요.
Fargate를 사용하는 경우, 리포지토리 루트에서 이미지를 만들어 자신의 ECR 리포지토리에 push하고 `FargateImageUri`에 지정합니다.
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
실행은 먼저 `dryRun`을 생략한(즉 `true`인) 입력으로 합니다.
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20, "excludePatterns": ["*.vmdk"]}'
```
삭제까지 하려면 `"dryRun": false`를 JSON 불리언으로 전달하고, `requestedBy`에 시작하는 주체를 넣습니다. 문자열 `"false"`는 입력 오류이며 삭제되지 않습니다.
## 디렉터리 구성
```
archive-verify-delete/
├── template.yaml                # SAM: 버킷, 원장, Lambda 9개, 스테이트 머신 2개, Fargate(선택), 알람
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore,watchdog}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tools/render_access_point_policy.py
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
도메인 로직(체크섬, 입력 검사, 원장, 복원 후 검증)은 [`shared/archive_verify/`](../../../shared/archive_verify/)에 있으며 `shared/tests/`에서 테스트합니다. Access Point에 대한 읽기와 쓰기는 `shared/s3ap_helper.py`를 거칩니다.
## 로컬 테스트
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
삭제 판정이 깨지면 감지되는지 확인하기 위해, ETag 비교를 제거한 스텁으로 `test_does_not_delete_when_etag_changed`와 `test_does_not_delete_when_size_differs_but_etag_equal`을 1회 실행했고, 2건 모두 `assert 'DELETED' == 'CHANGED'`로 실패했습니다. 승인 기록의 확인과 50 GiB 제외는 테스트를 먼저 작성하고, 구현하기 전의 코드에 대해 1회 실행하여 각각 `assert 'DELETED' != 'DELETED'`와 `KeyError: 'skippedTooLarge'`로 실패하는 것을 확인했습니다.
## Success Metrics
### Outcome
거의 읽지 않는 파일을 대조와 사람의 승인을 거쳐 S3 Glacier 계열 클래스로 옮겨 볼륨 사용량을 낮춘다. 옮긴 파일은 원장에서 찾아 복원할 수 있다.
### Metrics
목표값은 이용자가 정합니다. 여기에는 수치를 두지 않습니다.
| 구분 | 지표 | 정의 |
|---|---|---|
| Business Outcome | 확보한 용량 | 실행 전후의 볼륨 사용 용량의 차이(스냅샷을 정리한 뒤). `bytesDeleted`(`-result.json`)는 삭제한 파일의 크기 합계이며 확보한 용량이 아니다. 스냅샷이 남아 있는 동안은 볼륨 사용량이 줄지 않고, 압축이나 중복 제거가 적용된 데이터는 논리 크기보다 적게 확보된다 |
| Business Outcome | 월간 보관 비용의 절감 예상 | (용량 풀에서 옮긴 GB × 단가 차이) − (아카이브용 클래스의 보관 요금, 오브젝트당 오버헤드, 복원 요금). 단가는 아래의 "비용 추정" 참조 |
| Technical KPI | 대조 일치율 | `VERIFIED` ÷ (`VERIFIED` + `MISMATCH`) |
| Technical KPI | 삭제하지 않은 건수 | `CHANGED`, `MISMATCH`, `FAILED`의 합계 |
| Technical KPI | 복원 검증 일치율 | `RESTORE_VERIFIED` ÷ (`RESTORE_VERIFIED` + `RESTORE_MISMATCH`) |
| Quality KPI | 승인 없이 삭제된 건수 | 0이어야 한다. `approvedBy` 또는 `approvedAt`이 비어 있는 `DELETED` 항목을 센다 |
| Cost KPI | 실행당 Lambda, Fargate, DynamoDB, S3 요청, 상태 전이, 아카이브용 클래스의 보관 요금 | `dryRun=true`와 작은 `maxFiles`로 측정한 실행에서 "비용 추정"의 식으로 견적한다 |
| Go / No-Go | 기술: 실제 환경의 실행에서, 복사한 모든 파일이 `VERIFIED`가 되고, 의도적으로 만든 `CHANGED` 파일이 삭제되지 않으며, 시작한 주체의 자기 승인이 거부되고, 복원한 파일이 `RESTORE_VERIFIED`가 될 것. 업무: 예상 절감액이 운영 비용(승인 작업, 복원 요청 대응)을 웃돌 것. 복원 요청의 접수 창구와 목표 응답 시간(클래스의 복원 시간 포함)이 정해져 있을 것. 이용자에게 안내가 끝나 있을 것 | 모두 충족하기 전에는 운영 볼륨에 `dryRun=false`를 사용하지 않는다. 먼저 각 항목을 누가 판단할지(데이터 소유자, 승인자, 운영 책임자)를 정한다 |

PoC의 계획과 운영 전 확인은 FSx for ONTAP Adoption Playbook의 [pre-production review checklist](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/04-build/checklists/pre-production-review.md)와 [pre-migration inventory](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/01-assess/checklists/inventory.md)(모두 일본어)에 있습니다. 이 패턴의 PoC에서는 `maxFiles`를 20, 200, 2,000으로 올리면서 부모 실행의 소요 시간, 상태 전이, Fargate 초를 기록하면 파일당 값을 얻을 수 있습니다.
### Measurement Method
Step Functions 실행 이력과 로그(`/aws/vendedlogs/states/<stack>-archive`와 `-restore`, 실행 데이터는 포함하지 않음), `manifests/<runId>-result.json`, `manifests/<runId>-approval.json`, CloudWatch EMF 메트릭(`FilesVerified`, `FilesDeleted`, `FilesMismatch`, `FilesChanged`, `FilesFailed`, `FilesStuckDeleting`, `BytesVerified`, `BytesDeleted`, `RestoreVerified`, `RestoreMismatch`, `ApprovalPendingHours`), 원장.

알람(모두 알림 토픽으로 전송):

| 알람 | 조건 |
|---|---|
| `ArchiveExecutionsFailedAlarm`, `RestoreExecutionsFailedAlarm` | 5분 사이에 실패, 타임아웃, 중단된 실행이 1건 이상 |
| `ApprovalPendingAlarm` | 승인 요청이 `ApprovalAlarmHours`(기본값 24)를 넘어 대기 중 |
| `FilesStuckDeletingAlarm` | `DELETING` 또는 `APPROVED` 항목이 남은 채 실행이 끝남 |
| `FilesMismatchAlarm` | 아카이브한 사본이 일치하지 않음(`MISMATCH`) |
| `RestoreMismatchAlarm` | 복원한 파일이 원장과 일치하지 않음 |
알림 토픽은 고객 관리형 KMS 키로 암호화되어 있습니다. AWS 관리형 키(`alias/aws/sns`)의 키 정책은 편집할 수 없으며, EventBridge와 CloudWatch 알람이 암호화된 토픽에 게시하려면 서비스 주체에 `kms:GenerateDataKey*`와 `kms:Decrypt`를 허용하는 고객 관리형 키가 필요합니다([Amazon SNS key management](https://docs.aws.amazon.com/sns/latest/dg/sns-key-management.html), 2026-11-26 열람). 두 번째 실행에서 EventBridge의 실패 알림과 알람 알림이 도착하는 것을 확인했습니다.
## Performance Considerations
기본 병렬도는 아래의 1회 측정에 근거합니다. 나머지는 설계상의 요인이며 측정하지 않았습니다.
- 원본 파일은 2회 읽힙니다. 1회째는 해시 계산을 위해 Access Point에서 읽고, 2회째는 `CopyObject`가 서버 측에서 읽습니다. 읽기 요청 요금이 발생하며, 용량 풀에 있는 데이터에는 용량 풀의 읽기 요금도 발생합니다
- 병렬도는 `MapConcurrency`입니다(기본값 2, 아카이브와 복원 공통). 1회 측정에서 Lambda 함수가 Access Point를 통해 5.3 GB(약 4.94 GiB)를 69.8초에 읽었으며, 스트림 하나에서 약 76 MB/s입니다. 이는 이 환경의 처리량 용량 128 MBps의 약 60%에 해당합니다. 각 파일은 2회 읽히고 같은 볼륨을 이용자도 사용하므로 기본값을 2로 했습니다. 큰 파일이나 부하가 높은 볼륨에서는 1로 하고, 올리기 전에 실행 중의 파일 시스템 `DataReadBytes`와 클라이언트 지연을 확인하세요. 병렬 실행은 측정하지 않았습니다
- `LargeFileThresholdBytes`의 기본값 5 GiB는 `CopyObject`를 1회 요청으로 처리할 수 있는 상한에서 나온 값입니다. 위의 속도라면 Lambda의 15분으로 약 63 GiB를 처리할 수 있지만, 이는 데이터 1점에 근거한 값입니다
- 목록은 `ListObjectsV2`의 전체 결과를 Lambda 하나의 메모리에 올립니다. 수백만 건을 넘으면 `prefix`로 나누세요
- `selection=ATIME`은 디렉터리를 깊이 우선으로 탐색합니다. 탐색 상한은 200,000 엔트리(`ONTAP_SCAN_LIMIT`)이며, 넘으면 도중까지의 결과를 반환합니다
- 복원 대기 시간은 클래스와 `tier`로 정해집니다. S3 Glacier Deep Archive는 Standard에서 12시간 이내, Bulk에서 48시간 이내라고 AWS가 기재하고 있습니다. `RestoreMaxWaitHours`의 기본값은 72입니다. 대기 시간이 긴 클래스에서는 `RestorePollMinutes`를 크게 하면 폴링에 따른 상태 전이가 줄어듭니다
- Fargate 태스크는 `FargateTimeoutSeconds`(기본값 7200초)로 제한됩니다. 모든 Task에 `TimeoutSeconds`가 있으며, 타임아웃은 재시도됩니다
## 비용 추정
청구액은 측정하지 않았습니다. 아래는 견적에 사용할 수 있는 측정된 사용량과, 공개된 오브젝트당 조건입니다.
두 번의 실행에서의 파일당 상태 전이(각 1회 실행):

| 실행 | 파일당 상태 전이 | 출처 |
|---|---|---|
| 아카이브 dry run | 17(119 ÷ 7), 18(72 ÷ 4) | 첫 번째와 두 번째 실행 |
| 아카이브 실제 실행(삭제 포함) | 18(127 ÷ 7), 19.5(78 ÷ 4) | 같음 |
| 복원(`Expedited`. 두 번째는 검증 포함) | 18(107 ÷ 6), 14(56 ÷ 4) | 같음 |
대기 시간이 긴 클래스에서는 폴링할 때마다 전이가 더해집니다.
오브젝트당 보관 조건([Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare), 2026-11-26 열람):

| 클래스 | 최소 보관 기간 | 오브젝트당 오버헤드, 최소 청구 크기 |
|---|---|---|
| S3 Glacier Instant Retrieval | 90일 | 최소 청구 오브젝트 크기 128 KB |
| S3 Glacier Flexible Retrieval | 90일 | 40 KB의 메타데이터(32 KB는 이 클래스의 요율, 8 KB는 S3 Standard의 요율) |
| S3 Glacier Deep Archive | 180일 | 40 KB의 메타데이터(구분은 같음) |
식: 월 비용 ≈ 파일 수 × 파일당 상태 전이 × 전이당 단가 + Lambda와 Fargate의 실행 시간 × 단가 + 파일 수 × (`CopyObject`, `HeadObject`, `DeleteObject` 등의 요청 단가) + (데이터 + 파일 수 × 오버헤드) × 클래스 단가 + 복원할 때의 복원 요금. 단가는 [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)과 [AWS Step Functions pricing](https://aws.amazon.com/step-functions/pricing/)에서 리전과 날짜를 지정하여 가져오세요. 여기에는 기재하지 않습니다.
## Governance Note
> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법률, 컴플라이언스, 규제에 관한 조언이 아닙니다. 조직은 적격한 전문가와 상담하십시오.
- 대조 결과와 승인은 사람이 최종 판단을 하기 위한 보조 신호입니다. AI는 사용하지 않습니다
- 보존 기간과 불변성을 충족해야 하는 경우 이 패턴은 대응하지 않습니다. Object Lock 등을 사용하지 않으므로 권한이 있으면 누구나 삭제할 수 있습니다
- 출력 분류: 원장과 매니페스트에는 파일 경로, 크기, 해시, 속성이 들어갑니다. 경로에는 개인 이름이나 환자, 사건의 식별자가 포함될 수 있으므로, 출력에는 기본적으로 `data_classification`으로 `RESTRICTED`(`shared/data_classification.py`의 "Restricted — Limited access")를 붙입니다. 데이터 자체의 분류가 더 엄격하면 `DataClassification` 파라미터에 그 분류를 지정하세요. 분류는 이용자가 판단합니다. 파일 내용은 아카이브용 버킷에 들어가므로 원본 데이터와 같은 분류로 취급하세요
- Human Review: 승인은 모든 실행에 필수입니다. 신뢰도에 의한 자동 승인은 없습니다. 기본 설정에서는 시작한 주체와 승인자가 같은 주체이면 아무것도 삭제되지 않습니다
- IAM: Access Point에 대한 `s3:DeleteObject`를 가진 것은 `delete` 함수의 역할뿐이며, `s3:PutObject`를 가진 것은 복원 스테이트 머신과 복원용 Fargate 태스크 역할뿐입니다. 아카이브용 Fargate 태스크는 복사만 하며 원본 파일을 삭제하거나 덮어쓸 수 없습니다. 원장 항목을 삭제할 수 있는 주체는 없습니다
- 감사: 승인과 삭제는 원장(`approvedBy`, `approvedAt`, `requestedBy`, `deletedBy`, `deletedAt`), `manifests/<runId>-approval.json`, Step Functions 실행 이력과 로그에 남습니다. CloudTrail에 삭제가 기록되는 것은 트레일에서 S3 데이터 이벤트를 활성화한 경우뿐이며, 이 실행에서는 확인하지 않았습니다
- 사본의 수: 두 번째 복사가 없으면 삭제 후에는 아카이브용 버킷의 오브젝트가 유일한 사본입니다. 승인 알림에 그 내용이 기재됩니다
## 제약과 미확인 사항
- Access Point에서 다른 리전의 버킷으로의 직접 복사는 `AccessDenied`였습니다(Access Point 1개, 1회). 두 번째 복사는 같은 리전의 버킷만 대상으로 합니다
- UNIX 스타일 볼륨에서의 확인입니다. 크기와 mtime을 바꾸지 않는 내용 변경은 ETag와 크기 확인으로 검출되지 않습니다(위의 "실기 통합 실행에서 알게 된 동작"). `chown`이 ETag를 바꾸는지는 확인하지 않았습니다
- 속성은 디렉터리 목록으로 가져옵니다. 파일 하나를 위해 부모 디렉터리 전체를 읽으므로, 큰 디렉터리에서는 느려집니다
- 아카이브용 버킷의 버저닝은 Object Lock이 아닙니다. 버전은 남지만 권한이 있으면 버전도 삭제할 수 있습니다
- 50 GiB를 초과하는 파일은 기본적으로 선택되지 않습니다. `allowOversize: true`로 포함하면 Access Point로 복원할 수 없으므로 버킷에서 다운로드하세요
- `requestedBy`와 `approver`는 신고된 값입니다. 주체 단위의 분리는 IAM과 CloudTrail로 확인하세요
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
