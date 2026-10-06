# v0.2 안내서

v0.2는 v0.1의 읽기·검색·승인 실행 코어에 **결정적 도입 진단, 서버 등록 데이터 계약, 선택적 RS256 액세스 토큰 검증, SQLite 운영 지식 생명주기, 안전 veto가 있는 릴리즈 평가**를 추가합니다. 이 기능들은 현장 검토에 필요한 경계를 드러내며, SSO 전체·원천 커넥터·물리 삭제·출시 승인을 자동화하지 않습니다.

## 어디서 시작할까

| 목적 | 문서 |
|---|---|
| 무엇을 어떤 조건에서 도입할지 | [도입 가이드](ADOPTION.md) |
| 실제 요청·저장·검색·승인 흐름 | [아키텍처](ARCHITECTURE.md) |
| 인증·반출·삭제·위협 경계 | [보안 모델](SECURITY_MODEL.md) |
| 서버 기동·명령·장애·백업 | [운영 가이드](OPERATIONS.md) |
| 한 업종 강화·v0.1 전환·릴리즈 | [업그레이드 가이드](UPGRADE_GUIDE.md) |
| 코드와 합성 입력으로 학습 | [학습 가이드](LEARNING_GUIDE.md) |
| 공식 표준·제품·사례·연구의 적용 경계 | [자료 카탈로그](SOURCE_CATALOG.md) |

검토 서식:

- [위험·데이터 검토서](../templates/risk-data-review.md)
- [모델 계약·릴리즈 검토서](../templates/model-contract-review.md)
- [업종 확장 검토서](../templates/industry-expansion-review.md)

## 구현 범위

### 도입 진단

`POST /v1/onboard`와 `ax onboard evaluate`는 `CompanyProfile`과 `BusinessIntake`를 결합합니다. 안전한 경로를 정하는 핵심 unknown은 `blocked`, 그 밖의 추가 검토 항목은 `on_hold`로 두고 누락 질문과 다음 단계를 반환합니다. 특히 region/model/tool 정책 근거가 `UNKNOWN`이면 각각 `region_policy_evidence_unknown`, `model_policy_evidence_unknown`, `tool_policy_evidence_unknown`으로 `blocked`입니다. `REPORTED`는 제출된 자기신고 상태이며 원천 진위, 현장 통제 작동 또는 보안 인증을 증명하지 않습니다. 명시 거절과 정책 충돌도 `blocked`입니다. 어느 결과도 실행 권한이나 출시 자격을 주지 않으며, 판정은 `assurance=self_reported_readiness`, `live_validated=false`, `security_certified=false` 경계를 유지합니다.

### 데이터 계약과 지식

`DataContractRegistry`는 서버가 시작할 때 등록합니다. 변경 요청은 contract ID만 참조하며, 호출자가 정책을 바꿔 보내지 못합니다. schema 4는 managed 문서에 contract ID/version/hash와 응답에 노출하지 않는 내부 ACL snapshot을 저장합니다. 현재 registry의 tenant·source·계약 binding이 모두 같은 문서만 current pack에 포함하고, 계약 drift나 미바인딩 문서는 fail-closed로 숨깁니다. apply/import는 SQLite 트랜잭션 진입 직후 exact credential과 live 계약의 ID/version/canonical SHA·현재 권한을 다시 확인합니다. 외부 registry 파일 교체와 DB commit은 하나의 원자적 변경이 아닙니다. `POST /v1/knowledge/apply`는 upsert/retire/tombstone/ACL 변경을 tenant/source revision CAS와 `apply` request-key namespace 아래 한 트랜잭션으로 처리합니다.

기존 문서 mutation은 계약 권한 외에도 저장 ACL snapshot의 tenant/group/clearance를 검사합니다. 문서 purpose는 이 쓰기 검사에서 생략하지만 계약의 `READ+AUDIT+MANAGE_KNOWLEDGE`는 유지하며, ACL 불명·권한 밖·타 계약 문서는 404입니다. 같은 contract ID/source의 기존 upsert는 새 source version으로 현재 version/hash에 재바인딩할 수 있습니다. retire와 ACL 변경은 full binding이 필요하고, tombstone만 같은 tenant/source/contract ID에서 version/hash drift를 허용해 현재 binding으로 삭제 상태를 기록합니다. 새 문서 ID는 candidate access를 계약과 대조합니다.

신규 managed upsert ID는 `<tenant>.<점 없는 접미부>`여야 하며 전역 ID 조회 전에 검사합니다. 위반은 존재 여부와 무관하게 422이므로 다른 tenant의 ID 탐색·선점을 막습니다. 같은 tenant 안에서는 생성 성공과 비가시 기존 ID의 404가 달라 ID 사용 여부를 추론할 수 있으므로 ID에 민감한 의미를 넣지 않고 신뢰 가능한 할당자와 계약별 접미부 규칙을 둡니다. 더 강한 격리가 필요하면 tenant별 DB를 사용합니다. 기존 unqualified managed ID는 자동 rename하지 않으며 upsert는 422입니다. 현재 binding·저장 ACL을 만족하는 retire/tombstone 정리나 승인된 ID/history migration을 사용합니다. 다중 tenant 전에는 legacy·bootstrap 문서의 실제 owner, 저장 tenant와 prefix를 재고 대조해 다른 tenant namespace처럼 보이는 ID를 해소합니다. 이 guard는 trusted bootstrap/admin 파일을 검증·재작성하거나 entity/action/object·일반 ontology ID 전체에 적용되지 않습니다.

managed upsert와 ACL 변경의 새 `access.groups`가 비면 `data_contract_violation` 422로 전체 트랜잭션을 거부합니다. 비어 있지 않은 다른 그룹 self-revoke는 허용합니다. 모든 그룹의 접근을 회수할 때는 빈 그룹 active 문서를 만들지 않고 보존 판단에 맞는 retire/tombstone을 사용합니다. 공통 `Access`·bootstrap의 deny-all 용도는 바꾸지 않으며, legacy managed 빈 그룹·ACL 불명 행은 숨김+404로 두고 실제 회사 보존 결정을 확인한 통제된 migration으로 정리합니다.

`POST /v1/knowledge/import`는 단일 파일에 정규화한 **변경 문서 delta**를 별도 `import` namespace의 upsert로 바꿉니다. 같은 document ID가 한 요청에 중복되면 계약 단계에서 거부하고, 전체 envelope hash, source별 `observed_at` 엄격 증가와 문서별 수락 source-version history를 검사합니다. 변경 문서는 과거에 수락하지 않은 새 source version을 사용합니다. 신규 성공과 동일한 수락 envelope replay의 응답 `documents`는 현재 저장 record의 exact binding과 actor의 문서 ACL `READ/AUDIT` 가시성으로 필터됩니다. 이 투영은 DB에 저장한 canonical receipt/audit와 상위 tenant/contract/request/payload/revision 필드를 수정하지 않지만, 권한 변경 뒤 응답 배열은 비거나 줄 수 있습니다. delta에서 빠진 문서를 자동 삭제하지 않으므로 삭제·정정은 명시적 apply 변경으로 보냅니다. 실제 SharePoint, ERP, FHIR, OPC UA 로그인·수집·원천 인증은 제공하지 않습니다. tombstone은 document JSON의 본문·title·source URI를 제거하고 source version/history·원 ACL snapshot을 남기는 논리 삭제이며 WAL·백업·모델 제공자의 물리 삭제 증명이 아닙니다.

`GET /v1/knowledge/state`의 tenant revision/state hash는 CAS용 tenant aggregate입니다. 반면 `sources`는 호출자가 `READ+AUDIT+MANAGE_KNOWLEDGE`와 계약 ACL을 만족하는 현재 계약의 source로 제한되고, `documents`는 현재 binding·실제 문서 ACL·관리 가능한 계약을 모두 만족해야 보입니다. 하나의 source를 여러 계약이 공유하면 보이는 source head도 그 source의 aggregate CAS 상태입니다. bootstrap 문서는 자체 ACL을 적용합니다. retire/tombstone은 직전 ACL snapshot을 유지하고, ACL을 복원할 수 없는 legacy 메타데이터는 숨깁니다. 따라서 이 응답은 전체 tenant 재고가 아닙니다.

state의 문서 가시성은 `AUDIT` purpose까지 확인하지만 기존 문서 쓰기 ACL은 문서 purpose를 생략합니다. 따라서 state에 보이지 않는다는 사실만으로 mutation 결과를 예측하지 말고 저장 ACL tenant/group/clearance와 현재 계약 권한을 함께 봅니다.

`change_acl` 권한은 계약 범위에서 groups, purposes, 민감도를 넓히거나 줄일 수 있고 purpose 추가로 본문 열람 범위를 바꿀 수 있습니다. 회사 담당자의 위임·승인·대조가 필요합니다. 계약은 문서 정리 뒤 registry에서 제거합니다. 이미 제거했다면 같은 tenant/source/contract ID를 통제해 재등록한 뒤 ACL을 확인하고 drift tombstone으로 정리합니다. `delete_within_hours`는 실제 원천·백업·provider 삭제 실행이나 증명이 아닙니다.

### 인증

`IdentityRegistry.authentication_mode`는 기본 `opaque_only`이며, JWT만 쓰는 `jwt_only`나 둘을 함께 쓰는 `both`를 명시적으로 선택할 수 있습니다. pinned public JWKS가 설정된 JWT 경로는 RS256 access token의 `iss/aud/sub/client_id/exp/iat/nbf`, `kid`, access-token `typ`을 확인한 뒤 서버에 등록한 human 또는 service Principal에 매핑합니다. 브라우저 로그인, Authorization Code/PKCE, 세션, refresh token, discovery/introspection은 범위 밖입니다.

### 현재 근거와 모델 반출

검색은 SQLite의 active 문서와 bootstrap pack을 현재 시점에 합성합니다. approve/execute는 근거의 source version, content hash, ACL hash, lifecycle, 현재 contract binding을 다시 확인합니다. 승인자는 human이어야 하며 다른 subject라도 같은 `person_id`면 자기 승인으로 차단합니다. 제안·승인 당시 actor kind/person binding도 고정해 같은 subject의 사람 재할당 뒤 과거 승인을 재사용하지 않습니다. 모든 action write와 knowledge state/apply/import는 트랜잭션 안에서 요청에 사용한 exact credential을 다시 인증합니다. 모델 경로는 미확인 텍스트를 기본 `RESTRICTED` 이상으로 다루며, 호출 전·후 credential과 검색 근거를 다시 계산하고 바뀌면 생성 결과를 반환하지 않습니다.

### 릴리즈 평가

`POST /v1/release/evaluate`와 `ax release evaluate`는 baseline/candidate의 품질, 불필요 거부, 지연, 비용을 비교합니다. pack·data contract·model·prompt·policy·case set·rubric·code의 version/hash를 묶은 target manifest가 없거나 evidence·case의 manifest hash가 다르면 `blocked`입니다. 실제 criteria의 canonical SHA는 rubric SHA와, 정렬된 case ID·domain·fixture digest 집합 SHA는 case-set SHA와 같아야 하며 중복 case ID는 입력 오류입니다. 지표는 반올림 전 case 원값의 산술평균으로 threshold를 판정합니다. 안전 실패, 권한 위반, 삭제 누락은 veto입니다. 이 결합은 fixture 내용·측정·evidence origin을 인증하지 않습니다. 합성 평가만으로 현업 검토 자격을 얻지 못하며, `eligible_for_field_review`도 입력 기반 추천일 뿐 출시 승인이나 live validation이 아닙니다.

## API와 CLI 빠른 표

| 기능 | CLI | HTTP |
|---|---|---|
| 온보딩 | `ax onboard evaluate REQUEST` | `POST /v1/onboard` |
| 릴리즈 | `ax release evaluate EVALUATION CRITERIA` | `POST /v1/release/evaluate` |
| 계약 검증 | `ax contract validate REGISTRY` | 서버 등록 |
| 지식 상태 | `ax knowledge state` | `GET /v1/knowledge/state` |
| 지식 변경 | `ax knowledge apply BATCH` | `POST /v1/knowledge/apply` |
| snapshot 반입 | `ax knowledge import SNAPSHOT` | `POST /v1/knowledge/import` |

지식 CLI는 `AX_API_BASE`와 `AX_TOKEN`을 사용하는 loopback API 클라이언트입니다. JSON 파일을 읽는 CLI는 `AX_INPUT_ROOT` 안의 일반 로컬 파일만 허용하며, 기본 root는 현재 작업 디렉터리입니다. init/assets 출력과 서버 운영 설정 경로는 이 guard의 범위가 아닙니다. 데이터 계약 파일은 `AX_DATA_CONTRACTS_FILE`로 서버에 지정합니다. 자세한 기동 예는 [운영 가이드](OPERATIONS.md)에 있습니다.

## 적용 전 최소 체크

1. 업종 이름이 아니라 데이터 등급·전송·리전·보존·통신 조건으로 offline/private/gateway/hybrid를 선택합니다.
2. 위험, 관할, 보존, 소유자, 위탁·국외전송을 검토하고 unknown을 닫습니다.
3. source contract와 company profile을 승인된 근거에서 만듭니다.
4. 합성 dry run, 현업 gold, shadow, staged promotion, rollback을 순서대로 수행합니다.
5. 모델·온톨로지·도구·계약의 ID/version/hash와 비용·평가·승인을 함께 기록합니다.
6. v0.2 독립 감사와 현장 검토 증거를 v0.1 감사와 분리합니다.

## 현재 한계

- SQLite 단일 파일의 동시성·고가용성·물리 삭제는 기업 운영 요구를 자동 충족하지 않습니다.
- audit hash chain은 audit event 연쇄만 검증합니다. 문서 row 전체, knowledge state head, 전체 DB 교체를 검증하지 않으며 외부 anchor도 없습니다.
- 문서 read guard는 ID·source version·tenant·본문 SHA·ACL SHA 불일치만 fail-closed로 검사합니다. title·scope·`valid_until`·source URI·전체 canonical JSON·state head의 무결성 보장은 아닙니다.
- 팩·신원·provider·계약 registry 파일과 SQLite 파일의 ACL·운영자 신원·배포 무결성은 외부 통제입니다. registry 파일 교체와 DB commit은 하나의 원자적 변경이 아닙니다.
- snapshot adapter는 변경 문서 delta upsert 경계입니다. 전체 source reconciliation, OCR, embedding, 악성 파일 검사, 원천 API connector나 누락 문서 자동 삭제기가 아닙니다.
- knowledge state는 호출자별 투영이며, 보이지 않는 문서·source head의 부재나 tenant 전체 재고 완전성을 증명하지 않습니다.
- tenant-prefixed managed ID는 cross-tenant 선점을 막지만 같은 tenant 안의 ID 사용 여부 추론을 막지 않습니다. ID 할당과 더 강한 물리 격리는 운영 책임입니다.
- 멱등 replay 응답의 문서 배열도 현재 가시성 투영입니다. 과거 저장 영수증 전체를 계속 열람할 권리나 응답 byte 동일성을 보장하지 않습니다.
- OIDC access-token 검증은 기업 IdP 로그인 전체가 아닙니다.
- GraphRAG, vector DB, reranker, 실제 외부 action connector는 포함하지 않습니다.
- 공식 표준과 공개 기업 사례는 설계 참고 자료이며 이 프로젝트의 효과나 규제 적합성을 증명하지 않습니다.
- 기존 v0.1 감사는 v0.2 변경의 완료 증거가 아닙니다.
