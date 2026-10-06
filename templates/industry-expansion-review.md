# 업종팩 강화 검토서

공통 코어는 그대로 두고 업종의 용어·관계·규칙·근거·평가를 강화합니다. 표준이나 공개 사례는 후보를 제공하지만 회사의 실제 규칙을 대신하지 않습니다.

## 1. 변경 범위

- 업종 / 회사 / 업무:
- 해결할 실제 실패 사례:
- 바꾸려는 객체·관계·규칙·문서·행위:
- 유지할 공통 코어 계약:
- 업무 책임자 / 데이터 소유자 / 현업 승인자:

## 2. 용어·관계·규칙 출처

| 후보 | 정의·관계·규칙 | 출처와 버전 | 회사 원천 필드 | 예외 | 현업 승인 |
|---|---|---|---|---|---|
|  |  |  |  |  | 대기 / 승인 / 반려 |

- 참조 표준: FIBO / FHIR / OPC UA / GS1 EPCIS / 기타
- 라이선스·사용 조건:
- 회사 용어와 표준 용어가 다를 때의 매핑 책임자:
- 표준 업데이트 시 호환·마이그레이션 계획:

## 3. source contract

| 항목 | 값 | 확인자 |
|---|---|---|
| 원천 식별자·URI·인증 방식 |  |  |
| 계약 ID·버전·소유자 |  |  |
| 현재 계약 canonical hash·변경 절차 |  |  |
| 객체 범위와 기본 키 |  |  |
| managed 문서 ID `<tenant>.<점 없는 접미부>`·신뢰 가능한 할당자·계약별 접미부 규칙 |  |  |
| ACL·목적·민감도 |  |  |
| 갱신 주기·보존·삭제·대조 |  |  |
| 필수 출처 주장과 해시 |  |  |
| 누락·중복·순서·부분 실패 처리 |  |  |
| source `observed_at` 단조성·시계 책임 |  |  |
| 문서별 source-version 생성·재사용 금지 |  |  |
| delta 파일은 변경 문서만 포함·동일 document ID 중복 금지 |  |  |
| snapshot 누락 문서의 retire/tombstone 이벤트 책임 |  |  |
| retire/tombstone 원 ACL snapshot·legacy ACL 불명 행 처리 |  |  |
| 기존 문서 write ACL tenant/group/clearance와 계약 권한 |  |  |
| ACL 변경의 groups/purposes/민감도 확대·축소 위임과 승인 |  |  |
| managed 빈 groups 거부와 완전 회수 retire/tombstone 책임 |  |  |
| legacy 빈/불명 ACL의 보존 확인·통제 migration |  |  |
| 계약 drift 시 upsert 재등록 / tombstone cleanup / full-binding 변경 구분 |  |  |
| registry 제거 전 retire/tombstone·제거 후 동일 계약 재등록 cleanup |  |  |
| legacy unqualified ID·accepted version history의 통제 migration |  |  |
| 다중 tenant 전 legacy/bootstrap owner·저장 tenant·ID prefix 충돌 재고 |  |  |
| replay 응답 `documents`의 현재 metadata 가시성 투영 |  |  |

현재 제공되는 source snapshot adapter는 승인된 단일 파일의 변경 문서 delta를 정규화하는 경계입니다. 같은 document ID를 한 envelope에 중복할 수 없고, 변경 문서는 과거에 수락하지 않은 새 source version을 사용합니다. managed 문서는 현재 registry의 tenant, source, contract ID/version/hash가 일치할 때만 근거로 사용됩니다. 같은 contract ID·source의 version/hash 변경은 새 source version upsert로 재바인딩할 수 있지만, contract ID가 없는 과거 행이나 다른 계약이 소유한 같은 문서 ID는 일반 upsert로 가져올 수 없습니다. 명시적 관리자 migration 또는 새 문서 ID와 대조 계획을 적습니다. adapter가 delta를 받는다는 사실은 원천 인증, SharePoint·ERP 실시간 증분 수집, 전체 source reconciliation, 누락 문서 자동 삭제 또는 원천 삭제 증명을 뜻하지 않습니다.

신규 managed upsert ID는 DB 조회 전에 `<tenant>.<점 없는 접미부>` 형식으로 검사되며 위반은 존재 여부와 무관하게 422입니다. cross-tenant ID 선점은 막지만 같은 tenant에서는 미사용 ID 생성 성공과 비가시 기존 ID의 404 차이로 사용 여부를 추론할 수 있습니다. ID에 민감한 의미를 넣지 않고 신뢰 가능한 할당자와 계약별 접미부 규칙을 정합니다. 더 강한 격리가 필요하면 tenant별 DB를 검토합니다. 기존 unqualified ID는 자동 rename하지 않으며, cleanup 또는 ID·accepted history의 통제 migration을 선택합니다. 다중 tenant 전에는 legacy·bootstrap owner와 prefix 충돌을 재고 대조합니다. 이 guard가 trusted bootstrap/admin 파일이나 entity/action/object·일반 ontology ID를 자동 검증한다고 기록하지 않습니다.

`knowledge state`의 source head와 문서 메타데이터는 호출자의 등급·그룹·감사 목적과 관리 가능한 현재 계약으로 제한됩니다. retire/tombstone은 직전 ACL snapshot을 유지하고 ACL 불명 legacy 메타데이터는 숨깁니다. 이 응답을 전체 tenant 재고나 삭제 완료 증거로 사용하지 않습니다.

기존 문서 mutation은 저장 ACL의 tenant/group/clearance를 검사하되 문서 purpose는 쓰기 검사에서 생략하고, 계약의 `READ+AUDIT+MANAGE_KNOWLEDGE`는 유지합니다. 기존 upsert는 같은 contract ID/source와 새 source version으로 재바인딩할 수 있습니다. retire/change_acl은 full binding이 필요하고, tombstone만 같은 tenant/source/contract ID의 version/hash drift를 허용해 중간 ACTIVE 재게시 없이 삭제 상태를 현재 binding으로 기록합니다. ACL 불명·권한 밖·타 계약은 모두 404입니다.

저장 ACL을 만족하는 계약 관리자는 계약 범위 안에서 groups, purposes, 민감도를 확대하거나 축소할 수 있습니다. purpose 추가가 이후 본문 열람 범위를 넓힐 수 있으므로 회사 담당자의 위임·승인과 대조 기준을 적습니다. 계약은 문서 보존을 확인해 retire/tombstone한 뒤 registry에서 제거합니다. 이미 제거했다면 같은 tenant/source/contract ID를 승인해 재등록하고 ACL을 확인한 drift tombstone으로 정리합니다. `delete_within_hours`는 실제 원천·백업·provider 삭제 증명이 아닙니다.

managed upsert와 ACL 변경의 새 groups가 비면 422로 배치 전체를 거부합니다. 완전 회수는 빈 그룹 active 문서가 아니라 보존 판단을 거친 retire/tombstone으로 표현합니다. 공통 `Access`·bootstrap의 deny-all 의미는 유지합니다. 기존 DB의 managed 빈 그룹·ACL 불명 행은 숨김+404를 유지하고, 원천 소유자와 실제 회사 보존 의무를 확인한 통제된 migration에서만 정리합니다.

신규 성공과 멱등 replay의 응답 `documents`는 현재 메타데이터 가시성으로 비거나 줄 수 있으며, 이 투영은 DB에 저장하는 canonical receipt/audit를 수정하지 않습니다. 검토 기록에는 저장 증거와 호출자별 응답 투영을 구분합니다.

## 4. gold에서 승격까지

| 단계 | 필요한 증거 | 진입 조건 | 중단 / 복구 조건 | 승인자 |
|---|---|---|---|---|
| Gold set | 정상·예외·거부·권한·삭제 사례, 기대 근거와 판정 | 현업이 사례와 정답 근거 확인 | 라벨 불일치·대표성 부족 |  |
| Dry run | 실제 쓰기 없는 결과·근거·지연·비용 | 계약과 데이터 품질 확인 | 권한·근거·스키마 실패 |  |
| Shadow | 현행 처리와 병렬 비교, 사용자 영향 없음 | dry run 기준 충족 | 안전 veto·회귀·운영 부하 |  |
| Staged promotion | 제한 사용자·업무·데이터, 관측·중단 스위치 | 현업·보안·운영 승인 | 품질·권한·삭제·비용 기준 이탈 |  |
| Rollback | 이전 팩·모델·도구·데이터 head | 복구 시험 완료 | 대조 실패 시 수동 복구 |  |

## 5. 평가와 비용

- retrieval recall / 근거 정확성 / 유보 정확성:
- 위험한 허용 / 불필요한 거부:
- ACL·테넌트·삭제·stale evidence 실패율:
- 지연 / 처리량 / 가용성:
- 모델·인프라 비용:
- 현업 검수·재작업·교육·운영 비용:
- 업무 결과 지표와 기준선:

## 6. 변경 결정

- 선택한 대안과 선택하지 않은 대안:
- 변경할 계약·팩·모델·도구 버전:
- 미구현 항목:
- 후속 현장 검증:
- 결정: 보류 / 실험 / shadow / 단계 승격 / 반려
- 승인자 / 일시:
