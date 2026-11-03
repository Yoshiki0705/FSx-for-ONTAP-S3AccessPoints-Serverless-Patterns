# 일본어 문서 OCR × AI 에이전트 — S3 Access Points 위에서 Textract(도쿄) 실행

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

FSx for ONTAP S3 Access Points에 있는 스캔 문서(이미지, PDF, TIFF)를 Amazon Textract 도쿄 리전으로 일본어 OCR 처리하고,
그 실행을 Amazon Bedrock AgentCore Gateway의 Step Functions 커넥터를 통해 AI 에이전트 도구로 노출하는 샘플입니다.
Textract의 일본어 지원과 도쿄 리전 제공 시작은 2026-11-02에 발표되었습니다.

에이전트가 정하는 것은 어떤 컬렉션을, 어떤 프로파일로, 몇 건까지 읽을지뿐입니다. 단계의 순서, 재시도, 실패 처리는
상태 머신이 담당합니다. OCR 본문은 에이전트에 전달하지 않고 결과 버킷에 저장합니다.

## 사용 사례

- 청구서, 계약서, 메모 같은 스캔 문서를 파일 서버에 둔 채로 일본어 OCR
- 사람의 확인이 필요한 문서와 그 이유를 에이전트가 정리
- Textract Forms를 쓸 수 없는 일본어 청구서에서 합계 금액 같은 항목을 근거와 함께 추출(선택)

## 아키텍처

```
AI 에이전트 ──MCP──▶ AgentCore Gateway (NONE | AWS_IAM)
                       │ GatewayServiceRole: states:StartExecution 등
                       ▼
           Standard StateMachine (Discover → Map → Report)
                       │
   이미지: bytes를 Textract 동기 API에 전달    PDF / TIFF: 임시 복사본 → Textract 비동기 API
                       │
   S3 Access Points(DemoMode는 일반 S3) ──▶ 결과 버킷(result.json / text.txt / manifest.json)
```

자세한 내용은 [docs/architecture.md](docs/architecture.md)(일본어)를 참조하십시오.

## 노출되는 도구

| 도구 | 입력 | 용도 |
|---|---|---|
| `ocr___StartExecution` | `input`(JSON 문자열) | OCR 시작. `executionArn` 반환 |
| `ocr___DescribeExecution` | `executionArn`, `includedData: "ALL_DATA"` | 상태와 결과 확인 |
| `ocr___ListExecutions` | `statusFilter`(선택) | 최근 실행 목록 |
| `ocr___GetExecutionHistory` | `executionArn` | 중단 지점 조사(출력이 큼) |
| `ocr___DescribeStateMachine` | `includedData`(선택) | 정의 확인 |

고정된 상태 머신 ARN은 도구에 나타나지 않으므로 에이전트가 변경할 수 없습니다. `includedData: "ALL_DATA"` 없이
호출한 `DescribeExecution`은 `output`도, FAILED 실행의 `error`와 `cause`도 반환하지 않습니다.

## 에이전트가 전달하는 입력

```json
{"collection": "invoices", "profile": "structure", "max_files": 20, "modified_after": "2026-10-01"}
```

| 키 | 필수 | 규칙 |
|---|---|---|
| `collection` | 예 | ASCII ID(`^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$`). 허용 목록(`CollectionsJson`)에 있어야 함 |
| `profile` | 아니요 | `text`(문자만) 또는 `structure`(문자, 표, 레이아웃). 생략하면 컬렉션 설정을 따름 |
| `max_files` | 아니요 | 1부터 `MaxFilesPerExecution`까지의 정수. 키 순서로 앞에서부터 선택 |
| `modified_after` | 아니요 | `YYYY-MM-DD`. 해당 날짜 이후에 수정된 문서만 |

S3 경로와 키는 받지 않습니다. 알 수 없는 키나 규칙 위반은 FAILED로 끝나며 `Cause`에 수정 방법이 들어 있습니다.

## 처리 경로와 프로파일

| 문서 | 경로 | 비고 |
|---|---|---|
| PNG / JPEG, 5 MiB 이하 | 동기. bytes를 직접 전달 | 복사본 없음 |
| PNG / JPEG, 5 MiB 초과 10 MiB 이하 | 비동기. 임시 복사본 | |
| PDF / TIFF | 비동기. 임시 복사본 | 페이지 수는 추정하지 않음 |

`text`는 `DetectDocumentText`, `structure`는 `AnalyzeDocument`(`TABLES`와 `LAYOUT`)를 호출합니다. Forms, Queries,
AnalyzeExpense, AnalyzeID는 제공하지 않습니다(일본어 미지원이거나 도쿄에서 허용되지 않음).

## 에이전트가 받는 것

`DescribeExecution`(`ALL_DATA`)의 `output`에는 상태, 건수, 평균 신뢰도, 검토 대상 목록과 그 이유, 문서별 결과의 S3 URI가
들어 있습니다. OCR 본문은 들어 있지 않지만 원본 키(파일 이름)는 포함됩니다. 항목 추출을 켜면 항목 값(60자까지)도
포함됩니다. 전체 문서 목록은 결과 버킷의 `manifest.json`에 있습니다.

## 매개변수

| 매개변수 | 설명 | 기본값 |
|---|---|---|
| `S3AccessPointAlias` | S3 Access Points alias(DemoMode에서는 일반 버킷 이름) | (필수) |
| `DemoMode` | `true`이면 FSx for ONTAP 없이 동작 | `false` |
| `CollectionsJson` | 컬렉션 허용 목록(JSON). 비어 있으면 `FilePrefix`로 하나를 생성 | `""` |
| `MaxFilesPerExecution` | 실행당 최대 문서 수(1–100) | `50` |
| `MapConcurrency` | 병렬 처리 문서 수. 도쿄의 동기 API는 1 TPS | `2` |
| `AsyncJobMaxSeconds` | 비동기 작업을 기다리는 시간(초) | `600` |
| `EnableFieldExtraction` | Bedrock 항목 추출. 꺼져 있으면 Bedrock 권한을 부여하지 않음 | `false` |
| `BedrockModelId` | 항목 추출용 모델 또는 추론 프로파일 ID([docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)) | `apac.amazon.nova-pro-v1:0` |
| `DataClassification` | 출력에 붙이는 데이터 분류의 기본값 | `INTERNAL` |
| `ReviewAutoApproveThreshold` / `ReviewRejectThreshold` | 평균 신뢰도 임계값 | `0.95` / `0.30` |
| `LowConfidenceLineThreshold` / `LowConfidenceCharRatioLimit` | 저신뢰도 행의 기준과, 문서를 검토 대상으로 올리는 문자 비율 | `90` / `0.05` |
| `HandwritingWordRatioLimit` | 필기로 판정된 단어 비율의 상한 | `0.05` |
| `GatewayAuthorizerType` | `NONE`(PoC 전용) 또는 `AWS_IAM` | `NONE` |
| `GatewayName` | Gateway 이름 | `ja-ocr-agent-gateway` |
| `NotificationEmail` | SNS 알림 주소(비우면 생략) | `""` |

## 배포

배포 스크립트는 `sam build`, `sam package`, `aws cloudformation deploy` 순으로 실행하고, 배포 후 저장된 `CollectionsJson`과
`tools/list`를 확인합니다.

```bash
# DemoMode (FSx for ONTAP 불필요)
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <demo-bucket> --demo-mode \
  --collections-file collections.json --stack-name ja-ocr-agent-demo

# S3 Access Points. 서명된 호출을 요구하고 항목 추출을 켠다
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <your-ap>-ext-s3alias \
  --collections-file collections.json --auth iam --enable-field-extraction --stack-name ja-ocr-agent

# 정리 (--delete-results를 붙이면 OCR 텍스트가 있는 결과 버킷도 삭제)
./scripts/deploy-japanese-document-ocr-agent.sh --cleanup --stack-name ja-ocr-agent --delete-results
```

컬렉션 작성법, 에이전트 시스템 프롬프트, 대화 예시는 [docs/demo-guide.md](docs/demo-guide.md)(일본어)에 있습니다.

## Human Review 임계값

OCR 평균 신뢰도(문자 수 가중)를 `shared/human_review.py`로 평가하고 다음 조건으로 상향합니다.

| 조건 | 판정 |
|---|---|
| 평균 신뢰도가 `ReviewAutoApproveThreshold`(0.95) 이상이고 아래 조건이 없음 | AUTO_APPROVE |
| 평균 신뢰도가 0.95 미만 | HUMAN_REVIEW |
| 평균 신뢰도가 `ReviewRejectThreshold`(0.30) 미만 | REJECT |
| 신뢰도 90 미만 행에 있는 문자가 전체의 5%를 초과 | HUMAN_REVIEW로 상향 |
| 필기로 판정된 단어가 5%를 초과 | HUMAN_REVIEW로 상향 |
| 병합 셀 등 구조가 의심스러운 표가 있음 | HUMAN_REVIEW로 상향 |
| 검출된 행이 없음 | HUMAN_REVIEW |
| 항목 추출에서 근거 없는 항목이 있거나 추출에 실패 | HUMAN_REVIEW로 상향(REJECT는 변경하지 않음) |

기본 임계값은 출발점이며 측정으로 구한 최적값이 아닙니다. 가상의 문서 4건으로 실행했을 때, 문자 오류가 0건인
계약서를 포함해 4건 모두 기본 임계값에서 HUMAN_REVIEW가 되었습니다([docs/success-metrics.md](docs/success-metrics.md)).
자신의 문서로 분포를 측정한 뒤 결정하십시오. 판정은 결과에 포함될 뿐이며 이 패턴은 최종 판단을 내리지 않습니다.
`result.json`에는 OCR만의 판정이 있고, 항목 추출을 포함한 최종 판정은 `manifest.json`과 실행 결과에 있습니다.

## 데이터 분류

출력에는 `shared/data_classification.py` 기반 `data_classification`이 붙습니다. 기본값은 `INTERNAL`이며
`DataClassification`으로 변경하거나 컬렉션별 `classification`으로 재정의합니다. 결과 버킷은 SSE-KMS, 퍼블릭 액세스 차단,
TLS 이외 요청 거부로 구성되며 스택을 삭제해도 남습니다.

## 항목 추출(선택)

`EnableFieldExtraction=true`이면 컬렉션의 `fields`에 적은 항목(최대 20개, 각 40자 이하)을 Bedrock Converse API로
추출합니다. 모델은 값과 함께 원문에서 인용한 문장을 반환하고, 코드가 그 인용이 OCR 텍스트에 실제로 있는지
(NFKC 정규화와 공백 제거 후 부분 일치) 기계적으로 확인합니다. 인용을 찾지 못한 항목은 `grounded: false`이며,
하나라도 있으면 문서는 HUMAN_REVIEW가 됩니다. 문서에 적혀 있지 않은 항목도 근거 없음으로 세므로, `fields`에는
컬렉션의 모든 문서에 있는 항목만 나열하십시오.

## Governance Note

- OCR 신뢰도는 보조 신호이며 최종 판단이 아닙니다. 측정에서는 오류가 0건인 문서에서 문자의 22.6%가 신뢰도 90 미만
  행에 있었고, 잘못 읽은 행("括孤")의 신뢰도는 98.2였습니다. 신뢰도만을 자동 승인의 유일한 조건으로 삼지 마십시오.
- 추출된 항목 값은 LLM의 출력입니다. 인용 검증은 날조를 줄이지만 정확성을 보장하지 않습니다.
- 문서 내용에서 꺼낸 값은 에이전트에게 신뢰할 수 없는 입력입니다. 값 안에 지시처럼 보이는 문장이 있어도 따르지 않도록
  시스템 프롬프트에서 알려 주십시오. 지시가 적힌 문서에 대한 동작은 측정하지 않았습니다.
- PDF와 TIFF는 처리하는 동안 같은 계정, 같은 리전의 임시 버킷에 복사됩니다(SSE-KMS, 퍼블릭 액세스 차단, 작업 종료 시
  삭제, 백스톱으로 1일 수명 주기 규칙). 복사를 허용하지 않는 운영에서는 컬렉션의 `suffixes`를 이미지로 제한하십시오.
- `GatewayAuthorizerType=NONE`은 URL을 아는 누구나 OCR을 시작할 수 있습니다(본문은 반환되지 않음). PoC 전용이며
  공유 환경에서는 `AWS_IAM`을 사용하십시오. authorizer 유형은 생성 후 변경할 수 없습니다.
- Textract는 시작한 작업을 취소할 수 없습니다. `AsyncJobMaxSeconds`에서 기다리기를 멈춰도 과금은 계속될 수 있습니다.
- 이것은 거버넌스 지침이며 법무·컴플라이언스 판단을 대체하지 않습니다.

## Performance Considerations

- 도쿄의 동기 API는 1 TPS입니다. 20회 연속 호출에서 재시도 없는 클라이언트는 병렬 2에서 4회, 병렬 5에서 7회
  스로틀링되었고, adaptive(최대 5회) 클라이언트는 병렬 1, 2, 5 모두 0회였습니다. `MapConcurrency` 기본값은 2입니다.
- 3페이지 PDF(비동기)는 패턴을 통해 약 12초에 완료되었습니다.
- 실행 기록 이벤트는 동기 문서 1건당 13, 비동기 문서는 20 + 9 × 폴링 횟수입니다. 최악의 경우 100문서에서 약 23,200으로
  추정하며 Standard 상한 25,000 안에 들어갑니다.
- Map 상태가 256 KiB를 넘지 않도록, 키가 매우 길면 discovery는 `max_files`보다 적은 수를 선택하고 `truncated`를 반환합니다.
- Textract 비용은 페이지 단위입니다. 도쿄 Price List에서 `text`는 0.0015 USD/페이지, `structure`(Tables와 Layout의 합)는
  0.019 USD/페이지입니다(적용 시작 2026-10-01, 청구액과는 대조하지 않음).

## 테스트

```bash
python3 -m pytest solutions/genai/japanese-document-ocr-agent/tests/ shared/tests/test_textract_helper.py -v
```

## 알려진 주의점

- Forms는 일본어를 지원하지 않습니다. 요청은 받아들여지지만 메모에서는 문장을 중간에서 나눈 쌍을 반환했습니다.
- `DescribeExecution`에는 `includedData: "ALL_DATA"`가 필요합니다. `GetExecutionHistory`는 페이지를 넘길 수 없습니다.
- Gateway 입력에 일본어를 넣으면 `??`가 됩니다. 이 패턴은 ASCII ID만 전달합니다.
- `max_files`는 키 순서로 앞에서부터 선택하므로, 첫 문서가 손상되어 있으면 매번 그 문서가 선택됩니다.
- 검증 환경의 S3 Access Points에는 이미지와 PDF가 없어, 실제 Access Point에서 OCR 성공까지는 확인하지 못했습니다
  (목록 조회, 읽기, 임시 복사본 삭제는 확인). [docs/demo-guide.md](docs/demo-guide.md)의 "既知の注意点"을 참조하십시오.

## 참고

- [Amazon Textract가 일본어를 포함한 지원 언어를 추가하고 도쿄 리전에서 제공 시작 (What's New)](https://aws.amazon.com/jp/about-aws/whats-new/2026/11/textract-tokyo-zurich/)
- [AWS Step Functions as Connector Target (공식)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- 관련 패턴: [stepfunctions-agentcore-tools](../stepfunctions-agentcore-tools/)

---

<!-- playbook-reading:start -->
## 프로덕션 적용 전에 읽을 것

배포 후에 부딪히는 제약을 설계 판단으로 어떻게 옮기는지는 [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook)에 정리되어 있습니다. 같은 내용을 두 곳에 두면 갱신이 멈춘 쪽이 더 오래 남기 때문입니다.

- [데이터 활용](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — 액세스 포인트 경유의 제약 (모든 패턴 공통)
- [보안 및 거버넌스](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/security-governance) — 이 패턴에서 판단이 집중되는 곳
- [구축](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — 프로덕션 전에 확인 (모든 패턴 공통)
<!-- playbook-reading:end -->
