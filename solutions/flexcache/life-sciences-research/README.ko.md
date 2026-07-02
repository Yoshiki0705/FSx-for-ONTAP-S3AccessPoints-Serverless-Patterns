# Life Sciences Research — 데이터 분류 및 메타데이터 추출

🌐 **Language / 언어**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 개요

생명과학 연구 데이터(현미경 이미지, 시퀀스 데이터, 연구 논문)의 자동 분류 및 메타데이터 추출 파이프라인입니다. 다중 사이트 연구 데이터 공유를 위해 FlexCache를 활용합니다.

## 해결하는 문제

| 문제 | 솔루션 |
|------|--------|
| 파일 서버에 정리되지 않은 연구 데이터 | 데이터 유형별 자동 분류 |
| 수동 메타데이터 카탈로깅 | AI 기반 메타데이터 추출 |
| 원격 연구 사이트의 느린 데이터 접근 | 다중 사이트 공유를 위한 FlexCache |
| 관련 데이터셋 찾기 어려움 | 검색 가능한 메타데이터 카탈로그 |

## 지원 데이터 형식

| 카테고리 | 형식 | 설명 |
|----------|------|------|
| 현미경 이미지 | .tiff, .nd2, .czi | 형광, 공초점, 전자 현미경 |
| 시퀀스 데이터 | .fastq, .bam, .vcf | NGS 시퀀싱 결과 |
| 연구 논문 | .pdf | 문헌, 프로토콜, 보고서 |
| 구조 데이터 | .pdb, .cif | 단백질 구조 |

## FlexCache의 역할

- **다중 사이트 공유**: 본사 → 각 연구 사이트
- **대규모 데이터셋**: 현미경 이미지(수백 GB) 캐싱
- **협업**: 여러 팀이 동일 데이터셋을 병렬 분석

## 성공 지표

| 지표 | 목표 |
|------|------|
| 실행당 분류 파일 수 | > 500 파일 |
| 분류 정확도 | > 85% |
| 메타데이터 추출 성공률 | > 90% |
| 파일당 처리 시간 | < 5초 |
| Human Review 비율 | < 10% (저신뢰도 분류) |

---

## 배포

AWS SAM CLI로 배포합니다 (플레이스홀더는 환경에 맞게 교체하세요):

```bash
# 전제 조건: AWS SAM CLI 필요. 'sam build'가 함수 코드를 자동으로 패키징합니다.
sam build

sam deploy \
  --stack-name fsxn-life-sciences-research \
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
