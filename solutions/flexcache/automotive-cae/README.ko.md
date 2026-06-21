# Automotive CAE — 시뮬레이션 결과 분석

🌐 **Language / 언어**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 개요

자동차 CAE(Computer-Aided Engineering) 시뮬레이션 결과의 자동 분석 파이프라인입니다. FSx for ONTAP에서 S3 Access Points를 통해 솔버 출력(LS-DYNA, STAR-CCM+, Nastran 등)을 읽고 품질 검사, 통계 집계, 보고서 생성을 자동화합니다.

## 해결하는 문제

| 문제 | 솔루션 |
|------|--------|
| 시뮬레이션 결과의 수동 검토 | 자동 품질 검사 + AI 요약 |
| 파일 서버에 분산된 솔버 출력 | S3 AP를 통한 중앙 집중식 검색 |
| 교차 시뮬레이션 분석 부재 | Athena/Glue 통합으로 트렌드 분석 |
| HPC 클러스터의 느린 데이터 접근 | 컴퓨팅 근처의 FlexCache로 빠른 읽기 |

## 지원 솔버

| 솔버 | 출력 형식 | 추출 메트릭 |
|------|-----------|-------------|
| LS-DYNA | d3plot, binout | 에너지, 변위, 응력 |
| STAR-CCM+ | .sim, .csv | 유속, 압력, 온도 |
| Nastran | .op2, .f06 | 모드 주파수, 응력 |
| Abaqus | .odb | 변위, 응력, 변형률 |
| OpenFOAM | postProcessing/ | 잔차, 힘 계수 |

## 성공 지표

| 지표 | 목표 |
|------|------|
| 실행당 처리 솔버 출력 | > 50 파일 |
| 품질 검사 통과율 | > 85% |
| 보고서 생성 시간 | < 3분 |
| 실행당 비용 | < $5 |
| Human Review 비율 | < 15% (품질 불합격 케이스) |

---

## Governance Note

> 본 패턴은 기술 아키텍처 가이던스를 제공합니다. 법적, 컴플라이언스, 규제 관련 조언이 아닙니다. 조직은 적격한 전문가에게 상담하십시오.
