# v0.3 보안 모델과 남은 기업 통제

보호 대상은 업무 원문과 파생물, 객체·관계, 사용자 권한, 지식 변경, 검토 제안, 승인·실행·릴리즈 기록입니다. 이 저장소는 단일 운영자 환경에서 경계를 재현하는 참조 런타임입니다. 인터넷 공개 서비스, SSO 전체 흐름, 불변 원장, 물리 삭제, 실제 ERP 쓰기를 검증한 제품이 아닙니다.

## 신뢰 경계

사용자 입력, 문서 본문, 모델 출력, 원천 파일의 자기 주장과 네트워크 위치는 신뢰하지 않습니다. 관리자가 승인해 서버에 배포한 도메인팩, 회사 정책, 데이터 계약 레지스트리, identity registry, pinned public JWKS와 로컬 파일 권한은 현재 구현의 신뢰 전제입니다. 이 전제를 수정할 수 있는 관리자를 통제하는 KMS, 변경 승인, 배포 서명, WORM/SIEM은 외부 인프라가 제공해야 합니다.

| 경계 | 구현한 통제 | 기업 환경에서 추가할 통제 |
|---|---|---|
| 사용자 → API | 명시적 `opaque_only`/`jwt_only`/`both`, 요청마다 현재 registry 사용, 서버 `Principal` 매핑, body/host 제한 | TLS, MFA, IdP 로그인·세션, 기기 신뢰, 속도·동시성·쿼터, 운영 key rotation |
| 원천 → 지식 변경 | 서버 등록 `DataContractRegistry`, contract ID/version/hash binding, upsert 전 tenant 문서 ID namespace, 기존 문서 저장 ACL tenant/group/clearance 쓰기 검사, source·scope·content/provenance hash, CAS·멱등 namespace·version history·watermark | 원천 인증, 신뢰 가능한 ID 할당자, 커넥터 자격증명, 서명·전송 보안, 스키마·품질·ACL 동기화, quarantine 운영 |
| SQLite → 현재 pack | 현재 registry binding과 일치하는 active managed 문서만 조립, 문서 ID·source version·tenant·본문/ACL hash read 검사, bootstrap 정적 정책 | title·scope·유효기간·source URI·state head 전체 무결성, DB 암호화, RLS, HA, 외부 감사 앵커, 백업 암호화·복원 훈련 |
| SQLite → 지식 상태 응답 | `READ+AUDIT+MANAGE_KNOWLEDGE`, actor 등급·그룹, 현재 계약 ACL로 문서 메타데이터·source head 제한, retire/tombstone ACL snapshot 유지, ACL 불명 legacy 메타데이터 숨김 | tenant head 자체의 행 단위 투영, 원천 ACL 자동 동기화, 특권 관리자용 전체 재고·외부 대조 |
| 자료 → 검색 | tenant·그룹·등급·목적·READ를 검색 전에 적용, 관계 탐색 한도, 숨은 객체 404 | 필드·사용자별 투영, 파생 ACL, 원천 정정·삭제 전파, 인덱스·캐시·embedding 동등 통제 |
| 검색 → 모델 | 현재 credential·근거·scope 객체·분류·반출·HTTPS host를 호출 직전 재검사, 미확인 텍스트 기본 `RESTRICTED`, 외부 경로 기본 거부 | DLP, egress firewall·DNS/proxy/tunnel 차단, 공급자 리전·보존·학습·하위처리자 계약, rate limit |
| 모델 → 응답 | JSON 계약, 인용 ID·연속 원문 검사, 응답 후 credential·근거 재검사, 실행 도구 미연결 | 의미 정확성·위해성 red team, 출력 필터, 사용자 교육, prompt/response 로그 정책 |
| 제안 → 실행 | human 승인자, subject와 `person_id` 동일인 차단, payload/object/evidence/contract binding 재검사, action write 직전 exact credential 재인증 | 실제 시스템 최소권한 커넥터, 한도·강한 재인증, dual control, 결과 대조, 중단 스위치 |
| 실행 → 기록 | SQLite 트랜잭션 안의 상태·영수증·감사, tenant별 체인 | KMS 서명, 외부 chain head, WORM/SIEM, 접근·거부·반출 감사, 재해복구 |

팩·신원·provider·데이터 계약 registry 파일과 SQLite 파일은 운영자가 배포하고 권한을 관리하는 신뢰 입력입니다. 런타임 검증이 운영체제 계정, 파일 소유자나 배포자의 신원을 인증하지는 않습니다. 서비스 계정 최소권한, 파일·디렉터리 ACL, 원자 교체, 변경 승인, 백업 접근 통제와 호스트 무결성을 별도로 운영합니다.

## access token 검증의 정확한 범위

`IdentityRegistry.authentication_mode`의 기본값은 `opaque_only`입니다. OIDC 설정만 쓰려면 `jwt_only`, opaque와 OIDC를 함께 쓰려면 `both`를 명시해야 합니다. 모드와 실제 bindings/OIDC 구성의 조합이 맞지 않으면 registry 자체를 거부하므로, OIDC 블록을 추가하는 것만으로 JWT 경로가 암묵적으로 켜지지 않습니다.

검증기는 다음 조건을 모두 요구합니다.

- JOSE header의 `alg=RS256`, 등록된 `kid`, `typ=at+jwt` 또는 `application/at+jwt`
- registry에 고정한 HTTPS `iss`와 단일 `aud`의 정확한 일치
- 필수 `sub`, `client_id`, `jti`, `exp`, `iat`의 존재·형식과 현재 시각 검증; `nbf`가 있으면 유효 시작 시각 검증
- pinned JWKS 안의 RSA 서명키와 서명 검증; 약한 키·중복 키·알 수 없는 키 거부
- `(issuer, subject)`가 enabled 서버 binding에 등록되고 `client_id`가 binding의 allowlist에 있을 것
- user binding은 `sub != client_id`와 human Principal, service binding은 `sub == client_id`와 service Principal일 것
- 토큰의 tenant, group, role, clearance 같은 권한 주장은 무시하고 binding의 `Principal`만 사용
- `jku`, `x5u`, inline `jwk`, `crit`처럼 토큰이 키 선택을 바꾸는 header 거부

이것은 access token을 resource server에서 검증하는 한 경로입니다. OIDC discovery, authorization endpoint, 로그인 UI, authorization code와 PKCE, refresh token, logout, SCIM, SAML, MFA, DPoP/mTLS, 동적 JWKS 수집을 구현하지 않습니다. 따라서 “SSO를 구현했다”거나 특정 IdP 통합이 끝났다고 표현하지 않습니다. 운영 키 회전은 관리자가 검증한 public JWKS를 겹쳐 배포하고 이전 키를 제거하는 절차와 실제 IdP 시험이 필요합니다.

## 권한 회수와 시간차

identity 파일이 설정된 서버는 요청마다 현재 registry를 다시 읽습니다. 모든 action write(propose/approve/execute/rollback)와 knowledge state/apply/import는 transaction을 연 직후 read/replay보다 먼저 **처음 전달된 바로 그 credential**을 다시 인증합니다. 모델 egress 전후에도 같은 credential과 검색 근거를 다시 평가합니다. raw credential은 응답, 로그, 감사 이벤트, SQLite에 저장하지 않습니다. 이 설계는 한 요청 안의 TOCTOU 창을 줄이지만 파일시스템 배포 지연, 여러 서버의 설정 불일치, 이미 외부로 전송한 데이터까지 되돌리지는 못합니다.

승인은 `ActorKind.HUMAN`에게만 허용합니다. 제안자와 승인자의 subject가 같으면 거부하고, subject가 달라도 같은 tenant의 `effective_person_id`가 같으면 자기 승인으로 거부합니다. service Principal은 승인할 수 없습니다. 제안 payload에는 proposer의 actor kind/person ID, 승인 record에는 approver의 actor kind/person ID를 고정합니다. 새 제안의 동일 request-key replay와 미완료 제안의 approve·execute는 현재 매핑과 비교하므로 subject가 같아도 뒤의 사람이 재할당되면 거부합니다. 이는 디렉터리가 사람을 정확히 `person_id`로 연결하고 변경을 제때 배포한다는 전제에 의존합니다.

이 binding이 없는 과거 미완료 제안은 안전하게 보완됐다고 추정하지 않고 새 제안과 승인을 요구합니다. 이미 실행되거나 rollback된 terminal 제안의 멱등 execute replay와 rollback 호환 경로는 유지되지만, 호출 주체의 현재 credential·권한 검사는 계속 수행합니다.

권한 회수 시험은 다음을 포함합니다.

1. binding을 disabled로 바꾼 뒤 새 요청이 거부되는지 확인합니다.
2. 모델 호출 직전과 응답 직후 회수·문서 ACL 변경을 주입해 결과가 반환되지 않는지 확인합니다.
3. 승인 뒤 실행 전에 제안자·승인자 권한, 사람 매핑, 모든 근거 snapshot이나 contract binding 중 하나를 바꿔 실행이 막히는지 확인합니다.
4. 다중 인스턴스라면 설정 배포 최대 지연과 오래된 프로세스의 행동을 측정합니다.

## 데이터 계약은 원천 인증서가 아니다

`DataContractRegistry`는 서버가 허용한 원천 식별자·URI, 객체 범위, ACL, 민감도, 목적, 수명주기와 필수 출처 주장을 고정합니다. managed 문서는 수락 당시 contract ID/version/hash를 저장하며, 현재 registry의 tenant/id/version/source/hash가 모두 같을 때만 current pack에 들어갑니다. 계약이 바뀌거나 없어지거나 schema 2 행에 binding이 없으면 fail-closed로 검색·승인·실행 근거에서 제외됩니다. 미바인딩 기존 행은 일반 upsert로 같은 문서 ID의 소유권을 주장할 수 없고 관리자 migration 또는 새 문서 ID 같은 명시적 복구가 필요합니다. bootstrap 정적 문서는 별도의 `bootstrap.<document_id>` 정책을 유지합니다.

apply/import는 SQLite 트랜잭션 진입 직후 exact credential을 확인한 다음 외부 registry를 다시 읽어 요청 시작 때 선택한 계약의 tenant, ID, version과 canonical SHA가 같은지 검사합니다. 달라졌으면 `data_contract_changed`, registry를 읽을 수 없으면 `data_contract_registry_unavailable`로 닫습니다. fresh 계약의 현재 권한과 current pack을 사용하지만, 파일시스템의 registry 교체와 SQLite commit 자체가 하나의 원자적 트랜잭션은 아닙니다.

현재 계약에서 문서를 관리할 수 있다는 사실은 기존 문서 전체의 관리자 권한이 아닙니다. 기존 문서의 upsert, retire, tombstone, ACL 변경은 저장 ACL snapshot의 tenant 일치, group 교집합, clearance를 별도로 확인합니다. 문서 ACL의 purpose는 이 관리 쓰기 검사에 사용하지 않지만, 계약 ACL에 대한 `READ`, `AUDIT`, `MANAGE_KNOWLEDGE`는 계속 요구합니다. 저장 ACL이 없거나 이 범위를 벗어난 기존 문서 mutation은 구체적인 원인을 나누지 않고 404 `document_not_found`로 응답합니다. 이 규칙을 모든 ID 존재 은닉으로 확대하지 않습니다. 같은 tenant의 upsert에서는 미사용 ID의 생성 성공과 이미 사용 중인 비가시 ID의 404, candidate 계약 오류 422가 구분될 수 있습니다. 새 문서는 candidate access가 계약 범위에 맞는지를 검증합니다.

managed upsert는 전역 ID 조회보다 먼저 마지막 점 앞부분이 계약 tenant와 정확히 일치하고, 마지막 접미부가 비어 있지 않으며 점이 없는지를 검사합니다. 위반은 문서 존재와 무관하게 `data_contract_violation` 422입니다. 이 규칙은 cross-tenant ID 탐색과 선점을 막지만 같은 tenant 안의 ID 사용 여부 추론을 없애지 않습니다. ID에는 고객·사건·질환처럼 민감한 의미를 넣지 않고, 신뢰 가능한 서버 할당자와 계약별 접미부 규칙을 사용합니다. 더 강한 격리가 필요하면 tenant별 DB를 사용합니다.

managed upsert와 ACL 변경은 새 `access.groups`가 비면 `data_contract_violation` 422로 트랜잭션 전체를 거부합니다. 빈 그룹은 이후 어떤 actor도 저장 ACL 교집합을 만족하지 못해 active 문서를 정상 경로로 정리할 수 없게 만들기 때문입니다. 비어 있지 않은 다른 그룹으로 바꾸는 self-revoke는 허용하며 반환 영수증 문서가 빈 배열일 수 있습니다. 모든 그룹의 접근을 회수하려면 원천 보존·삭제 판단을 확인한 retire 또는 tombstone을 사용합니다. 공통 `Access`와 bootstrap 등 다른 deny-all 용도의 빈 그룹 의미는 그대로입니다.

이미 존재하는 managed 빈 그룹이나 ACL 불명 legacy 행은 권한을 임의 복구하지 않습니다. state·receipt에서 숨기고 모든 mutation을 404로 닫습니다. 운영자가 원천 소유자, 보존 의무와 삭제 결정을 확인한 통제된 DB migration으로 정리해야 하며, 이 절차를 자동 보안 복구라고 표현하지 않습니다.

ACL 변경은 단순 메타데이터 수정 권한이 아닙니다. 저장 ACL을 만족하는 계약 관리자는 계약이 허용한 범위에서 groups, purposes, 민감도를 확장하거나 줄일 수 있습니다. 특히 purpose 추가는 이후 읽기 경로를 넓힐 수 있으므로 위임 대상을 최소화하고 회사 담당자의 승인·감사를 요구합니다.

기존 upsert는 같은 tenant/source/contract ID와 새 source version으로 현재 version/hash에 명시적으로 재바인딩할 수 있습니다. retire와 ACL 변경은 기존 version/hash까지 현재 계약과 일치해야 합니다. tombstone만은 같은 tenant/source/contract ID라면 version/hash drift 뒤에도 삭제 정리를 허용하고 현재 binding을 tombstone 메타데이터에 기록합니다. 이 예외는 ACL 검사를 우회하지 않으며 타 계약 문서나 ACL 불명 legacy 행을 삭제할 권한도 만들지 않습니다.

신규 namespace 규칙은 bootstrap·읽기 ID와 v0.1 역사 기록을 바꾸거나 기존 unqualified managed ID를 자동 rename하지 않습니다. 따라서 과거 acme 소유 문서가 `beta.doc`처럼 다른 tenant namespace로 보이는 ID를 이미 가질 수 있습니다. 다중 tenant 운영 전에 legacy·bootstrap 문서의 실제 owner, 저장 tenant와 ID prefix를 별도 재고 대조하고 충돌을 통제된 migration으로 해소합니다. 기존 managed ID의 upsert는 422이지만, 현재 binding과 저장 ACL 권한을 충족하는 retire/tombstone 정리는 유지됩니다. 계속 사용할 문서의 ID와 accepted source-version history를 옮기는 작업도 통제된 migration입니다. 이 guard는 신규 managed upsert의 행위자 간 선점 방지이며 trusted bootstrap/admin 파일의 namespace를 검증·재작성하지 않습니다. entity, action, object나 일반 ontology ID 전체의 namespace 보장도 아닙니다.

계약을 registry에서 제거하면 그 계약 ID를 사용하는 API 정리도 `data_contract_not_found`로 막힙니다. 제거 전에 보존을 확인하고 명시적으로 retire/tombstone합니다. 이미 제거했다면 같은 tenant/source/contract ID를 통제해 재등록한 뒤 ACL을 확인하고 drift tombstone으로 정리합니다. 계약의 `delete_within_hours`는 원천·파생물·백업의 실제 삭제 이행이나 증명이 아니며 회사와 원천 담당자가 별도 통제해야 합니다.

지식 문서 read guard는 `Document` JSON 파싱과 문서 ID, source version, access tenant, 본문 SHA, access SHA의 row 메타데이터 일치를 검사하고 불일치를 `knowledge_integrity_failure`로 거부합니다. title, object scope, `valid_until`, source URI, 전체 canonical document JSON이나 state head에는 대응하는 read hash가 없습니다. 따라서 이 검사를 문서 row 전체 또는 DB 전체의 변조 탐지라고 표현하지 않습니다.

문서의 실제 byte hash와 선언 hash를 비교하지만 `origin_authenticated=false`, `provenance_authenticated=false` 경계를 유지합니다. 계약 통과는 파일이 허용된 모양이라는 뜻이며, SharePoint·ERP·센서가 실제로 서명하거나 인증한 기록이라는 뜻은 아닙니다.

단일 파일 snapshot adapter도 같은 경계를 갖습니다. 여기서 snapshot은 전체 원천 상태가 아니라 변경 문서만 보내는 delta envelope입니다. 한 요청에 같은 문서 ID가 둘 이상이면 계약 단계에서 거부하며, API는 422 `invalid_request`, CLI는 `invalid_input_file`로 끝냅니다. 신규 snapshot의 `observed_at`은 미래 시각, 계약 갱신 주기, 같은 tenant/source의 엄격한 단조 증가를 검사하지만 게시자가 제공한 claim일 뿐 실제 원천 수집 시각을 인증하지 않습니다. schema 2 마이그레이션은 과거 `observed_at` 대신 마지막 knowledge batch 감사 시각 또는 migration 시각을 보수적 watermark 상한으로 사용합니다. 이 상한도 원천 진위나 실제 수집 시각을 인증하지 않습니다. 변경 문서는 과거에 수락하지 않은 새 source version을 사용하며, 문서별 history가 이전 version 재사용을 막습니다. delta에서 빠진 문서는 그대로 두고 자동 retire/tombstone하지 않습니다. 운영 커넥터는 서비스 신원, TLS, export 시각·cursor, 누락·중복·순서, rate limit, 원천 ACL·삭제·정정, 실패 격리와 재대조를 별도로 증명해야 합니다.

신규 성공과 멱등 replay 모두 반환 `documents`를 현재 저장 record의 exact binding과 actor의 문서 ACL `READ/AUDIT` 가시성으로 투영합니다. ACL 변경으로 호출자 자신의 group이 빠지면 성공 응답도 빈 배열일 수 있습니다. replay는 저장 영수증과 감사 이벤트를 수정하지 않지만 권한 회수나 계약 변경 뒤 응답 문서 배열은 원래 영수증보다 적을 수 있습니다. 상위 tenant/contract/request/payload/revision 필드가 같다는 사실을 응답 전체의 byte 동일성이나 과거 문서 메타데이터 열람 권한으로 확대하지 않습니다.

## 논리 삭제와 물리 삭제를 구분한다

`tombstone`은 current pack, 검색, approve, execute가 문서를 사용하지 못하게 하고 document JSON의 본문·title·source URI를 지식 행에서 제거합니다. source version/history와 원 ACL snapshot, 논리 삭제 메타데이터는 남는 metadata-only logical tombstone입니다. 다음을 증명하지 않습니다.

- SQLite 페이지, WAL, 파일시스템 snapshot과 백업의 물리 삭제
- 이전 로그, 캐시, embedding·vector index, OCR·전사 결과의 삭제
- 원천 SharePoint·ERP·파일 저장소의 삭제
- 모델 provider·게이트웨이·관측 시스템의 삭제
- 암호화 키 폐기나 포렌식 복구 불가 상태

retire와 tombstone은 변경 직전의 ACL snapshot을 메타데이터에 유지합니다. 따라서 본문이 사라진 tombstone도 원래 ACL을 만족하는 감사 주체에게만 상태가 보입니다. 이전 schema에서 ACL snapshot을 안전하게 복원할 수 없는 메타데이터는 허용으로 추정하지 않고 상태 응답에서 숨깁니다. tenant revision/state hash는 전체 tenant 변경의 CAS aggregate이므로 보이지 않는 행의 구체 내용을 드러내지는 않지만 변경 발생 자체를 추론하는 신호가 될 수 있습니다. 이 제한 때문에 `knowledge state`를 tenant 전체 자산 목록이나 삭제 완료 보고서로 사용해서는 안 됩니다.

삭제 완료를 주장하려면 [위험·관할·데이터 검토서](../templates/risk-data-review.md)에 매체별 삭제 요청, 수행자, 완료 시각, provider 증명과 복원·잔존 확인을 기록합니다.

## 모델 반출과 로그

모드 선택은 업종명이 아니라 실제 데이터와 계약으로 합니다. 개인정보·의료·금융 데이터가 포함된다고 모든 환경에서 무조건 on-premises가 되는 것은 아니며, 법무·보안·개인정보 담당자가 배치·전송·리전·보존·하위 처리자·로그 조건을 확인해야 합니다.

모델에 보내기 전 provider의 `minimum_query_sensitivity`, 질문, 현재 근거, 인용의 민감도 중 가장 높은 등급으로 경로를 제한합니다. 기본 하한은 `RESTRICTED`이므로 분류되지 않은 텍스트가 낮은 등급으로 간주되지 않습니다. 운영자가 이 하한을 낮추려면 검증된 channel과 회사 분류·반출 정책 근거를 릴리즈 기록에 남겨야 합니다. 외부 모드는 명시적 egress 승인과 정확한 HTTPS host가 필요하며 실패 시 다른 cloud로 자동 우회하지 않습니다. OCR, embedding, prompt·completion, tool 인수와 OpenTelemetry 속성에도 같은 분류가 적용됩니다. OTel GenAI semantic convention은 개발 상태이고 검색문·시스템 지시 속성은 민감할 수 있으므로 원문 수집을 기본값으로 두지 않습니다.

`local` mode의 loopback host 검사는 첫 hop만 고정합니다. loopback 서버가 원격 provider로 forward하거나 cloud model을 선택하는지, 로컬 proxy·SSH tunnel·VPN이 데이터를 반출하는지는 증명하지 않습니다. Ollama를 쓸 때는 공식 절차에 따라 `server.json`의 `disable_ollama_cloud: true` 또는 `OLLAMA_NO_CLOUD=1`을 적용하고 서버 재시작 뒤 로그의 `Ollama cloud disabled: true`를 확인합니다. 이 확인만으로 무반출이나 회사 보안 인증이 되지는 않습니다. LOCAL을 무반출 경로로 승인하려면 backend 구성과 model artifact를 대조하고 원격 forwarding·cloud model·proxy·tunnel을 차단해야 합니다. 필요한 환경에서는 OS/container outbound default-deny, 허용 DNS와 endpoint만 남기는 egress 정책, KMS/secret manager, 실제 패킷 검사를 적용합니다. 공식 근거는 [자료 카탈로그](SOURCE_CATALOG.md)에 기록했습니다.

Wiki 모델 초안은 검토 payload, page와 export manifest에 `generation_route`를 남깁니다. 값은 `mode`, `endpoint_host`, `model`, 비밀값을 포함하지 않는 `provider_settings_sha256`입니다. API key·token·credential 원문은 hash preimage와 export에 넣지 않습니다. 이 provenance는 요청에 사용한 설정을 식별할 뿐 backend의 실제 모델, 물리 실행 위치, 원격 forwarding, 전송된 byte나 provider 삭제 이행을 인증하지 않습니다.

## 로컬 JSON CLI 입력 경계

JSON 파일을 받는 `assess`, `process`, `pack validate/eval`, `action propose`, `onboard evaluate`, `release evaluate`, `contract validate`, `knowledge apply/import`는 `local_input.py`를 사용합니다. `AX_INPUT_ROOT`를 지정하지 않으면 현재 작업 디렉터리가 root이며, 그 밖의 파일·UNC·Windows device name·ADS·reparse point·symlink 경로를 거부합니다. 파일 크기와 JSON 계약도 검사하고 raw 입력이나 비밀값을 출력하지 않습니다.

`ax init`·`ax assets`가 쓰는 출력 목적지와 runtime이 읽는 운영자 설정 경로는 다른 신뢰 경계이며 이 입력 guard를 적용하지 않습니다. 생성 디렉터리 소유권, 설정 파일 ACL, 배포 무결성은 별도 운영 통제입니다.

## 공격·실패 가정과 한계

1. 문서에는 프롬프트 인젝션이 있을 수 있습니다. 문서 내용은 근거이지 시스템 지시가 아니며 모델에게 실행 권한을 주지 않습니다.
2. 공급망 패키지·모델·업종팩·도구 설정은 변조될 수 있습니다. 버전·해시·검토자와 rollback 대상을 릴리즈 기록에 고정합니다.
3. `audit_check`의 해시 체인 검증 범위는 tenant의 audit event 연쇄뿐입니다. 문서 row의 전체 canonical JSON, title·scope·`valid_until`, entity·proposal, knowledge state head 또는 DB 파일 전체를 audit chain이 덮는다고 해석하지 않습니다. DB를 통제한 관리자의 전체 DB 교체·감사 chain 재작성·꼬리 삭제도 외부 anchor 없이 탐지한다고 보장하지 않습니다.
4. SQLite는 저장 암호화, RLS, HA, 다중 writer의 기업 규모 격리를 제공하지 않습니다.
5. 모델의 인용 substring 검사는 허위 원문 인용을 줄이지만 답변 의미의 완전성·정확성·공정성·안전을 인증하지 않습니다.
6. release gate는 criteria canonical SHA와 정렬된 case ID/domain/fixture digest 집합 SHA를 manifest에 결합하고 중복 case ID를 거부합니다. raw 산술평균으로 threshold를 판정하지만 fixture 내용, 측정 수행이나 evidence origin을 인증하지 않으며 적대적 시험, 개인정보 영향평가, 모의해킹, 법무 판단을 대체하지 않습니다.
7. delta snapshot 누락 자동삭제가 없으므로 원천 삭제·정정 전파를 별도 사건으로 처리하지 않으면 오래된 문서가 남을 수 있습니다.
8. 상태와 replay 영수증의 문서 목록은 호출자에게 허용된 투영입니다. 보이지 않는 문서·source head가 없다는 결론, 과거에 보였던 문서를 계속 볼 권리 또는 tenant 전체 재고의 완전성을 이 응답 하나로 증명할 수 없습니다.

보안 검토의 기준 자료와 상태는 [SOURCE_CATALOG.md](SOURCE_CATALOG.md)에, 운영 전 점검과 사고 대응은 [OPERATIONS.md](OPERATIONS.md)에 있습니다.

## Wiki의 추가 경계

파생 Wiki는 raw 문서와 별도 저장합니다. 모델에 전달한 모든 원문·질문을 최고 분류와 서버 floor에 결속하고 source별 snapshot AND current ACL을 적용합니다. query anchor와 hop traversal에서 분류에 기여한 scope 객체도 검토 hash에 결속하고 작성자·reviewer·독자의 현재 객체 접근권한을 각각 검사합니다. source 변경을 같은 transaction에서 stale/scrub으로 전파하며 replay·검토·조회 때 현재 credential·원문·객체·분류를 다시 검사합니다. source tombstone은 종속한 모든 버전과 초안의 live-cell 내용을 제거하지만 WAL·백업·다운로드 사본의 물리 삭제는 증명하지 않습니다.

객체와 원문 ACL을 만족해도 저장 query의 현재 관계 탐색으로 결속 객체 전체에 도달하지 못하면 Wiki를 읽거나 게시할 수 없습니다. 관계의 ACL 회수와 민감도 상승은 조회·export에서도 다시 확인합니다. 현재 관계 분류가 저장 분류를 넘으면 결과를 숨기고 재컴파일·재검토를 요구합니다. 현재 허용된 대체 경로는 인정하지만 과거 링크 ID·type·경로 snapshot은 결속하지 않으며, 관계 변경이 자동으로 stale 상태를 기록하거나 재컴파일 작업을 예약하지는 않습니다.

작성자와 검토자는 모두 server registry의 HUMAN이며 non-null effective person이 있어야 합니다. 현재 SERVICE 작성은 403이고 서비스 위임 작성은 지원하지 않습니다. 검토자는 `READ+APPROVE`로 전체 입력과 payload를 읽을 수 있고 작성자와 effective person이 달라야 게시합니다. 인용 substring 존재와 입력 hash·CAS는 byte 결속과 동시 수정 방지이며, 검토 수행·문장 의미·출처 진위·프롬프트 인젝션 저항을 인증하지 않습니다.

`DataContractRegistry.evidence_roles`의 `derived_output`은 current pack에서 제외됩니다. role을 생략한 legacy 계약, `contract_id=None` bootstrap 문서와 registry 없는 실행은 v0.2 호환상 raw로 허용되므로 기업 적용에서는 모든 관리 원천 계약과 role을 완전 등록합니다. role을 derived로 재분류하면 다음 current pack부터 page가 숨겨지지만 자동 watcher나 재compile queue는 없습니다. 운영자가 영향 범위를 찾아 새 raw 원천으로 재검토해야 합니다.

export marker 검사는 BOM·앞 공백을 정규화하고 CLI 원형 JSON의 `text`도 확인합니다. 임의 frontmatter로 marker를 감추거나 marker를 제거하고 raw로 등록하거나 source metadata를 위조하는 공격은 인증해 차단하지 못합니다. registry role, 인증된 connector와 변경 승인이 1차 통제입니다.

Markdown export는 비권위 snapshot입니다. HTML tag와 모든 Markdown image 표기를 거부해 알려진 자동 이미지 요청 경로를 줄입니다. 일반적인 Markdown 렌더링 보안 인증은 아니므로 downstream viewer는 HTML·스크립트·위험한 URL·원격 자원·파일 접근을 따로 격리/정제해야 합니다. HTTP API의 title·body·question·link ID도 plain data이며 클라이언트가 렌더링할 때 escape, URL scheme allowlist와 CSP를 적용합니다. 작성자 입력 metadata는 원천 ACL에서 자동 생성되지 않으므로 독립 검토 범위에 포함합니다.

`proposer_person_id`와 `reviewer_person_id`는 내부 person directory와 결합될 때 개인정보가 됩니다. page 독자에게 이 필드를 반환할 필요, 로그·export 포함 범위, 보존기간, 접근기록, 정정·삭제와 legal hold 예외를 개인정보 담당자가 승인해야 합니다. source tombstone 뒤에도 page ID, request key, version ID, source dependency, 최소 audit actor·event·시각·hash가 남을 수 있으므로 scrub 필드와 잔존 필드를 운영 장부에 명시합니다. 다운로드 뒤 권한 회수와 법적 보존 충돌은 외부 운영 절차가 필요합니다.
