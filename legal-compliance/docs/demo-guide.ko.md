# 파일 서버 권한 감사 — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

본 데모는 파일 서버의 과도한 접근 권한을 자동 감지하는 감사 워크플로우를 시연합니다.

**핵심 메시지**: 수주가 걸리는 파일 서버 권한 감사를 자동화하여 과도한 권한 리스크를 즉시 가시화합니다.

**예상 시간**: 3–5 min

---

## Workflow



---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 문제 제기: 수천 개 폴더의 권한 감사를 수동으로 수행하는 것은 비현실적

### Section 2 (0:45–1:30)
> 워크플로우 트리거: 대상 볼륨을 지정하고 감사 시작

### Section 3 (1:30–2:30)
> ACL 분석: ACL을 자동 수집하고 정책 위반 감지

### Section 4 (2:30–3:45)
> 결과 검토: 위반 건수와 리스크 레벨 즉시 파악

### Section 5 (3:45–5:00)
> 컴플라이언스 보고서: 우선순위별 액션을 포함한 감사 보고서 자동 생성

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 워크플로우 오케스트레이션 |
| Lambda (ACL Collector) | NTFS ACL 메타데이터 수집 |
| Lambda (Policy Checker) | 정책 위반 규칙 매칭 |
| Lambda (Report Generator) | Bedrock 감사 보고서 생성 |
| Amazon Athena | 위반 데이터 SQL 분석 |

---

*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*
