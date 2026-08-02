# 파일 포털 — 사용자 가이드

> 🌐 Language: [English](../en/portal-user-guide.md) | [日本語](../ja/portal-user-guide.md) | **한국어** | [简体中文](../zh-CN/portal-user-guide.md) | [繁體中文](../zh-TW/portal-user-guide.md) | [Français](../fr/portal-user-guide.md) | [Deutsch](../de/portal-user-guide.md) | [Español](../es/portal-user-guide.md)

이미 배포된 File Portal에 초대된 최종 사용자를 위한 가이드입니다. 이 문서는 포털 관리자가 배포를 완료하고 계정을 생성한 상태를 전제합니다 — AWS CLI 액세스나 배포 지식은 필요하지 않습니다.

**이 포털의 기능**: VPN이나 SMB/NFS 클라이언트 설정 없이 브라우저에서 NAS 파일을 탐색하고, AI/ML 분석을 실행하며, 결과를 확인하고, 데이터 보호 상태를 점검할 수 있습니다.

---

## 시작하기

### 1. 로그인

1. 관리자가 제공한 포털 URL을 엽니다
2. 이메일과 비밀번호를 입력합니다 (설정에 따라 제공받았거나 직접 등록한 정보)
3. MFA가 활성화된 경우, 인증 앱의 TOTP 코드를 입력합니다
4. 첫 로그인 시 **Welcome Modal**이 3가지 핵심 기능을 안내합니다:
   - 📂 파일 탐색 — 브라우저에서 NAS 파일 탐색
   - ⚡ AI 처리 — 파일을 선택하고 워크플로우 실행
   - 🔒 데이터 보호 — 스냅샷, 잠금, 랜섬웨어 상태

> **팁**: "다시 표시하지 않음"을 체크하면 이후 로그인 시 Welcome Modal을 건너뜁니다.

### 2. 포털 레이아웃

```
┌─────────────────────────────────────────────────────────┐
│ [☰] File Portal              🌐 KO ▾   user@example.com │
├───────────────┬─────────────────────────────────────────┤
│ 사이드바      │  메인 콘텐츠                            │
│ (내비게이션)  │                                         │
│               │                      AI 어시스턴트 패널 →│
└───────────────┴─────────────────────────────────────────┘
```

- **좌측 사이드바**: 탐색, AI & 처리, 데이터 보호, 관리 그룹별 내비게이션
- **메인 콘텐츠**: 활성 섹션 (사이드바 항목 클릭 시 변경)
- **우측 패널**: AI 어시스턴트 (All Files에서 파일 선택 시 표시)
- **상단 바**: 언어 전환, 사용자 이메일, 로그아웃

### 3. 언어

상단 바의 🌐 언어 선택기를 클릭하면 8개 언어 간 전환이 가능합니다: 日本語, English, 한국어, 简体中文, 繁體中文, Français, Deutsch, Español. 즉시 전환되며 페이지 새로고침이 필요 없습니다.

---

## 탐색 — 파일 작업

### All Files

기본 파일 브라우저입니다. S3 Access Point를 통해 FSx for ONTAP 볼륨의 내용을 표시합니다.

| 작업 | 방법 |
|------|------|
| 폴더 탐색 | 폴더 이름 클릭 |
| 상위 레벨로 이동 | 파일 목록 상단의 `..` 클릭 |
| 이미지 미리보기 | 이미지 파일 옆의 🖼️ 아이콘 클릭 |
| PDF 미리보기 | 📕 아이콘 클릭 — 브라우저 내장 뷰어로 열림 |
| Word 문서 미리보기 | 📝 아이콘 클릭 — 브라우저에서 렌더링 |
| 파일 다운로드 | 📄 아이콘 클릭 |
| 공유 링크 생성 | 🔗 클릭 → TTL 선택 (5분 / 15분 / 1시간) → URL 복사 |
| 파일에 대해 AI에 질문 | 파일 선택 → 우측 AI 패널에 질문 입력 |
| 이미지에서 객체 감지 | 이미지 선택 → AI 패널에서 "Detect Objects" 클릭 |
| 이 폴더 처리 | 파일 목록 위의 ⚡ 버튼 클릭 |

**PHI 보호 폴더**: `/dicom/`, `/phi/`, `/pii/` 등의 폴더로 이동하면 AI 처리 버튼에 `🚫 PHI — AI Blocked`가 표시됩니다. 이는 안전 가드레일로, 권한에 관계없이 이러한 폴더의 파일을 AI 서비스로 보낼 수 없습니다.

### Favorites

파일 목록에서 ⭐ 아이콘을 클릭하여 자주 액세스하는 파일을 고정합니다. 고정된 파일은 Favorites 섹션에서 빠르게 접근할 수 있습니다.

### Recent

최근에 조회, 다운로드 또는 AI 쿼리한 파일을 상대적 시간 표시("3분 전", "2시간 전")로 보여줍니다. 자신의 기록만 표시되며, 다른 사용자의 활동은 보이지 않습니다.

### Upload

Storage Browser for S3 기반의 드래그 앤 드롭 파일 업로드. 추가 기능:
- 폴더 생성
- 파일 복사 및 삭제
- 다중 파일 업로드 (파일당 최대 50 GB)

---

## AI & 처리

### AI Processing

폴더 또는 파일 세트에 대해 AI/ML 워크플로우를 실행합니다.

1. 드롭다운에서 처리 패턴을 선택합니다 (예: Legal Compliance, Financial IDP, Semiconductor EDA)
2. 입력 접두사를 설정합니다 (All Files에서 ⚡를 클릭한 경우 미리 입력됨)
3. **Start Processing** 클릭
4. Job History로 이동하며 5초마다 상태가 업데이트됩니다

### Job History

모든 과거 처리 작업의 상태, 타임스탬프, 출력 데이터를 확인합니다.

| 상태 | 의미 |
|------|------|
| 🔵 RUNNING | 처리 진행 중 |
| 🟢 SUCCEEDED | 완료 — 클릭하여 결과 확인 |
| 🔴 FAILED | 오류 발생 — 출력에서 상세 내용 확인 |
| ⚪ TIMED_OUT | 최대 실행 시간 초과 |

작업을 클릭하면 출력이 펼쳐집니다. 결과가 볼륨에 다시 기록된 경우, All Files의 출력 폴더로 바로 이동하는 링크가 제공됩니다.

### Analytics

Amazon Athena를 사용하여 데이터에 대한 SQL 쿼리를 실행합니다. 이 기능은 관리자가 설정한 Glue Data Catalog 테이블이 필요합니다.

---

## 데이터 보호

### Snapshots

볼륨 스냅샷 — 데이터의 특정 시점 복사본을 확인합니다.

- **목록**: 생성 타임스탬프와 함께 사용 가능한 모든 스냅샷 확인
- **복원**: "Restore"를 클릭하면 스냅샷에서 FlexClone(즉시 생성되는 공간 효율적 복사본)을 생성합니다. 클론은 자체 S3 Access Point를 가지며 수 초 내에 사용 가능합니다.

### Lock (WORM)

3가지 메커니즘에 걸친 데이터의 불변성 상태를 확인합니다:

| 탭 | 표시 내용 |
|----|-----------|
| ONTAP SnapLock | 볼륨이 Compliance 또는 Enterprise 모드를 사용하는지, 보존 기간 |
| S3 Object Lock | AI 출력 버킷에 객체 수준 WORM이 활성화되어 있는지 |
| Tamperproof Snapshot | 잠긴 스냅샷과 만료 시점 |

> **참고**: 잠금 설정 구성은 `storage-admin` 역할이 필요합니다. 일반 사용자는 이 섹션에 읽기 전용 액세스 권한을 가집니다.

### ARP/AI (랜섬웨어 보호)

볼륨의 자율 랜섬웨어 보호 상태를 확인합니다.

| 표시 내용 | 의미 |
|-----------|------|
| 🟢 No threats | 모든 볼륨 정상 |
| 🔴 Threat detected | ARP/AI가 의심스러운 활동을 감지함 |
| Incident badge | 현재 대응 단계 표시 (Detected → Contained → Investigating → Resolved) |

위협이 감지되고 `storage-admin` 그룹에 속해 있다면, 이 패널에서 직접 격리 조치를 실행할 수 있습니다.

---

## 관리 (`storage-admin` 그룹 필요)

이 섹션은 계정이 `storage-admin` Cognito 그룹에 속한 경우에만 표시/작동합니다.

### Storage Dashboard

관리자 랜딩 페이지. 4개의 카드 표시:
- 💾 볼륨 수 + 평균 용량 사용률
- 🛡️ ARP 보호 볼륨 + 활성 위협
- 🔐 잠긴(변조 방지) 스냅샷
- 📊 스토리지 효율성 비율

카드를 클릭하면 상세 패널로 이동합니다.

### Resources

10개의 관리 영역을 카테고리별로 구성한 카드 그리드 관리 패널:

| 카테고리 | 패널 |
|----------|------|
| 스토리지 | Volumes, Qtrees, Quotas, Efficiency |
| 액세스 제어 | Export Policies, CIFS Shares, QoS |
| 보호 | ARP Admin, Snapshot Admin, SnapLock |

### Version Diff

두 스냅샷 간의 파일 내용을 나란히 비교합니다.

### Audit Trail

CloudTrail S3 데이터 이벤트를 쿼리하여 "누가, 언제, 무엇에 접근했는지" 확인합니다.

---

## 팁 & FAQ

**Q: 일부 패널에서 "ONTAP Connection Required"가 표시됩니다.**
A: 포털이 DemoMode이거나 관리자가 아직 VPC 연결을 구성하지 않은 것입니다. 파일 탐색과 AI 기능은 정상 작동합니다 — ONTAP 전용 패널(Snapshots, ARP, Lock)만 연결이 필요합니다.

**Q: AI 처리 버튼에 "PHI — AI Blocked"가 표시됩니다.**
A: 보호된 폴더(`/dicom/`, `/phi/`, `/pii/` 등)에 있습니다. 이는 의도된 동작으로, 이 경로의 파일은 AI 서비스로 보낼 수 없습니다. AI 기능을 사용하려면 비보호 폴더로 이동하세요.

**Q: 공유 링크가 빨리 만료됩니다.**
A: 공유 링크는 선택한 유효 시간(5분, 15분, 또는 1시간)의 Presigned URL을 사용합니다. 장기 공유가 필요하면 관리자에게 Nextcloud 연동에 대해 문의하거나 TTL 옵션을 조정하세요.

**Q: NFS/SMB로 업로드한 파일이 보이지 않습니다.**
A: 즉시 표시되어야 합니다 (ONTAP은 크로스 프로토콜 강력한 일관성을 보장합니다). 파일 목록을 새로고침해 보세요. 여전히 보이지 않으면 하위 폴더에 있을 수 있습니다 — 경로를 확인하세요.

**Q: 모바일에서 포털을 사용할 수 있나요?**
A: 네. 좁은 화면에서는 사이드바가 접힙니다. 모든 기능이 모바일 브라우저에서 작동하지만, 데스크톱에 최적화되어 있습니다.

**Q: 비밀번호를 변경하려면 어떻게 하나요?**
A: Cognito Hosted UI를 사용하거나 관리자에게 재설정을 요청하세요.

---

## 관련 문서

| 문서 | 대상 | 용도 |
|------|------|------|
| [Getting Started (Deploy)](../../solutions/amplify-portal/docs/GETTING-STARTED.md) | 관리자 | 포털을 처음부터 배포 |
| [Admin Demo Guide](admin-resource-management-demo.md) | 스토리지 관리자 | 관리 작업 E2E 데모 |
| [AI Features Quick Start](ai-features-quick-start.md) | 모든 사용자 | Bedrock, Rekognition, Athena 사용해보기 |
| [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) | 개발자 | 아키텍처 및 커스터마이징 |
| [Authorization Model](portal-authorization-model.md) | 보안 팀 | Cognito 그룹, IAM, 파일 수준 액세스 |
| [Compliance Guide](portal-compliance-guide.md) | 보안/컴플라이언스 | 규제 제어 검증 |
| [Quick Reference](portal-quick-reference.md) | 모든 역할 | 1페이지 요약 시트 |
