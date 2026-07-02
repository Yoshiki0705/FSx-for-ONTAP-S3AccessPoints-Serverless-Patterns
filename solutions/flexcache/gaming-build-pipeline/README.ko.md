# Gaming Build Pipeline — 에셋 품질 검사 및 로그 분석

🌐 **Language / 언어**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 개요

게임 개발을 위한 자동 에셋 품질 검사 및 빌드 로그 분석 파이프라인입니다. 글로벌 스튜디오 에셋 공유 및 CI/CD 파이프라인 통합을 위해 FlexCache를 활용합니다.

## 해결하는 문제

| 문제 | 솔루션 |
|------|--------|
| 수동 텍스처/에셋 품질 검토 | Rekognition 기반 자동 품질 검사 |
| 대규모 팀의 빌드 로그 분석 | AI 기반 로그 패턴 분석 (Bedrock) |
| 글로벌 스튜디오로의 느린 에셋 배포 | FlexCache로 글로벌 에셋 전달 |
| 품질 문제의 늦은 발견 | 빌드 파이프라인의 자동 품질 게이트 |

## 지원 게임 엔진

| 엔진 | 에셋 형식 | 검사 항목 |
|------|-----------|-----------|
| Unreal Engine 5 | .uasset, .umap | 텍스처 해상도, LOD 설정 |
| Unity | .prefab, .asset | 메시 버텍스 수, 머티리얼 참조 |
| Godot | .tscn, .tres | 씬 구조, 리소스 참조 |

## FlexCache의 역할

- **글로벌 에셋 전달**: 메인 스튜디오 → 지역 스튜디오
- **빌드 캐시**: CI/CD 파이프라인에서 빠른 에셋 읽기
- **버전 관리**: 에셋 버전 간 델타 전달

## 성공 지표

| 지표 | 목표 |
|------|------|
| 실행당 검사 에셋 수 | > 1,000 |
| 품질 검사 통과율 | > 90% |
| 빌드 로그 문제 감지율 | 100% (알려진 패턴) |
| 에셋당 처리 시간 | < 2초 |
| Human Review 비율 | < 5% (치명적 품질 불합격) |

---

## 배포

AWS SAM CLI로 배포합니다 (플레이스홀더는 환경에 맞게 교체하세요):

```bash
# 전제 조건: AWS SAM CLI 필요. 'sam build'가 코드와 공유 레이어를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name fsxn-gaming-build-pipeline \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region <your-region>
```

> **참고**: `template.yaml`은 SAM CLI (`sam build` + `sam deploy`) 를 통해 배포합니다.
> `aws cloudformation deploy` 명령으로 직접 배포하려면 `template-deploy.yaml`을 사용하세요 (Lambda zip 파일의 사전 패키징 및 S3 업로드가 필요합니다).

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적, 컴플라이언스, 규제 관련 조언이 아닙니다. 조직은 적격한 전문가에게 상담하십시오.
