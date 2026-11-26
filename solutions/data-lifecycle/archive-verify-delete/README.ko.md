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
| 이 리포지토리에서 확인함 | moto를 사용한 단위 테스트, 그리고 스테이트 머신과 IAM 구조의 테스트. AWS에는 연결하지 않았습니다 |
| 아직 확인하지 않음 | 패턴 전체의 실제 환경 엔드투엔드 실행. 다수 파일에서의 소요 시간과 요금. Lambda에서 5 GiB에 가까운 파일의 해시 계산 시간. Fargate 멀티파트 복사의 실제 환경 동작. ONTAP REST API의 루트 디렉터리 지정 방법과 `unix_permissions`의 표현. Distributed Map의 `ItemReader`와 `ResultWriter`의 실제 환경 동작. 복원이 필요한 2개 클래스에서의 복원. NTFS 볼륨, root 이외의 사용자, 2세대, Multi-AZ |
삭제 전 확인에는 쓰기 창이 하나 남아 있습니다. Access Point의 `DeleteObject`는 조건부 삭제를 지원하지 않으므로, `HeadObject`로 확인한 뒤 삭제하기까지 사이에 쓰기가 일어나도 감지할 수 없습니다. 이 창은 API 호출 1회 왕복 분량입니다.
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
- `selection=ATIME`과 속성 기록을 사용할 때만: VPC, 서브넷, ONTAP 자격 증명 시크릿, 관리 엔드포인트, 볼륨 UUID. VPC 내부 Lambda에서 Secrets Manager와 S3로 가는 경로(VPC 엔드포인트 또는 NAT)가 필요합니다
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
- UNIX 스타일 볼륨에서의 확인입니다. 수정 시각을 되돌린 뒤 내용을 바꾸는 조작과 `chown`을 ETag로 감지할 수 있는지는 확인하지 않았습니다
- 속성은 디렉터리 목록으로 가져옵니다. 파일 하나를 위해 부모 디렉터리 전체를 읽으므로, 큰 디렉터리에서는 느려집니다
- 아카이브용 버킷의 버저닝은 Object Lock이 아닙니다. 버전은 남지만 권한이 있으면 버전도 삭제할 수 있습니다
## 관련 문서
- [Architecture (EN)](docs/architecture.en.md)
- [S3 Access Points 호환성 메모](../../../docs/s3ap-compatibility-notes.md)
- [아카이브용 클래스로 옮기는 8가지 방식의 비교](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)(일본어)
