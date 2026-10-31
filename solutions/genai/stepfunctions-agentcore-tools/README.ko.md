# Step Functions × AgentCore Gateway — 워크플로를 AI 에이전트 도구로

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | 한국어 | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

FSx for ONTAP S3 Access Points의 파일을 처리하는 Standard Step Functions 워크플로
(검색 → 처리 → 보고)를 Amazon Bedrock AgentCore Gateway의 내장 Step Functions
커넥터를 통해 AI 에이전트 도구로 노출하는 샘플입니다.

에이전트는 언제 실행할지와 어떤 입력을 전달할지를 판단하고, 단계의 순서는 상태 머신이
보장합니다. 정해진 절차는 워크플로에, 실행 판단은 에이전트에 두는 분담입니다.

## 사용 사례

- 상태 머신을 수정하지 않고 기존 Step Functions 워크플로를 에이전트에서 실행
- 절차와 승인은 워크플로에 고정하고 실행 판단만 에이전트에 위임
- 실행 기록에서 어느 단계까지 진행되었는지 에이전트가 조사

## 아키텍처

```
AI 에이전트 ──MCP──▶ AgentCore Gateway (Step Functions 커넥터)
                        │ GatewayServiceRole → states:StartExecution 등
                        ▼
               Standard StateMachine (Discover→Choice→Map→Report)
                        │
           Discovery / Processing / Report Lambda
                        │
                  S3 Access Point (FSx for ONTAP / DemoMode는 일반 S3)
```

자세한 내용은 [docs/architecture.md](docs/architecture.md)를 참조하세요.

## 노출되는 도구

| 도구 | 입력 | 용도 |
|---|---|---|
| `workflow___StartExecution` | `input`(JSON 문자열) | 워크플로 시작 |
| `workflow___ListExecutions` | `statusFilter`(선택) | 실행 목록(Standard 전용) |
| `workflow___DescribeStateMachine` | `includedData`(선택) | 상태 머신 메타/정의 |
| `workflow___DescribeExecution` | `executionArn`, `includedData` | 상태·결과 확인 |
| `workflow___GetExecutionHistory` | `executionArn` | 단계 기록 |

고정된 상태 머신 ARN은 도구에 노출되지 않으며 에이전트가 변경할 수 없습니다.

## 매개변수

| 매개변수 | 설명 | 기본값 |
|---|---|---|
| `S3AccessPointAlias` | FSx for ONTAP 볼륨의 S3 AP Alias(DemoMode에서는 일반 버킷 이름) | (필수) |
| `DemoMode` | `true`이면 FSx for ONTAP 불필요(일반 S3 버킷) | `false` |
| `FilePrefix` | 스캔할 프리픽스 | `input/` |
| `BedrockModelId` | 요약 모델 / 추론 프로파일 ID([docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)) | `apac.amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | 실행당 최대 파일 수 | `100` |
| `NotificationEmail` | SNS 알림 대상(비우면 생략) | `""` |
| `GatewayName` | Gateway 이름(배포 스크립트에서 사용) | `sfn-agentcore-tools-gateway` |

## 배포

Gateway와 커넥터 대상도 CloudFormation 1급 리소스
(`AWS::BedrockAgentCore::Gateway` / `GatewayTarget`)이므로 하나의 템플릿으로 선언적으로
완결됩니다. 배포 스크립트는 `sam build` + `sam deploy` 래퍼이며 배포 후 `tools/list`를
검증합니다.

```bash
# DemoMode(FSx for ONTAP 불필요)
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias my-demo-bucket --demo-mode --stack-name sfn-agentcore-tools-demo

# 프로덕션(S3 AP)
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias <your-ap>-ext-s3alias --stack-name sfn-agentcore-tools

# 정리
./scripts/deploy-stepfunctions-agentcore.sh --cleanup --stack-name sfn-agentcore-tools
```

대화 예시와 검증 절차는 [docs/demo-guide.md](docs/demo-guide.md)에 있습니다.

## Human Review 임계값

Processing Lambda는 `shared/human_review.py`로 요약 신뢰도를 평가합니다.

| 신뢰도 | 판정 |
|---|---|
| `>= 0.85`(기본 `HUMAN_REVIEW_AUTO_APPROVE_THRESHOLD`) | AUTO_APPROVE |
| `>= 0.30`(기본 `HUMAN_REVIEW_REJECT_THRESHOLD`) 및 `< 0.85` | HUMAN_REVIEW |
| `< 0.30` | REJECT |

임계값은 환경 변수로 재정의할 수 있습니다. 판정은 결과에 포함될 뿐이며 이 패턴은
자동으로 최종 판단을 내리지 않습니다.

## 데이터 분류

Report Lambda는 출력에 `shared/data_classification.py` 기반 `data_classification`
레이블을 붙입니다(기본 `INTERNAL`, `DATA_CLASSIFICATION`으로 변경).

## Governance Note

- 에이전트가 담당하는 것은 실행 판단과 상태 확인뿐입니다. 순서·분기·승인은 상태
  머신이 보장하며 에이전트가 건너뛰거나 재정렬할 수 없습니다.
- 고정된 상태 머신 ARN은 노출되지 않으므로 다른 상태 머신을 시작할 수 없습니다.
- AI 요약·분류는 **보조 신호**이며 최종 판단이 아닙니다. 신뢰도가 임계값 미만이면
  Human Review로 보냅니다.
- 작업 토큰 작업(`SendTaskSuccess` 등)은 IAM으로 리소스를 제한할 수 없어 여기서는
  노출하지 않습니다.
- 이는 거버넌스 지침이며 법률·컴플라이언스 판단을 대체하지 않습니다.

## 테스트

```bash
python3 -m pytest solutions/genai/stepfunctions-agentcore-tools/tests/ -v
```

## 알려진 주의점

동일 리전 제약, 작업당 하나의 pin, 일본어 입력의 `?` 깨짐과 `\uXXXX` 회피, Cedar의
`input` 조건 제약은 [docs/demo-guide.md](docs/demo-guide.md#既知の注意点)에 정리되어 있습니다.

## 참고

- [AWS Step Functions as Connector Target(공식)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- [AWS Step Functions workflows now available as AI agent tools(What's New)](https://aws.amazon.com/about-aws/whats-new/2026/10/step-functions-workflows-ai-agent-tools/)
