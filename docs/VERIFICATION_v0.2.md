# v0.2 검증 결과와 적용 경계

기준일: 2026-10-02, Asia/Seoul. 회사별 도입 판단, 신원·승인 결속, 데이터 계약과 문서 수명주기, 평가 대상 결합을 구현하고 로컬 검사와 설치된 패키지 실행을 통과했습니다. 현재 범위는 합성 데이터의 참조 런타임입니다.

회사 간 문서 ID 선점·존재 탐지 P2까지 수정한 새 검사에서 **325 passed**, 타입 검사 **0 errors / 0 warnings**, Ruff와 포맷 검사를 통과했습니다. 새 wheel의 실제 HTTP·CLI·재시작과 추가 namespace HTTP 검증, 독립 Sol namespace 검토도 통과했습니다. **현재 소스의 91개 파일을 고정한 실제 Opus 5.5 max 최종 감사는 PASS**입니다. 앞선 최초 구현·142개 파일 감사의 PASS와 119개 파일 hardening 감사의 NEEDS_FIX도 변경 없이 보존합니다.

## 실행으로 확인한 결과

| 검사 | 결과와 의미 | 재현 증거 |
|---|---|---|
| 통합 검사 | 325 tests, Ruff ALL, 103개 Python 파일 포맷, basedpyright all 통과 | [최종 검사 로그](evidence/v0.2.0/namespace-checks.txt) |
| wheel 독립 실행 | 새 wheel 설치 후 runtime 설정 검사와 support 데모 통과 | [최종 빌드·실행 로그](evidence/v0.2.0/namespace-wheel.txt) |
| 실제 HTTP·CLI·재시작 | CLI subprocess와 loopback uvicorn으로 권한 거부, 제한 문서 metadata 비노출, 중복 snapshot 입력 거부와 상태 불변, import/replay, retire/tombstone, 검색 제외, 재시작, 검토·승인·중복 실행·되돌리기·감사 검증 | 같은 wheel 로그, `tests/v02_runtime_smoke.py` |
| 설치 소스 일치 | 설치된 wheel의 Python 모듈을 현재 소스와 byte 단위로 대조 | 같은 wheel smoke의 내부 assertion |
| 실제 쓰기 ACL·삭제·namespace HTTP | 다른 그룹의 네 변경을 동일 404로 거부하고 상태 유지; 잘못된 namespace ID 네 모양을 valid/empty groups 각각 같은 422 본문으로 거부; 빈 groups 상태 불변, actor별 replay 투영, live 계약 version 변경 후 tombstone 정리 | 같은 최종 wheel 로그, `tests/v02_hardening_smoke.py` |
| 변경 Python 품질 규칙 | 73개 변경 관련 파일에서 no-excuse 위반 없음 | [최종 규칙 검사 로그](evidence/v0.2.0/namespace-no-excuse.txt) |
| 업종 재현 | 구매·고객지원·입사서류 모두 진단·검색·독립 승인·멱등 실행·복구·감사 통과 | [최종 합성 업종 결과](evidence/v0.2.0/domain-smoke-namespace/synthetic-demos.json) |
| 독립 구현 검토 | 실제 재현한 12개 결함의 수정과 회귀를 다시 확인, 표적 66개 검사 통과 | [독립 검토](evidence/v0.2.0/independent-review.md) |
| 독립 delta 검토 | 권고 보완 범위 PASS, 표적 26 tests와 실제 도입 HTTP·CLI 관찰 | [새 독립 검토](evidence/v0.2.0/independent-delta-review.md) |
| 독립 hardening 검토 | 빈 groups 고립 P1을 재현·수정한 뒤 지정 범위 PASS; 표적 45 tests와 핵심 6 tests, HTTP uniform 404, legacy 빈 ACL의 fail-closed와 상태 불변 | [최종 독립 검토](evidence/v0.2.0/independent-hardening-review.md) |
| 독립 namespace 검토 | 회사 간 ID 선점·존재 탐지 P2의 지정 범위 PASS; 표적 52 tests, same-suffix 공존, 점 경계, legacy cleanup, 배치 rollback과 문서 경계 대조 | [namespace 독립 검토](evidence/v0.2.0/independent-namespace-review.md) |

테스트 개수는 검사 범위를 나타냅니다. 실제 회사의 정확도, 누출 확률, 처리 성능이나 ROI를 보증하는 수치로 사용하지 않습니다. 모델 wire 검사는 실제 loopback의 가짜 Ollama 서버와 gateway MockTransport를 사용합니다. 실제 LLM 추론 품질은 회사별 파일럿에서 평가해야 합니다.

[최종 증거 인덱스](evidence/v0.2.0/namespace-verification-index.json)는 TQE capsule ID, 원래 로그 SHA-256과 UTF-8/LF 전달 파일의 실제 hash를 각각 기록합니다. [검사 소스 manifest](evidence/v0.2.0/namespace-tested-source-manifest.json)는 모든 103개 Python 파일과 실행 설정의 hash를 고정합니다. [P2 해결·로그 판독 기록](evidence/v0.2.0/namespace-resolution.md)은 PowerShell이 uv의 빌드 진행 stderr를 `NativeCommandError`로 감싼 기록과 실제 종료·성공 신호를 구분합니다. ZIP 내부 manifest는 전달 파일의 byte와 hash를 증명합니다. [최초 286개 기록](evidence/v0.2.0/verification-index.json), [300개 보완 기록](evidence/v0.2.0/delta-verification-index.json), [316개 기록](evidence/v0.2.0/hardening-verification-index.json)도 보존하며 현재 namespace 소스의 증거로 혼용하지 않습니다.

## v0.1에서 강화한 경계

신원은 서버 등록 Principal에서 결정합니다. 기업 JWT는 고정 issuer/audience/공개키와 사용자·서비스 클라이언트 매핑을 확인하며, 실패 JWT를 opaque 인증으로 다시 시도하지 않습니다. 사용한 credential을 transaction 안에서 다시 인증해 다른 인증 방식의 동일 Principal이 남아 있어도 회수된 토큰의 쓰기를 차단합니다.

승인은 사람이 수행해야 하며 제안자와 같은 사람의 다른 계정은 승인할 수 없습니다. 제안·승인 당시 actor kind와 person ID를 고정하고 현재 매핑과 대조합니다. 계정 이름이 다른 사람에게 재할당되면 미완료 작업이 차단됩니다. 새 결속 필드가 없는 기존 pending 작업은 재제안·재승인이 필요하며, 완료된 v0.1 기록의 hash와 종단 replay/rollback 호환은 유지합니다.

managed 문서는 tenant·source·contract 소유권과 계약 version/hash에 결합됩니다. 계약이 바뀌면 기존 문서를 검색·승인 근거에서 제외하고, 변경 요청은 transaction 진입 후 live 계약을 다시 확인합니다. 관측 시각은 단조 증가해야 하며 과거 source version은 다시 사용할 수 없습니다. 실패 배치에서 문서·버전 이력·리비전·watermark·감사는 함께 되돌아갑니다.

지식 상태의 문서 목록은 실제 ACL과 관리 가능한 현재 계약으로 제한됩니다. schema 4 내부 ACL snapshot은 retire/tombstone에도 유지하며, 안전하게 ACL을 복원할 수 없는 기존 metadata는 숨깁니다. tenant 및 허용 source의 revision/hash는 CAS용 집계로 남아 변경 여부가 드러날 수 있습니다. 가져오기는 변경 문서만 담는 delta이고 중복 ID를 요청 단계에서 거부하며 누락을 자동 삭제로 해석하지 않습니다. 지역·모델·도구 정책 증거 UNKNOWN은 BLOCKED이고, REPORTED는 자기신고이지 검증 완료가 아닙니다.

기존 문서의 upsert·ACL 변경·retire·tombstone은 저장 ACL의 tenant/group/clearance를 검사합니다. 권한 없음과 문서 없음은 동일한 404이며, 거부된 배치의 문서·revision·audit·accepted-version history는 불변입니다. 관리 문서 upsert candidate와 ACL 변경의 빈 groups는 422로 거부하고 nonempty 그룹으로의 self-revoke는 유지합니다. legacy 빈·불명 ACL은 자동으로 권한을 복원하지 않고 숨김·404를 유지하므로 담당자의 통제된 migration이 필요합니다.

retire와 ACL 변경은 현재 계약의 exact version/hash 결속을 요구합니다. 같은 stable owner binding의 upsert는 새 source version으로 현재 계약에 재결합할 수 있으며, tombstone은 version/hash drift 후에도 중간 재게시 없이 정리합니다. 신규 및 replay 응답의 `documents`는 현재 권한과 결속으로 투영하지만, 포함된 meta와 상위 revision/hash·원본 receipt·audit는 역사적 기록을 유지합니다.

managed upsert는 저장소 조회 전에 문서 ID의 마지막 점 앞 prefix를 계약 tenant와 정확히 비교하고, separator·suffix 누락과 다른 prefix는 422로 거부합니다. 전역 PK는 유지하며 같은 tenant 내부의 ID 배정 상태 추론·선점은 신뢰 발급자와 계약별 할당으로 관리해야 합니다. 과거 bootstrap·managed ID의 owner/prefix 충돌은 다중 tenant 도입 전에 통제된 migration으로 정리합니다. 기존 비정규 ID는 자동 변경하지 않고 현재 권한·binding에 따른 retire/tombstone cleanup을 유지합니다. 계약 제거 전 정리 또는 같은 owner 계약 재등록 후 drift cleanup 절차와 관리자의 ACL 확대 권한도 명시했습니다.

미분류 질문의 서버 등급 하한은 RESTRICTED입니다. 외부 전송은 회사가 검증한 입력 분류와 반출 정책을 운영 설정에 반영한 뒤에 허용해야 합니다. JSON CLI 입력에는 허용된 로컬 root, reparse·UNC·device·ADS 거부와 크기 제한을 적용합니다. 검색 비교는 NFC로 정규화하고 인용 원문과 해시는 그대로 보존합니다.

평가 추천은 pack·데이터 계약·모델·프롬프트·정책·case set·rubric·코드의 선언 버전과 digest에 결합합니다. 전달한 criteria와 fixture 집합을 다시 대조하며 중복 case ID와 평균 반올림에 따른 임계값 왜곡을 막습니다. 합성 사례, 미확인 검토자, manifest 누락·불일치와 안전·권한·삭제 veto가 남아 있으면 현업 검토 자격을 부여하지 않습니다.

## 모델 협업의 실제 범위

설계 호출의 실제 모델은 `claude-opus-5-5`, CLI 추론 인자는 `max`, 응답은 `is_error=false`였습니다. 최초 판정 **NEEDS_FIX**는 소스 읽기·테스트 실행 없이 제시한 설계 가설입니다. [세션 메타데이터를 제거한 설계 결과](evidence/v0.2.0/design-review-public.json)를 보존합니다. 원본 SHA-256은 `62863562c53ee98f499e96cbe114477d2503eac87572f00dd340d5189b1f4732`입니다.

최초 구현 감사는 새로운 Opus 호출에 코드·테스트·문서·설정·실행 증거 **122개 파일**을 공급했습니다. [감사 입력 manifest](evidence/v0.2.0/final-audit-input-manifest.json)와 [전체 감사 입력](evidence/v0.2.0/final-audit-request.md)에 원래 소스 줄과 SHA-256을 보존했습니다. [실제 판정은 PASS](evidence/v0.2.0/final-audit-public.json)이며, 원본 SHA-256은 `cf896db51f480b2390378ce942367504867bf012a01a8dd545686046affe537f`입니다. 이 감사는 정적 검토이며 실제 검사 실행은 Codex가 담당합니다. 권고 보완 후의 소스에는 새 감사 입력과 판정을 별도로 남깁니다.

첫 권고 보완 후에는 [142개 파일 manifest](evidence/v0.2.0/final-delta-input-manifest.json)와 [전체 재감사 입력](evidence/v0.2.0/final-delta-request.md)을 새로운 Opus 5.5 max 호출에 공급했습니다. [재감사 판정도 PASS](evidence/v0.2.0/final-delta-public.json)이며, 원본 출력 SHA-256은 `0cd20a87f0d2d5abdfad64195b5ef46f11fe12e87820ed5b514c375907a1172e`입니다. 추가 비차단 권고인 기존 문서의 쓰기 ACL 검사·현재 권한 receipt 투영과 계약 version 변경 후 tombstone 경로를 모두 구현하고 별도 검증했습니다.

hardening 감사에는 [119개 파일 manifest](evidence/v0.2.0/hardening-input-manifest.json)와 [전체 입력](evidence/v0.2.0/hardening-request.md)을 공급했습니다. 모든 runtime 49개 Python 파일과 지식 수명주기·핵심 API/CLI/credential·설치 smoke 27개 테스트 파일의 원문, 문서·설정·실행 증거를 포함합니다. [실제 판정은 NEEDS_FIX](evidence/v0.2.0/hardening-public.json)이며 원본 SHA-256은 `0148caf96643760857d99a9f21f989ac2a58657e2ca5ac514a736997e33f9a23`입니다. 기존 다섯 보완이 성립한다는 검토와 별도로 전역 문서 ID의 회사 간 선점·존재 탐지 P2를 지적했습니다. 코드를 수정하고 새 증거·새 호출로 최종 판정을 확인합니다. 앞선 PASS를 바뀐 소스의 판정으로 재사용하지 않습니다.

namespace 수정 후에는 [91개 파일 manifest](evidence/v0.2.0/namespace-input-manifest.json)와 [전체 입력](evidence/v0.2.0/namespace-request.md)을 새 Opus 5.5 max 호출에 공급했습니다. 현재 runtime 49개 Python 파일 전체와 표적 테스트·실제 설치 helper 12개, 관련 공개 계약·실행 증거를 포함합니다. 나머지 테스트는 전체 325개 실행 증거로 구분하고, 변경되지 않은 lock은 이전 frozen 입력의 hash와 대조합니다. [실제 최종 판정은 PASS](evidence/v0.2.0/namespace-public.json)이며 원본 출력 SHA-256은 `de82afffd7e709cda2ad4617566b1fd4847c27f59da367fa400b543c19ace5be`입니다. 이 판정은 공급 소스의 정적 감사이고 회사 배포·모델 정확도 인증이 아닙니다.

최종 감사의 비차단 증거 권고에 따라 독립 52개 검사의 정확한 실행 명령과 8개 테스트 파일 해시를 [보완 기록](evidence/v0.2.0/namespace-followup-verification.json)에 결속했습니다. 기존 독립 리뷰는 변경하지 않았고 테스트를 재실행한 것으로 표현하지 않습니다. 같은 기록은 최종 Opus 입력에서 빠진 학습 가이드의 managed 명령·namespace 설명과 v0.2 JSON 예제의 문서 ID를 Codex가 별도로 대조한 범위를 구분합니다.

추가 회귀 강화 후보는 잘못된 namespace 입력 뒤 owner의 정상 생성·source history·revision 불변을 하나의 pytest 시나리오로 묶는 검사, 빈 접미부의 pytest 사례, registry 제거 후 새 HTTP 요청의 404 경로입니다. 이번 판정의 차단 결함은 없으며 이 후보들을 구현·검증 완료로 세지 않습니다. 현재 실제 HTTP의 8개 거부 조합·상태 불변, 독립 DB probes, 계약 제거 중 transaction 경계의 409 회귀와 구분합니다.

## 회사 환경에서 확인할 조건

실제 원천 connector와 ACL·삭제·보존 전파, IdP/SSO/MFA 및 키 운영, 모델 계약·리전·보관·라이선스, default-deny 네트워크, 현업 gold set과 검토자 독립성, 외부 ERP 쓰기의 멱등·복구, 백업 복원과 장애·부하는 해당 조직에서 검증해야 합니다. `eligible_for_field_review`는 입력 기반 추천이며 증거 원천의 진위나 배포 승인 권한을 제공하지 않습니다.

`tombstone`은 primary SQLite의 논리 레코드 본문을 제거합니다. SQLite/WAL·백업·provider의 물리 삭제를 증명하지 않습니다. 문서 read 검사는 ID·tenant·source version·content/access hash를 대조하며, 제목·객체 scope·유효기간·source URI·전체 document/state head와 DB 전체 재작성의 외부 무결성은 보장하지 않습니다. 감사 체인 검사도 audit event 연쇄 범위입니다. DB와 설정 파일의 운영자 ACL 및 호스트 무결성이 필요합니다.

## 재현과 다음 단계

```powershell
uv sync --frozen
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\check-package.ps1
```

회사 파일럿은 [v0.2 사용 가이드](V02_GUIDE.md), 분야 강화는 [업그레이드 가이드](UPGRADE_GUIDE.md), 코드의 실제 데이터·승인 흐름은 [학습 가이드](LEARNING_GUIDE.md)에 따라 진행합니다. [v0.1 증거](VERIFICATION.md)와 기존 ZIP은 역사적 기록으로 보존하며 v0.2 판정을 대신하지 않습니다.
