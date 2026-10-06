# 업그레이드와 업종 강화 가이드

업그레이드는 공통 코어, 업종팩, 회사 보안 프로필, 증거팩을 따로 버전 관리한 뒤 한 릴리즈 기록에서 결합합니다. 업종 지식이 깊어져도 회사별 데이터 반출·보존·권한 정책은 자동으로 따라오지 않으며, 합성 평가가 현장 승격을 허가하지도 않습니다.

회사 프로필의 `REPORTED`는 제출자 자기신고이고 원천 진위·현장 통제 작동을 검증한 상태가 아닙니다. region/model/tool 정책 근거가 `UNKNOWN`이면 업그레이드 파일럿 검토도 `blocked`입니다.

## 1. 변경 대상을 먼저 나눈다

| 변경층 | 바꾸는 것 | 반드시 다시 확인할 것 |
|---|---|---|
| 공통 코어 | 계약, 인증, 저장소, 검색, 승인·실행, 감사 | API 호환성, schema migration, 회귀, 보안 veto |
| 업종팩 | 용어, 객체·관계, 문서, 규칙, 평가 사례 | 출처, 현업 승인, ACL, 위험한 오답, 지역·시점 적용범위 |
| 회사 보안 프로필 | 배치·등급·리전·모델·도구·보존·그룹 | 회사 정책 근거, 승인자, 위탁·국외전송, 회수 절차 |
| 증거팩 | gold set, fixture digest, 평가·검토·배포 기록 | 독립성, 데이터 출처, 재현성, 현장 검토자 |

한 층의 검증 결과를 다른 층의 승인으로 바꾸지 않습니다. 예를 들어 FHIR R5를 참조한 의료 업종팩이 있어도 특정 병원의 개인정보 처리, 의료기기 여부, 국외전송, 모델 사용 승인은 별도입니다.

## 2. 한 업종을 강화하는 표준 순서

다음 순서는 금융, 의료, 제조, 유통 중 어느 업종에도 같습니다. [업종 확장 검토서](../templates/industry-expansion-review.md)에 각 결정을 남깁니다.

1. **용어·관계·규칙과 출처를 묶는다.** 용어의 정의, 관계 방향, 규칙의 관할·효력일·예외를 표준·법령·회사 규정의 정확한 위치와 연결합니다.
2. **현업 승인을 받는다.** 업무 소유자가 정의와 예외를 승인하고, 보안·개인정보·준법 담당자가 자료 사용과 실행 범위를 승인합니다. 미확인 항목은 `unknown`으로 남깁니다.
3. **source contract를 고정한다.** 원천 ID/URI, 소유자, object scope, tenant, ACL, 민감도 범위, hash/provenance, 갱신·삭제·정합성 정책을 `DataContract`로 등록합니다.
4. **gold set을 만든다.** 정상·모름·상충·만료·삭제·권한 경계·위험한 오답 사례에 정답 문서 ID와 판정 이유를 붙입니다. 개발용과 최종 평가용을 분리합니다.
5. **dry run을 수행한다.** 복사된 비운영 데이터에서 수집, 계약 거부, CAS, 검색, 승인, rollback을 검증합니다. 외부 원천과 업무 시스템을 변경하지 않습니다.
6. **shadow 운영을 한다.** 실제 담당자의 판단과 병행해 결과를 비교하되 시스템 기록을 쓰지 않습니다. 오류 유형, 유보, 검토 시간, 재작업을 수집합니다.
7. **staged promotion을 한다.** 사용자군·자료 등급·작업 allowlist·기간을 좁혀 단계별로 열고 매 단계 release evaluation과 현업 승인을 새로 기록합니다.
8. **rollback을 실행 가능하게 유지한다.** 복귀할 모델·팩·도구·계약 버전, 데이터 호환성, 미완료 작업, 책임자와 중단 기준을 배포 전에 시험합니다.

### 예: 제조 정비 업종 강화

- 용어: 설비, 부품, 작업지시, 고장모드, 위험에너지 격리를 출처와 함께 정의합니다.
- 관계: 설비→부품→정비절차→작업지시를 만들되, 설비 계층·유효일·사업장 경계를 기록합니다.
- 규칙: 정비 주기와 안전 interlock은 모델 프롬프트가 아니라 승인된 결정적 규칙/도구로 구현합니다.
- source contract: OPC UA나 CMMS를 읽는 별도 커넥터의 정규화 결과에 적용합니다. 이 스타터의 snapshot adapter 자체가 OPC UA/CMMS 인증 연결은 아닙니다.
- gold set: 만료된 절차, 다른 사업장 문서, 권한 없는 작업자, 삭제된 안전문서, 단위 불일치, 센서 결측을 포함합니다.
- 승격: 읽기 전용 shadow에서 시작하고, 외부 쓰기는 샌드박스의 한 가지 가역 작업으로 제한합니다.

금융은 FIBO, 의료는 FHIR R5, 제조는 OPC UA, 유통 추적은 GS1 EPCIS를 출발점으로 검토할 수 있습니다. 이 표준을 채택했다는 사실만으로 현장 의미·규제·품질이 충족되지는 않습니다. 적용 상태와 경계는 [자료 카탈로그](SOURCE_CATALOG.md)에 구분했습니다.

## 3. 팩 변경 규칙

팩의 객체·관계·문서·규칙·ACL·출처가 바뀌면 버전을 올리고 canonical hash를 기록합니다. ID를 재사용해 의미를 바꾸지 않습니다. pack hash가 다른 파일로 기존 DB를 조용히 덮어쓰는 경로는 제공하지 않습니다.

지식 문서는 팩을 다시 빌드하지 않고 SQLite 계약 경로로 갱신할 수 있습니다. 두 변경을 구분합니다.

- bootstrap 팩 변경: 의미 구조와 초기 문서의 배포 변경. pack 버전/hash와 DB 호환성을 검토합니다.
- 운영 지식 변경: 등록된 데이터 계약 ID/version/hash binding, tenant/source revision CAS, 분리된 apply/import request-key namespace, 수락된 source-version history와 영수증으로 추적합니다. import는 변경 문서만 담는 delta이며 누락을 삭제로 해석하지 않습니다.

운영 지식 upsert로 객체 타입·관계 스키마를 임의 변경할 수 없습니다. 스키마 변경은 팩 업그레이드와 명시적인 migration 설계가 필요합니다.

같은 문서 ID를 다른 tenant, source 또는 contract ID의 upsert로 덮을 수 없습니다. 기존 upsert는 저장 ACL의 tenant/group/clearance를 만족하고 같은 contract ID·source에 새 source version을 제출할 때 현재 contract version/hash로 다시 묶을 수 있습니다. retire와 ACL 변경은 저장 version/hash도 현재 요청 계약과 일치해야 합니다. tombstone만은 같은 tenant/source/contract ID와 저장 ACL 권한을 만족하면 version/hash drift를 허용하고 현재 binding으로 기록합니다. 계약 v1→v2 전환 뒤 삭제할 문서를 중간 ACTIVE upsert로 재게시할 필요가 없도록 한 cleanup 예외입니다. 계약 hash는 집합형 `required_provenance`를 정렬한 canonical 직렬화에 기반하므로, 실제 계약 의미가 같은지와 hash가 같은지를 함께 검토합니다.

신규 managed upsert ID는 `<tenant>.<점 없는 접미부>`여야 하며 DB 조회 전에 검사합니다. 다른 tenant prefix, 빈 접미부, 접미부 안의 점은 존재 여부와 관계없이 422입니다. 이 규칙이 cross-tenant ID 선점은 막지만 같은 tenant 안의 ID 사용 여부 추론까지 없애지는 않습니다. ID를 비민감 난수나 내부 키로 만들고 신뢰 가능한 할당자와 계약별 접미부 규칙을 둡니다. 규제가 더 강하면 tenant별 DB를 고려합니다.

계약의 `READ+AUDIT+MANAGE_KNOWLEDGE` 권한과 기존 문서의 저장 ACL은 서로 다른 검사입니다. 기존 문서의 쓰기 ACL은 tenant, group, clearance를 검사하고 문서 purpose는 생략합니다. ACL snapshot이 없거나 권한 밖이면 다른 계약 문서와 마찬가지로 404입니다. 새 문서 생성은 candidate access가 계약을 만족하는지 검사합니다.

ACL 변경자는 계약 범위 안에서 groups, purposes, 민감도를 확대하거나 축소할 수 있습니다. purpose 추가는 이후 본문 열람자를 늘릴 수 있으므로 단순 메타데이터 편집 권한으로 취급하지 않고 회사 담당자의 명시적 위임·승인과 변경 대조를 둡니다.

managed upsert와 ACL 변경의 새 `access.groups`는 비어 있을 수 없습니다. 빈 그룹은 422로 전체 트랜잭션을 거부하며 revision, audit, accepted-version history를 남기지 않습니다. 모든 그룹의 접근을 회수할 때는 빈 그룹 active 문서를 만들지 않고 보존 의무에 맞는 retire/tombstone을 선택합니다. 공통 `Access`와 bootstrap의 빈 그룹 deny-all 의미는 변경하지 않습니다.

## 4. v0.1에서 v0.2로

v0.2의 현재 SQLite knowledge schema version은 4입니다. v1 DB를 처음 열 때 knowledge 테이블과 상태 head를 만들고 bootstrap 문서를 seed합니다. 기존 `pack_hash`, entity, proposal, receipt, audit 행은 보존 대상입니다. schema 4의 `access_json`은 상태 응답에서 공개하는 새 필드가 아니라 retire/tombstone 뒤에도 원래 ACL로 메타데이터 노출을 제한하는 내부 snapshot입니다.

안전한 전환 순서:

1. v0.1 프로세스를 멈추고 원본 DB, 팩, 신원 파일의 일관된 백업과 hash를 기록합니다.
2. 운영 원본이 아닌 복구 가능한 복사본에서 v0.2를 시작합니다.
3. 기존 pack hash, 객체 상태, 미완료 제안, 감사 chain을 확인합니다.
4. `knowledge state`에서 호출자 ACL로 보이는 bootstrap 문서와 revision 0 상태를 확인합니다. `sources`와 `documents`는 등급·그룹·관리 가능한 현재 계약으로 제한된 투영이며 tenant 전체 재고가 아닙니다.
5. 등록할 데이터 계약과 `manage_knowledge` 주체를 최소 범위로 검토합니다.
6. 합성 지식 변경으로 CAS, apply/import namespace, source-version 재사용 차단, snapshot watermark, 저장 ACL write guard, replay 응답의 현재 가시성 투영, 재시작 후 상태를 검증합니다.
7. managed 문서가 현재 registry의 tenant, contract ID/version/hash와 source에 정확히 묶였는지 확인합니다. binding이 달라지면 current pack에서 제외되어야 합니다. 같은 tenant/source/contract ID의 drift 문서는 retire·ACL 변경이 거부되고 tombstone cleanup만 현재 binding으로 완료되는지 확인합니다.
8. v0.2 독립 감사와 회사 현장 승인 후 제한 배포합니다.

v0.1의 미완료 proposal은 proposer/approver actor kind·person binding이 없을 수 있습니다. 이런 제안은 필드를 추정해 채우지 않고 새 제안 또는 새 승인을 받습니다. 이미 실행되거나 rollback된 terminal 제안의 멱등 execute replay와 rollback 호환 경로는 유지되지만 현재 호출 주체의 credential·권한 검사는 계속 적용됩니다.

schema 2 개발 DB를 열면 먼저 contract binding 컬럼, source watermark, accepted source-version history를 추가하고 기존 batch를 `apply` namespace로 옮깁니다. 현재 행과 기존 receipt로 source-version history를 재구성합니다. 과거 `observed_at`은 저장되지 않았으므로 마지막 knowledge batch 감사 시각을 source별 보수적 watermark 상한으로 쓰고, 감사 매핑이 없는 managed source는 migration 시각을 씁니다. 후속 `observed_at`은 이 상한보다 엄격히 커야 합니다. 이 상한은 rollback 방지를 위한 경계이며 원천 진위나 실제 수집 시각 인증이 아닙니다.

schema 2·3에서 schema 4로 갈 때는 본문이 남아 있고 그 안의 access hash가 저장 `access_sha256`과 맞는 행만 `access_json`을 backfill합니다. 본문이 이미 제거된 legacy tombstone처럼 ACL을 복원할 수 없는 메타데이터는 허용으로 추정하지 않고 `knowledge state`에서 숨깁니다. 자동 backfill이 못한 행을 수동으로 채우기 전에 원본·감사 기록·권한 소유자의 승인을 대조하고, 복구 가능한 DB 복사본에서 가시성 결과를 시험합니다.

ACL snapshot을 복원할 수 없는 legacy 행은 mutation에서도 fail-closed 404입니다. tombstone의 version/hash drift 예외가 이 경계를 우회하지 않습니다. 복구가 필요하면 운영 DB를 임의 편집하지 말고 승인된 관리자 migration을 별도로 설계합니다.

이미 managed ACL groups가 빈 개발 DB 행도 같은 404·숨김 경계를 적용합니다. 자동으로 운영 그룹을 넣거나 삭제 상태로 바꾸지 않습니다. 데이터 소유자와 실제 회사의 보존·법적 보존·원천 삭제 상태를 확인한 뒤 통제된 migration에서만 정리합니다.

새 namespace에 맞지 않는 기존 unqualified managed ID는 자동 rename하지 않습니다. upsert는 422이고, 현재 binding과 저장 ACL을 만족하는 retire/tombstone cleanup은 유지됩니다. 계속 사용할 문서를 새 ID로 옮길 때는 accepted source-version history도 함께 이동해야 하므로 DB 백업, 소유자 승인, 충돌 검사, 감사 대조와 rollback을 갖춘 별도 migration으로 처리합니다. bootstrap·읽기 ID와 v0.1 역사 파일은 바꾸지 않습니다. 다중 tenant 전환 전에는 legacy·bootstrap 문서의 실제 owner, 저장 tenant와 ID prefix를 재고 대조해 다른 tenant namespace처럼 보이는 기존 ID를 정리합니다. 신규 managed upsert guard는 trusted bootstrap/admin 파일이나 entity/action/object·일반 ontology ID의 migration을 수행하지 않습니다.

기존 managed 행의 contract binding은 추정하지 않습니다. binding이 없는 행은 current pack에서 숨기며, `contract_id`가 null인 같은 문서 ID를 일반 upsert로 재등록할 수도 없습니다. 운영자는 관리자 migration 또는 새 문서 ID와 승인된 대조 절차 중 하나를 설계해야 합니다. 같은 contract ID와 source로 이미 바인딩된 문서는 새 계약 version/hash와 새 source version을 검증한 upsert로 재바인딩할 수 있습니다.

계약 제거 순서는 문서 정리 뒤 registry 제거입니다. 먼저 실제 보존을 확인하고 retire/tombstone한 뒤 계약을 제거합니다. 계약이 이미 빠졌다면 같은 tenant/source/contract ID를 승인된 설정으로 재등록하고 ACL을 확인한 drift tombstone으로 정리할 수 있습니다. `delete_within_hours`는 선언값이므로 원천, 파생물, WAL, 백업과 provider의 실제 삭제는 별도 실행·증거가 필요합니다.

knowledge schema 값이 없거나 2·3인 경우 외의 알 수 없는 값이면 런타임은 `knowledge_schema_migration_required`로 닫혀야 합니다. DB의 `meta`나 knowledge 테이블을 손으로 바꾸지 않습니다. 마이그레이션이 실패하면 프로세스를 중지하고 일관된 원본 백업을 복원해 원인을 조사합니다. v0.2에서 v0.1 바이너리로 단순 롤백할 때 새 테이블이 무시된다는 이유만으로 데이터 호환성을 가정하지 말고, 배포 전에 복구 시험으로 확인합니다.

## 5. 모델·온톨로지·도구 릴리즈

릴리즈 ID 하나에 다음 manifest를 고정합니다. 런타임의 `EvaluationTarget`은 pack, data contract, model, prompt, policy, case set, rubric, code의 version과 SHA-256을 canonical manifest hash로 묶습니다.

| 대상 | 고정할 식별자 | 평가 항목 |
|---|---|---|
| 모델 | provider, endpoint class, deployment/model ID, 설정 hash | 품질, 불필요 거부, 지연, 비용, 인용, 안전 |
| 온톨로지 | pack ID/version/hash, 업종 출처 버전 | 관계·ACL·검색·규칙 회귀, 현업 gold |
| 도구 | action type, handler version/hash, allowlist, 한도 | 권한, dry-run, 멱등성, 부분 실패, rollback |
| 데이터 계약 | registry hash, contract ID/version, source ID | provenance, ACL, retention, deletion/reconciliation |
| 회사 프로필 | profile version/hash, 승인 기록 | 배치·등급·리전·전송·모델·도구 정책 |

회사 프로필과 도구 운영 기록은 릴리즈 검토에 계속 필요합니다. 현재 `EvaluationTarget`에는 별도 `company_profile`·`tool` 필드가 없으므로, 어떤 승인된 policy/code artifact가 이를 대표하는지 릴리즈 규칙에 명시하고 같은 자산을 여러 필드에 임의 중복시키지 않습니다.

`POST /v1/release/evaluate`는 baseline/candidate의 입력 측정값을 기준과 대조합니다. 다음 조건을 별도로 봅니다.

- 안전 실패, 권한 위반, 삭제 누락은 즉시 veto.
- 품질 최저선과 회귀 폭은 별도.
- 불필요 거부의 절대 비율과 회귀 폭은 별도.
- 평균 지연·비용의 절대 한도와 회귀 폭은 별도.
- target manifest가 없거나 evidence·case가 같은 manifest hash를 참조하지 않으면 점수와 무관하게 `blocked`.
- 실제 `ReleaseCriteria` canonical SHA가 manifest의 rubric SHA와 다르거나, 정렬된 case ID·domain·fixture digest 집합 SHA가 case-set SHA와 다르면 `blocked`.
- 중복 case ID는 평가 전에 계약 오류로 거부.
- 합성 평가면 `synthetic_evaluation_only`이며 현업 검토 자격 없음.
- 실자료라도 named field reviewer가 없으면 `field_review_required`.

평균 품질·불필요 거부율·지연·비용은 반올림 전 case 원값의 산술평균으로 threshold와 baseline 회귀를 판정합니다. 보고서 표시를 네 자리 등으로 반올림해 경계 통과 여부를 다시 계산하지 않습니다.

`eligible_for_field_review`는 출시 허가가 아닙니다. canonical manifest와 rubric/case-set 결합은 선언된 대상·기준·case 식별의 일관성만 확인합니다. 이 API는 fixture 내용, 측정 수행, 제출된 evidence digest의 원천을 검증하지 않으며, 회사의 change management나 실제 live observation을 수행하지 않습니다.

업그레이드 전후 감사 확인에서 tenant별 audit chain과 지식 상태를 별도로 봅니다. audit chain은 audit event 연쇄만 검증하며 문서 row 전체 JSON, state head 또는 DB 파일 전체의 무결성 증명이 아닙니다. 팩·신원·provider·계약 파일과 SQLite 파일은 운영자 ACL·배포 승인·호스트 무결성 경계 안에서 관리하고, 외부 registry 파일 교체와 SQLite commit이 하나의 원자적 변경이라고 가정하지 않습니다.

schema 4 read path는 문서 JSON 파싱과 문서 ID·source version·access tenant·본문 SHA·ACL snapshot SHA의 row 메타데이터 일치를 확인합니다. 남은 `document.access`와 snapshot이 다른 경우도 `knowledge_integrity_failure`로 닫히는지 복사본에서 점검하되, title·object scope·`valid_until`·source URI·전체 canonical JSON·state head까지 보호된다고 확대하지 않습니다. apply/import 중에는 트랜잭션 진입 직후 live registry의 계약 ID/version/canonical SHA와 현재 권한도 다시 확인합니다. 이는 외부 registry 파일과 DB commit의 완전한 원자성을 만들지 않습니다.

## 6. 구현된 항목과 후속 현장 검증

| 항목 | v0.2 구현 | 후속으로 필요한 것 |
|---|---|---|
| 도입 진단 | CompanyProfile+BusinessIntake 결정적 판정, unknown 보류, 명시 거절/정책 충돌 차단 | 정책 문서 진위, 승인자 신원, 네트워크·업무 현장 확인 |
| 데이터 계약 | 서버 등록 registry, 문서 계약 검증, source/tenant 범위 | 원천 시스템 인증, 실제 커넥터, lineage backend |
| 인증 | 명시적 `opaque_only`/`jwt_only`/`both`, pinned public JWKS RS256 access-token 검증, ActorKind/person mapping | 기업 로그인/PKCE/세션/refresh/introspection·중앙 키·디렉터리 사람 매핑 운영 |
| 지식 변경 | schema 4 계약 binding·ACL snapshot, 기존 문서 tenant/group/clearance write guard, tombstone drift cleanup, 신규·replay 영수증 문서의 현재 가시성 투영, tx 진입 후 live 계약 재대조, SQLite 변경·CAS·멱등 namespace·history·watermark | registry 파일+DB의 완전 원자성, row/state head 전체 무결성, 영수증 응답 전체 byte 동일성, 대용량 DB, 물리 삭제·백업 삭제 증명 |
| 검색·실행 | 현재 문서 source/version/hash/ACL/lifecycle/contract binding 재검증, 독립 human 승인 | 벡터·embedding 삭제 전파, 외부 시스템 실제 실행 connector |
| 모델 경계 | `RESTRICTED` 기본 하한, 호출 전·후 exact credential+검색 근거 재검사 | provider 보관 삭제, 실제 부하·장애·비용 검증 |
| snapshot adapter | 변경 문서만 든 단일 delta 파일을 계약 batch로 변환, 중복 문서 ID 거부, 시각 단조성과 source-version 재사용 차단 | 전체 source reconciliation, OCR, 악성 파일 검사, 누락 자동 삭제, SharePoint/ERP/FHIR/OPC UA 원천 연동 |
| 릴리즈 평가 | 여덟 대상 manifest, criteria/rubric·case-set digest 일치, 중복 ID 거부, raw 평균 threshold, 안전 veto, 합성 승격 금지 | fixture 내용·측정 provenance, 독립 현업 평가, 증거 origin 검증, 실제 출시 승인 |

개인정보·의료·금융 데이터라는 이유만으로 무조건 on-prem을 요구하지 않습니다. 법적 근거, 회사 정책, 데이터 등급, 위탁·국외전송, 리전, 모델 학습·보관, 키 관리, 통신 경로를 평가해 offline/private/gateway/hybrid를 결정합니다.

## 7. 비용과 효과

모델 호출료나 GPU 비용만 비교하지 않습니다. 데이터 정리, 계약·ACL 설계, OCR/embedding 재생성, gold 작성, 현업 검수, 보안 검토, 재작업, 운영, 관측, 장애 복구와 삭제 증명 비용을 포함합니다.

사례 연구의 시간 절감이나 기업이 발표한 KPI는 그 기업의 조건과 측정입니다. 우리 파일럿의 비용 절감으로 전이하지 않습니다. 그림자 운영의 기준선과 제한 도입을 같은 모집단·기간·업무 정의로 비교하고, 시간 절감이 실제 인력·처리량·품질·위험 비용 변화로 이어졌는지 별도로 확인합니다.

## 8. 평가와 감사 경계

`docs/evidence/v0.1.0/`의 기존 Opus·Codex 감사는 v0.1 범위의 역사적 증거입니다. v0.2 코드와 문서에 대한 감사 결과는 별도 evidence digest와 변경 파일 목록으로 기록해야 합니다. 이전 감사 판정, 구현자의 자체 테스트, 합성 release evaluation 중 어느 것도 v0.2 현장 출시 검증을 뜻하지 않습니다.

## 9. LLM Wiki 강화

v0.3은 reviewed Wiki를 원문 RAG와 온톨로지 사이의 지속 지식 계층으로 제공합니다. [Wiki 가이드](LLM_WIKI_GUIDE.md)의 모듈 지도·세 가지 수정 실습·회사 gold set과 [실행 가이드](V03_GUIDE.md)를 함께 사용합니다. L0는 출처·권한·용어, L1은 절차·예외의 독립 검토 게시, L2는 RAG-only/hybrid 비교, L3는 source watcher·검토 대기열·의미 충돌·삭제 증명, L4는 현업 기준을 통과한 좁은 action 연결입니다.

분야 강화는 지식을 늘리는 것과 사용 권한을 늘리는 것을 구분합니다. 규정·용어·예외를 새 raw version과 함께 검토하고 Wiki CAS revision을 올립니다. gold set에는 오래된 규정·상충한 문서·목적 변경·원천 삭제·멀티-role AND·object/hops 범위·reviewer 권한 회수 사례를 넣습니다. 합성 데모는 기능 회귀 증거이고 회사의 품질 개선이나 ROI를 입증하지 않습니다.

v0.3 Wiki는 source watcher나 자동 재compile queue를 포함하지 않습니다. 새 source, ACL·계약·role 변경과 floor 상향은 운영 사건으로 접수하고, 영향 page를 찾아 current raw 적격성과 모든 source/scope-object 접근을 다시 확인한 뒤 새 request key로 compile·독립 검토합니다. `evidence_roles`를 `raw_source`에서 `derived_output`으로 바꾸면 다음 `current_pack`에서 문서가 제외되고 그 원천에 의존한 page도 live read에서 숨겨집니다. role 변경만으로 안전한 대체 page가 생기지는 않습니다.

## 10. v0.3에서 v0.2로 되돌리기

v0.3 registry의 `evidence_roles`는 v0.2 계약의 `extra="forbid"`에 걸려 시작 자체가 실패할 수 있습니다. 이를 피하려고 필드만 삭제하면 v0.3에서 격리한 `derived_output` 문서와 marker 기반 문서가 v0.2 current pack의 raw 근거로 다시 들어갈 수 있습니다. 역할 삭제는 호환 변환이 아니라 권한·근거 경계의 약화입니다.

안전한 rollback은 다음 두 방식 중 하나로 수행합니다.

1. v0.2 배포 직전에 고정한 원천 snapshot, v0.2 registry, identity/provider 설정과 v0.2 DB를 한 묶음으로 복원합니다. 해당 snapshot 이후의 지식 변경과 Wiki 생성물은 별도 보존·대조합니다.
2. v0.3 DB를 그대로 열거나 registry를 손으로 줄이지 않고 새 v0.2 DB를 분리 생성합니다. 승인한 raw 원천만 v0.2 계약으로 재수집하고 derived export·Wiki table·v0.3 역할 metadata를 가져오지 않습니다.

두 방식 모두 복사본에서 v0.2 runtime 기동, raw current pack 목록, 검색·action evidence, 계약 hash, ACL·삭제 상태와 audit chain을 검사합니다. v0.3에서 page나 export에 사용된 원천이 v0.2에서 의도치 않게 다시 검색되지 않는지 adversarial case를 포함합니다. rollback 성공은 v0.3 Wiki history를 v0.2가 이해하거나 논리 scrub·provider 삭제를 완료했다는 뜻이 아닙니다.
