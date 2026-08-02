# 파일 포털 — 빠른 참조 카드

> 🌐 Language: [English](../en/portal-quick-reference.md) | [日本語](../ja/portal-quick-reference.md) | **한국어** | [简体中文](../zh-CN/portal-quick-reference.md) | [繁體中文](../zh-TW/portal-quick-reference.md) | [Français](../fr/portal-quick-reference.md) | [Deutsch](../de/portal-quick-reference.md) | [Español](../es/portal-quick-reference.md)

일상적인 포털 작업을 위한 1페이지 요약입니다. 인쇄하거나 북마크하세요.

---

## 내비게이션

| 사이드바 섹션 | 기능 |
|:---:|------|
| 📂 All Files | 탐색, 미리보기, 다운로드, 공유, AI Q&A |
| ⭐ Favorites | 고정된 파일 |
| 🕐 Recent | 접근 이력 |
| 📤 Upload | 드래그 앤 드롭 업로드 (최대 50 GB/파일) |
| ⚡ AI Processing | 폴더에 대한 AI/ML 워크플로 실행 |
| 📋 Job History | 과거 작업 결과 + 상태 |
| 📊 Analytics | Athena SQL 쿼리 |
| 📸 Snapshots | 특정 시점 복사본 + FlexClone 복원 |
| 🔒 Lock | SnapLock / S3 Object Lock / Tamperproof |
| 🛡️ ARP/AI | 랜섬웨어 보호 상태 |
| 🔧 Resources | 스토리지 관리 패널 (관리자 전용) |
| 🔄 Version Diff | 스냅샷 간 파일 비교 |
| 🔍 Audit Trail | 누가 언제 무엇에 접근했는지 |

---

## 일반 작업 (모든 사용자)

| 하고 싶은 것 | 방법 |
|-------------|------|
| 파일 탐색 | 사이드바 → 📂 All Files → 폴더 클릭 |
| PDF 미리보기 | 파일 옆의 📕 클릭 |
| Word 문서 미리보기 | 파일 옆의 📝 클릭 |
| 파일 다운로드 | 파일 옆의 📄 클릭 |
| 파일 링크 공유 | 🔗 클릭 → TTL 선택 → URL 복사 |
| AI에게 파일 질문하기 | 파일 선택 → 오른쪽 패널에 질문 입력 |
| 이미지 객체 감지 | 이미지 선택 → 오른쪽 패널에서 "Detect Objects" |
| 파일 업로드 | 사이드바 → 📤 Upload → 드래그 앤 드롭 |
| 폴더에 AI 실행 | All Files에서 파일 목록 위의 ⚡ 클릭 |
| 작업 결과 확인 | 사이드바 → 📋 Job History → 작업 클릭 |
| 스냅샷에서 복원 | 사이드바 → 📸 Snapshots → "Restore" 버튼 |
| 언어 전환 | 상단 바에서 🌐 클릭 |

---

## 일반 작업 (컴플라이언스 / 보안)

| 하고 싶은 것 | 방법 |
|-------------|------|
| 랜섬웨어 상태 확인 | 사이드바 → 🛡️ ARP/AI |
| WORM 잠금 확인 | 사이드바 → 🔒 Lock → SnapLock 탭 |
| 출력 버킷 잠금 확인 | 사이드바 → 🔒 Lock → S3 Object Lock 탭 |
| 잠긴 스냅샷 보기 | 사이드바 → 🔒 Lock → Tamperproof 탭 |
| 접근 감사 검토 | 사이드바 → 🔍 Audit Trail |
| PHI 가드레일 확인 | All Files → `/dicom/`으로 이동 → 버튼에 🚫 표시 |

---

## 일반 작업 (스토리지 관리자)

| 하고 싶은 것 | 방법 |
|-------------|------|
| 헬스 대시보드 보기 | 사이드바 → 🔧 Resources (대시보드가 먼저 표시됨) |
| 볼륨 관리 | Resources → Storage → Volumes |
| 내보내기 정책 구성 | Resources → Access Control → Export Policies |
| 볼륨에 ARP 활성화 | Resources → Protection → ARP Admin |
| 스냅샷 잠금 | Resources → Protection → Snapshot Admin → Lock 양식 |
| 침해된 사용자 차단 | 사이드바 → 🛡️ ARP/AI → Contain 탭 → Block SMB User |
| 해결 후 차단 해제 | 사이드바 → 🛡️ ARP/AI → Unblock 탭 |
| EMS 알림 확인 | Resources → (모니터링에 EMS 이벤트 표시) |

---

## 키보드 단축키

| 키 | 동작 |
|-----|------|
| `Tab` | 대화형 요소 간 이동 |
| `Enter` | 버튼 활성화 / 폴더 열기 |
| `Escape` | 모달 닫기 / 패널 닫기 |

---

## 상태 표시기

| 아이콘 | 의미 |
|:---:|------|
| 🟢 | 정상 / 위협 없음 / 해결됨 |
| 🔴 | 위협 탐지됨 / 오류 |
| 🟠 | 격리됨 (인시던트 진행 중) |
| 🟡 | 조사 중 |
| 🚫 | PHI — AI 차단됨 (가드레일 활성) |
| ⚠️ | 경고 (용량 > 85% 등) |

---

## 접근 레벨

| 그룹 | 할 수 있는 작업 | 할 수 없는 작업 |
|------|----------------|----------------|
| `authenticated` | 탐색, 다운로드, 업로드, AI, 보호 상태 보기 | 스토리지 설정 변경 |
| `storage-admin` | 위의 모든 것 + 볼륨 생성/삭제, 스냅샷 잠금, 사용자 차단, 정책 관리 | — |

---

## 빠른 문제 해결

| 증상 | 해결 방법 |
|------|-----------|
| "ONTAP Connection Required" | DemoMode에서는 정상입니다. 관리자에게 VPC 구성을 요청하세요. |
| AI 버튼에 🚫 표시 | PHI 보호 폴더에 있습니다. 다른 곳으로 이동하세요. |
| 공유 링크 만료됨 | 새 링크를 생성하세요 (🔗). 최대 TTL = 1시간. |
| NFS 쓰기 후 파일이 보이지 않음 | 파일 목록을 새로고침하세요. 즉시 표시되어야 합니다. |
| 무한 로딩 | 인터넷을 확인하세요. 로그아웃 → 로그인을 시도하세요. |

---

## 문서 안내

| 당신의 역할 | 시작 문서 |
|------------|-----------|
| 일반 사용자 (일상 업무) | [사용자 가이드](portal-user-guide.md) |
| 보안 / 컴플라이언스 담당자 | [컴플라이언스 가이드](portal-compliance-guide.md) |
| 스토리지 관리자 | [관리자 데모 가이드](admin-resource-management-demo.md) |
| IT 관리자 (배포) | [시작 가이드](../../solutions/amplify-portal/docs/GETTING-STARTED.md) |
| 개발자 (커스터마이즈) | [구현 가이드](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) |
