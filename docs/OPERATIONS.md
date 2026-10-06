# 운영 가이드

v0.3 운영의 기본 단위는 **팩 파일 + 신원 파일 + 데이터 계약 레지스트리 + SQLite 파일**입니다. 검토된 Wiki도 별도 테이블로 같은 DB에서 관리합니다. 서버는 이 네 항목을 운영자가 정한 경로에서 읽습니다. 온보딩과 릴리즈 평가는 입력 계약을 결정적으로 판정하지만, 현장 보안 인증이나 실제 배포 승인을 대신하지 않습니다.

## 1. 기동 전 확인

| 항목 | 환경 변수 | 운영 확인 |
|---|---|---|
| 도메인팩 | `AX_PACK_FILE` | 승인된 파일인지, 버전과 해시가 배포 기록과 일치하는지 확인 |
| 신원·인증 | `AX_AUTH_FILE` | 파일 ACL, 토큰/JWKS 변경 절차, 비활성 주체가 반영됐는지 확인 |
| 상태 DB | `AX_DB_FILE` | 절대 경로, 상위 폴더 존재, 파일 ACL·암호화·백업 정책 확인 |
| 데이터 계약 | `AX_DATA_CONTRACTS_FILE` | 서버가 등록할 계약만 포함하고 소유자·원천·ACL·보존 정책을 검토 |
| 모델 경로 | `AX_PROVIDER_FILE` | 선택 사항. 반출 승인, 등급 상한, 대상 호스트, 모델 ID를 확인 |
| CLI 입력 root | `AX_INPUT_ROOT` | 선택 사항. 생략하면 현재 작업 디렉터리이며 로컬 JSON 입력을 이 경계 안으로 제한 |

`AX_DB_FILE`은 절대 경로여야 하고 상위 폴더가 먼저 존재해야 합니다. 데이터 계약 파일을 생략하면 읽기·검색은 가능하지만 지식 변경 API는 `data_contract_registry_required`로 닫힙니다. 지정한 계약 파일이 사라지거나 유효하지 않으면 지식 변경은 `data_contract_registry_unavailable`로 거부됩니다.

```powershell
uv run ax init .runtime\pilot --domain procurement
$taskPilot = (Resolve-Path .runtime\pilot).Path
$env:AX_PACK_FILE = Join-Path $taskPilot 'domain-pack.json'
$env:AX_AUTH_FILE = Join-Path $taskPilot 'identities.json'
$env:AX_DB_FILE = Join-Path $taskPilot 'pilot.db'
$env:AX_DATA_CONTRACTS_FILE = Join-Path $taskPilot 'data-contracts.json'
uv run uvicorn ax_starter.runtime:load_app --factory --host 127.0.0.1 --port 8000
```

이 명령은 로컬 참조 런타임을 시작합니다. 외부 포트 노출, TLS 종료, 기업 SSO 로그인, WAF, 중앙 비밀 저장소, 고가용성 구성은 포함하지 않습니다.

## 2. 운영 명령과 API

| 목적 | CLI | API | 실패 의미 |
|---|---|---|---|
| 도입 진단 | `uv run ax onboard evaluate <request.json>` | `POST /v1/onboard` | 차단·보류 판정이면 CLI 종료 코드 2 |
| 릴리즈 판정 | `uv run ax release evaluate <evaluation.json> <criteria.json>` | `POST /v1/release/evaluate` | 현업 검토 자격 미충족이면 종료 코드 2 |
| 계약 형식 검증 | `uv run ax contract validate <registry.json>` | 서버 기동 시 등록 | 입력 형식만 확인하며 원천 진위를 인증하지 않음 |
| 지식 상태 | `uv run ax knowledge state` | `GET /v1/knowledge/state` | tenant head와 호출자의 등급·그룹·관리 가능 계약으로 제한된 source head·문서 메타데이터를 반환 |
| 지식 변경 | `uv run ax knowledge apply <batch.json>` | `POST /v1/knowledge/apply` | 계약·CAS·권한·멱등성 검사 실패 시 전체 트랜잭션 거부 |
| delta 스냅샷 반입 | `uv run ax knowledge import <snapshot.json>` | `POST /v1/knowledge/import` | 변경된 정규화 UTF-8 문서만 계약 기반 upsert; 누락은 삭제가 아님 |

JSON 파일을 받는 CLI는 `local_input.py`를 거칩니다. `AX_INPUT_ROOT`를 생략하면 현재 작업 디렉터리가 root이며, root 밖 경로, UNC·device·ADS, symlink·reparse point, 크기 한도를 넘는 파일을 거부합니다. `ax init`·`ax assets`의 출력 목적지와 서버가 읽는 운영자 설정 경로는 다른 신뢰 경계이므로 이 입력 guard의 보호 대상으로 보지 않습니다. `knowledge` 명령은 loopback API에 접속하므로 `AX_API_BASE`와 `AX_TOKEN`이 필요하며 loopback 이외의 주소를 거부합니다.

```powershell
$taskPilot = (Resolve-Path .runtime\pilot).Path
$env:AX_API_BASE = 'http://127.0.0.1:8000'
$taskCredentials = Get-Content (Join-Path $taskPilot 'demo-credentials.json') -Raw | ConvertFrom-Json
$env:AX_TOKEN = ($taskCredentials.credentials | Where-Object subject -eq 'steward').token
uv run ax knowledge state
uv run ax knowledge import (Join-Path $taskPilot 'source-snapshot.json')
uv run ax knowledge state
```

서버는 첫 터미널에 두고 이 블록은 두 번째 터미널에서 실행합니다. `ax init`이 만든 `steward`와 파일은 합성 학습용입니다. 토큰을 명령줄 인수, 문서, Git, 터미널 기록에 넣지 않습니다. 작업이 끝나면 `Remove-Item Env:AX_TOKEN`으로 현재 셸에서 지웁니다.

## 3. 도입 진단 운영

`CompanyProfile`과 `BusinessIntake`를 함께 제출합니다. 값이 없으면 추측해 채우지 않고 `null` 또는 `unknown`으로 둡니다. 판정은 다음 세 상태 중 하나입니다.

- `blocked`: 명시적인 거절 승인·정책 충돌이 있거나, 배치·민감도·전송·리전·모델·도구·접근·업무 소유자처럼 안전한 경로를 정하는 핵심 정보/근거가 미확인임.
- `on_hold`: 핵심 차단 조건은 없지만 비핵심 정보·근거·승인이 아직 남음.
- `pilot_review`: 입력상 통제된 파일럿 검토 단계로 이동할 수 있음.

`ProfileEvidence.region_policy`, `model_policy`, `tool_policy`가 `UNKNOWN`이면 각각 고정된 `*_evidence_unknown` 이유를 남기고 `blocked`입니다. `REPORTED`는 누락을 제출자의 자기신고로 채우지만 원천 진위나 통제 작동을 검증하지 않습니다. 응답의 `assurance=self_reported_readiness`, `live_validated=false`, `security_certified=false`는 고정 경계입니다. `pilot_review`도 기업 보안 인증, 현장 네트워크 검증, 개인정보 영향평가, 규제기관 승인 또는 운영 배포 허가가 아닙니다. 업종 이름만으로 배치 방식을 강제하지 말고 [도입 가이드](ADOPTION.md)의 실제 데이터·계약·통신 조건으로 선택합니다.

## 4. 지식 변경 절차

지식 변경 권한은 `manage_knowledge` 작업과 `audit` 목적을 모두 가진 서버 측 `Principal`에만 부여합니다. 운영자는 다음 순서를 지킵니다.

1. `knowledge state`로 현재 `tenant_revision`, 허용된 source별 revision/state hash, 보이는 문서별 source/version/hash/ACL/lifecycle을 읽습니다. 이 응답은 호출자의 등급·그룹과 관리 가능한 계약으로 제한되므로 tenant 전체 재고로 해석하지 않습니다.
2. 서버에 등록된 `contract_id`를 선택합니다. 요청자가 계약 객체를 함께 보내 등록을 우회할 수 없습니다.
3. 새 `request_key`, 현재 `expected_tenant_revision`, `sources`에서 확인한 해당 원천의 `expected_source_revision`을 넣습니다. `apply`와 `import`의 request-key 공간은 분리되어 있습니다. 신규 managed 문서 ID는 tenant가 `acme`라면 `acme.<점이 없는 접미부>` 형식으로 신뢰 가능한 할당자가 발급합니다.
4. 기존 문서라면 주체가 저장 ACL snapshot의 tenant, group, clearance를 만족하는지 확인한 뒤 upsert/retire/tombstone/ACL 변경을 한 배치로 제출합니다. 문서 purpose는 이 쓰기 검사에서 생략되지만 계약의 `READ+AUDIT+MANAGE_KNOWLEDGE`는 필요합니다.
5. 영수증의 payload hash와 새 revision을 보관하고 상태를 다시 읽습니다. 반환 `documents`는 현재 ACL·exact binding 투영이므로 성공한 모든 변경 문서를 항상 담는다고 가정하지 않습니다.
6. 재시도할 때는 같은 의도와 같은 payload에 같은 `request_key`를 씁니다. 같은 namespace의 같은 키에 다른 payload를 보내면 `idempotency_conflict`입니다. 저장 영수증은 바뀌지 않지만 replay 응답의 `documents`는 현재 ACL·binding 가시성으로 줄 수 있습니다.

tenant 또는 source revision이 달라지면 최신 상태를 다시 읽고 변경 의도를 재검토합니다. revision 숫자만 새 값으로 바꾸어 자동 재전송하지 않습니다. 각 문서에서 한 번 수락한 source version은 이후 retire·새 버전 반영 뒤에도 재사용할 수 없습니다. 배치 중 하나라도 실패하면 문서·수락 버전 history·source watermark·revision·감사 이벤트가 함께 롤백됩니다.

기존 문서 upsert는 저장 ACL 권한을 통과하고 현재 요청 계약의 tenant, source, contract ID가 저장 binding과 같으며 새 source version을 쓸 때 현재 contract version/hash로 다시 묶입니다. retire와 ACL 변경은 저장된 contract version/hash까지 현재 요청 계약과 정확히 같아야 합니다. tombstone은 저장 ACL 권한과 tenant/source/contract ID가 같으면 version/hash drift를 허용하고 현재 binding으로 기록합니다. 그래서 계약 v1 문서를 v2에서 삭제할 때 중간 ACTIVE upsert로 재게시하지 않아도 됩니다. 다른 계약 문서, ACL을 알 수 없는 legacy 행 또는 권한 밖 기존 문서 mutation은 구체적인 이유를 나누지 않고 404로 거부됩니다. 새 문서는 저장 ACL이 없으므로 candidate access를 계약과 대조합니다. 계약의 `required_provenance`는 정렬된 canonical 직렬화로 hash가 계산되므로, 같은 계약의 집합 순서 차이를 임의 변경으로 만들지 않습니다.

쓰기 ACL은 문서의 tenant, group, clearance만 확인하며 문서 purpose를 적용하지 않습니다. 따라서 `knowledge state`에서 숨겨진 모든 문서를 쓰기 불가라고 단정하지 않습니다. state는 `AUDIT` 목적까지 적용한 읽기 투영이고, mutation은 위 저장 ACL과 계약 권한을 각각 검사합니다. `change_acl` 담당자는 계약 범위 안에서 groups, purposes, 민감도를 넓히거나 줄일 수 있으며 purpose 추가는 이후 본문 읽기 범위를 넓힐 수 있습니다. 이 권한을 단순 메타데이터 편집으로 위임하지 말고 회사 담당자의 변경 승인과 사후 대조를 둡니다.

managed upsert는 DB 조회 전에 문서 ID의 마지막 점 앞부분이 계약 tenant와 정확히 같고 마지막 접미부가 비어 있지 않으며 점을 포함하지 않는지 검사합니다. 위반은 ID 존재 여부와 관계없이 `data_contract_violation` 422이고 배치의 revision·감사·history는 바뀌지 않습니다. cross-tenant ID 탐색·선점은 막지만 같은 tenant에서는 미사용 ID 생성 성공과 이미 사용 중인 비가시 ID의 404가 달라 ID 사용 여부를 추론할 수 있습니다. ID에 민감한 업무 의미를 넣지 않고 서버 할당자와 계약별 접미부 규칙을 사용합니다. 더 강한 격리가 필요하면 tenant별 DB를 사용합니다.

managed upsert와 ACL 변경에 넣는 새 `access.groups`는 한 개 이상이어야 합니다. 빈 그룹은 `data_contract_violation` 422이며 같은 배치의 문서, tenant/source revision, 감사와 accepted-version history는 모두 불변입니다. 비어 있지 않은 다른 그룹으로 바꾸는 self-revoke는 가능하고 성공 응답 `documents`가 비어 있을 수 있습니다. 모든 그룹에서 회수하려는 문서는 빈 ACL의 active 상태로 남기지 말고, 실제 보존 요구를 확인한 뒤 retire 또는 tombstone을 명시적으로 제출합니다.

### 생명주기 의미

| 상태 | 검색·근거 사용 | 본문 | 운영 의미 |
|---|---|---|---|
| `active` | 가능 | 유지 | 현재 계약과 유효기간을 만족하는 문서 |
| `retired` | 불가 | 유지 | 변경 직전 ACL snapshot으로 메타데이터 노출 제한; 다시 활성화하려면 새 source version의 upsert를 재검토 |
| `tombstone` | 불가 | document JSON의 본문·title·source URI 제거 | source version/history와 변경 직전 ACL snapshot 유지, 현재 contract binding 기록; 같은 문서 ID 재생성 금지 |

`tombstone`은 metadata-only 논리 삭제입니다. SQLite 파일의 미할당 페이지, WAL, 운영체제 캐시, 스냅샷, 백업, 벡터 인덱스, 모델 제공자 보관분의 물리 삭제를 증명하지 않습니다. 이 경로들은 각 저장소와 제공자의 삭제 절차·증거로 따로 닫아야 합니다.

상태 조회도 같은 ACL snapshot을 사용합니다. ACL snapshot을 안전하게 복원할 수 없거나 managed `groups`가 이미 비어 있는 legacy 메타데이터는 보이지 않고 mutation도 404입니다. 운영자는 숨겨진 행을 없다고 간주하거나 그룹을 임의 부여하지 말고, 원천 소유자와 실제 회사 보존·삭제 결정을 확인한 통제된 관리자 migration·대조 절차로 처리합니다.

신규 ID namespace 규칙은 기존 unqualified managed ID를 자동 rename하지 않습니다. 해당 ID의 upsert는 422이며, 현재 binding과 저장 ACL을 만족하는 retire/tombstone 정리는 가능합니다. 계속 사용할 ID와 accepted source-version history를 새 ID로 옮기려면 원본 DB 백업, 소유자 승인, 충돌 검사, 감사 대조와 rollback을 포함한 통제된 migration을 수행합니다. bootstrap·읽기 ID와 v0.1 역사 파일은 그대로 둡니다. 다중 tenant 기동 전에는 legacy·bootstrap 문서의 실제 owner, 저장 tenant와 prefix를 재고 대조해 acme 소유 `beta.doc` 같은 충돌을 해소합니다. 신규 upsert guard가 trusted bootstrap/admin 파일이나 entity/action/object·일반 ontology ID 전체를 정규화했다고 간주하지 않습니다.

registry에서 계약을 제거하기 전에 그 계약의 문서를 대조하고 보존 결정에 따라 retire/tombstone합니다. 계약을 먼저 제거하면 API가 contract ID를 해석할 수 없어 정리할 수 없습니다. 이미 제거했다면 같은 tenant/source/contract ID를 승인된 설정으로 재등록하고 저장 ACL을 확인한 뒤 drift tombstone을 사용합니다. `delete_within_hours`는 원천·WAL·백업·provider 삭제의 실행기가 아니므로 실제 삭제 책임자와 완료 증거를 별도로 관리합니다.

`knowledge import`는 변경 문서만 담은 정규화 source **delta snapshot**을 배치 upsert로 바꾸는 어댑터입니다. 같은 문서 ID를 한 파일에 중복하면 요청 단계에서 거부됩니다. API는 HTTP 422와 `invalid_request`, CLI는 종료 코드 1과 `invalid_input_file`을 반환하며 revision을 올리지 않습니다. 현재 주체의 `manage_knowledge`+`audit` 권한과 tenant의 서버 등록 계약을 먼저 확인합니다. 전체 envelope digest에는 `observed_at`도 포함됩니다. 신규 snapshot의 `observed_at`이 현재보다 미래면 `snapshot_observed_in_future`, 계약의 `refresh_interval_hours`보다 오래됐으면 `snapshot_stale`, 같은 tenant/source의 마지막 수락 시각보다 크지 않으면 `snapshot_watermark_conflict`로 거부합니다. 현재 권한·계약과 exact credential 재인증을 통과한 동일 request key/envelope replay만 watermark 검사 전에 저장 영수증을 읽습니다. 신규 성공과 replay의 응답 `documents`는 현재 저장 record의 exact binding과 actor의 문서 ACL `READ/AUDIT` 가시성으로 필터됩니다. 원본 저장 receipt/audit와 상위 필드는 불변이지만 ACL·binding에 따라 응답 배열은 비거나 줄 수 있습니다.

변경된 각 문서는 그 문서에서 과거에 수락하지 않은 새 `source_version`을 사용합니다. 이전 파일의 모든 문서를 반복해 보내는 전체 복제 프로토콜이 아니며, delta에서 빠진 문서는 변경되지 않은 것으로 둡니다. 삭제·정정은 별도의 명시적 retire/tombstone/apply 변경으로 제출합니다. `observed_at`은 게시자가 제공한 claim입니다. 런타임이 원천 수집 시각을 인증하거나 자동 connector로 갱신했다는 뜻이 아닙니다. 파일 포맷 파싱, 원천 로그인, 바이러스 검사, 전자서명 검증, SharePoint·ERP·FHIR·OPC UA 연결도 수행하지 않습니다. `origin_authenticated=false`, `provenance_authenticated=false`인 영수증을 원천 인증 증거로 해석하지 않습니다.

## 5. 검색, 모델 반출, 승인과 실행

현재 pack은 bootstrap 문서와 SQLite의 active 문서를 합성합니다. bootstrap 문서의 pack hash는 유지되고, 운영 문서 변경은 tenant/source revision과 state hash로 추적됩니다. managed 문서는 저장된 tenant, contract ID/version/hash와 source가 현재 registry에 모두 일치할 때만 포함됩니다. 계약이 바뀌거나 없어지거나 binding이 비어 있으면 검색·제안·승인·실행 근거에서 제외합니다.

- 검색은 현재 문서의 tenant, ACL, 목적, 민감도, 유효기간, lifecycle을 확인합니다.
- provider의 미확인 텍스트 기본 등급 하한은 `RESTRICTED`입니다. 하한을 내리려면 검증된 channel과 회사 분류·반출 정책을 릴리즈 기록에 남깁니다.
- 모델 호출 직전과 직후에 같은 credential을 다시 인증하고 동일 질의를 현재 지식 스냅샷에서 다시 계산합니다.
- credential이나 인용 근거가 바뀌면 응답을 내보내지 않고 `identity_changed` 또는 `knowledge_snapshot_changed`로 끝냅니다.
- 제안의 simulate/approve/execute는 근거 문서의 현재 source version, content hash, ACL hash, lifecycle을 다시 확인합니다.
- 모든 action write와 knowledge state/apply/import는 트랜잭션을 연 직후 read/replay 전에 요청에 사용한 exact credential을 다시 인증합니다. raw credential은 응답·로그·DB에 저장하지 않습니다.
- 모델은 승인·실행 주체가 아닙니다. 승인자는 human Principal이어야 하며 제안자와 subject가 다르더라도 같은 `person_id`면 자기 승인으로 거부합니다. 제안·승인 당시 actor kind/person binding을 기록하고 새 제안의 동일 request-key replay와 미완료 제안의 approve·execute에서 현재 매핑을 다시 비교해 계정 뒤 사람의 재할당도 차단합니다. 실행은 결정적 `ActionEngine` 경로를 통과합니다.

재시도는 변경이 없음을 확인한 뒤 새 검색이나 새 제안으로 수행합니다. 이미 생성된 모델 응답이나 예전 승인 hash를 그대로 재사용하지 않습니다.

## 6. RS256 액세스 토큰 운영

`IdentityRegistry.authentication_mode`의 기본값은 `opaque_only`입니다. OIDC만 사용하려면 `jwt_only`, 두 방식을 함께 사용하려면 `both`를 명시하고 실제 binding 구성도 그 모드와 일치시켜야 합니다. OIDC 경로는 운영자가 pinned public JWKS를 등록했을 때만 켜집니다. 런타임은 RS256 서명과 `kid`, `typ=at+jwt`(대소문자·media type 변형 허용), `iss`, 단일 정확한 `aud`, `sub`, `client_id`, `exp`, `iat`, `nbf`를 검증하고, `(issuer, subject)`를 서버에 미리 등록한 `Principal`로만 매핑합니다. user subject는 human Principal이며 `sub != client_id`, service subject는 service Principal이며 `sub == client_id`여야 합니다.

키 교체는 새 키를 기존 키와 겹쳐 배포하고 새 토큰 검증을 확인한 뒤 이전 키를 제거합니다. 런타임은 요청마다 신원 파일을 다시 읽으므로 파일 교체는 원자적으로 수행하고 이전 파일을 보호합니다. `jku`, `x5u`, 인라인 `jwk`, `crit` 헤더는 키 출처를 바꾸지 못하게 거부됩니다.

이 기능은 액세스 토큰 검증입니다. 브라우저 로그인, Authorization Code/PKCE, 로그아웃, 세션, refresh token, IdP discovery·동적 JWKS 다운로드, 토큰 introspection을 제공하지 않습니다. 토큰의 남은 수명 동안 강제 회수가 필요한 환경은 짧은 수명, 신원 매핑 비활성화, 별도 게이트웨이·introspection을 설계해야 합니다.

## 7. 릴리즈 판정과 기록

릴리즈 입력은 baseline/candidate, fixture digest, 증거 digest, 품질·불필요 거부·지연·비용, 안전 실패·권한 위반·삭제 누락을 포함합니다. 평가 대상 manifest는 pack, data contract, model, prompt, policy, case set, rubric, code의 version과 SHA-256을 하나의 canonical hash로 묶습니다. manifest가 없거나 evidence·case가 같은 manifest hash를 참조하지 않으면 점수와 무관하게 `blocked`입니다. 안전 실패, 권한 위반, 삭제 누락도 평균 점수가 좋아도 veto입니다. 합성 평가만으로는 현업 검토 자격이 생기지 않습니다.

다음 기록을 모델·온톨로지·도구 각각에 남깁니다.

| 필드 | 예시 의미 |
|---|---|
| 대상 ID/버전/hash | 모델 배포, 팩, 프롬프트, 도구 allowlist, 계약 레지스트리의 정확한 식별자 |
| 변경 이유·소유자 | 어떤 오류·정책·요구를 해결하는지와 책임자 |
| 평가 증거 | 동결 fixture digest, 기준, 결과, 위험 veto, 현업 검토자 |
| 배포 범위 | tenant, 사용자군, 자료 등급, 허용 작업, 기간 |
| 비용 | 추론·GPU뿐 아니라 데이터 정비, 검수, 재작업, 운영, 장애 복구 |
| rollback | 복귀 버전, 데이터 호환성, 실행 중 작업 처리, 책임자 |

`eligible_for_field_review=true`는 입력 기반으로 현업 검토 단계에 진입할 수 있다는 추천입니다. target manifest hash는 평가 대상 식별 일관성만 확인합니다. `live_validated=false`, `evidence_origin_verified=false`이므로 외부 증거의 진실성, 출시 승인, production readiness나 실제 성과 증명이 아닙니다.

## 8. 백업, 재시작, 복구

v1 DB를 v0.2 런타임에서 처음 열면 현재 knowledge schema 4 테이블을 생성하고 bootstrap 문서를 seed합니다. schema 2 개발 DB는 contract binding 컬럼, request namespace, source watermark와 accepted source-version history를 먼저 추가하고, schema 2·3 DB에는 내부 ACL snapshot인 `access_json`을 추가합니다. 본문이 남아 있고 그 안의 ACL hash가 저장 hash와 맞는 행만 backfill합니다. 본문이 없는 legacy tombstone 등 ACL을 복원할 수 없는 메타데이터는 상태 조회에서 숨깁니다. 현재 행과 기존 영수증으로 version history를 재구성하고 기존 batch는 `apply` namespace로 옮깁니다. 과거 `observed_at`은 schema 2에 없으므로 마지막 knowledge batch 감사 시각을 source별 보수적 watermark 상한으로 쓰고, 감사 매핑이 없는 managed source는 migration 시각을 씁니다. 이후 `observed_at`은 이 상한보다 엄격히 커야 하며 상한 자체는 원천 수집 시각 인증이 아닙니다. binding이 없는 기존 managed 행은 숨겨지고, 같은 문서 ID를 일반 upsert로 재등록할 수 없습니다. 신규 tenant namespace를 만족하지 않는 기존 managed ID도 자동 rename되지 않고 upsert는 422입니다. ID·accepted history를 새 namespace로 옮기는 관리자 migration이나 새 문서 ID 같은 명시적 복구를 계획합니다.

기존 proposal/entity/audit 및 pack hash는 보존 대상입니다. 운영 전 원본 DB의 일관된 백업을 만들고 복사본에서 schema 4 기동, current pack 제외·포함, 호출자별 상태 가시성, 감사와 복구를 검증합니다. 마이그레이션이 실패하면 원본 DB를 수동 편집하거나 재실행으로 덮지 말고 프로세스를 중지한 뒤 일관된 백업에서 복구해 원인을 조사합니다.

과거 미완료 제안에 proposer/approver actor kind·person binding이 없으면 새 제안 또는 새 승인이 필요합니다. 이 필드를 수동으로 채우지 않습니다. 이미 실행되거나 rollback된 terminal 제안은 멱등 execute replay와 rollback 호환 경로를 유지하지만, 요청 주체의 현재 credential과 권한은 계속 확인합니다.

권장 재시작 절차:

1. 새 변경 요청 유입을 멈추고 실행 중 제안을 확인합니다.
2. 프로세스를 정상 종료한 뒤 DB와 설정 파일의 해시, 권한, 백업 위치를 기록합니다.
3. 새 런타임으로 복사본을 열어 pack hash, audit chain, knowledge state를 확인합니다.
4. 계약·신원·모델 설정을 확정하고 제한된 트래픽으로 시작합니다.
5. rollback 조건을 넘으면 프로세스를 중지하고 기록한 버전으로 복귀합니다. DB 파일을 수동 편집하지 않습니다.

SQLite WAL을 사용하는 동안 파일 하나만 복사해 백업 완료로 간주하지 않습니다. 일관된 SQLite 백업 방식 또는 정지 상태 복사를 사용하고 실제 복구 시험을 정기적으로 수행합니다.

v0.3에서 v0.2로 되돌릴 때는 v0.3 registry의 `evidence_roles`를 v0.2가 extra field로 거부한다는 점을 먼저 확인합니다. v0.2 호환을 위해 이 필드만 지우면 `derived_output`과 marker 의존 문서가 raw 근거로 다시 들어올 수 있습니다. v0.2 시점의 원천 snapshot·registry·DB를 함께 복원하거나, v0.3 DB와 분리한 새 v0.2 DB를 구성해 raw 원천만 승인 재수집합니다. 자세한 절차는 [업그레이드 가이드](UPGRADE_GUIDE.md)를 따릅니다.

## 9. 장애 대응

| 오류 | 의미 | 처리 |
|---|---|---|
| `tenant_revision_conflict` / `source_revision_conflict` | 읽은 뒤 다른 변경이 반영됨 | 최신 상태를 읽고 사람 검토부터 다시 시작 |
| `idempotency_conflict` | 같은 request key에 다른 payload | 기존 영수증 확인; 새 의도면 새 키 사용 |
| `source_version_reuse` | 같은 문서에서 과거에 수락한 source version 재사용 | 새 source version으로 원천 변경을 명시하고 다시 검토 |
| 404 `document_not_found` | 문서 부재, 타 계약 문서, 기존 binding 불일치, 저장 ACL tenant/group/clearance 불충족 또는 ACL snapshot 불명 | ID·ACL·계약 소유권을 추정해 우회하지 말고 원천 소유자와 현재 계약을 대조; version/hash drift 정리는 같은 tenant/source/contract ID의 tombstone만 허용 |
| `data_contract_violation` | 원천·범위·ACL·등급·hash·provenance가 계약과 불일치하거나 managed upsert ID가 tenant namespace 밖이거나 upsert/ACL 변경의 groups가 비어 있음 | 입력과 서버 계약을 대조; 신규 ID는 `<tenant>.<점 없는 접미부>`로 발급하고 완전 회수는 빈 active ACL 대신 승인된 retire/tombstone 사용 |
| `document_domain_invalid` | 문서 생성 또는 변경 후 최종 DomainPack 불변식 위반 | 해당 문서와 팩 규칙 대조; 같은 배치의 앞선 변경·감사·revision도 rollback됐는지 확인 |
| `document_tombstoned` / `tombstone_recreation_forbidden` | 논리 삭제된 문서를 사용 또는 재생성 시도 | 새 ID와 승인된 복원/재수집 절차 검토 |
| `snapshot_observed_in_future` / `snapshot_stale` / `snapshot_watermark_conflict` | 신규 snapshot 시각이 미래·기한 초과이거나 이전 수락 시각보다 증가하지 않음 | 게시·수집 경로의 시계와 실제 새 snapshot 확인; 시각만 고쳐 우회하지 않음 |
| HTTP 422 `invalid_request` / CLI `invalid_input_file` | snapshot 안에 같은 문서 ID가 중복되었거나 입력 계약이 잘못됨 | 중복을 병합하지 말고 원천 변경 집합과 문서별 새 source version을 다시 생성 |
| `evidence_changed_or_revoked` | 제안 이후 source/version/hash/ACL/lifecycle 변경 | 새 근거로 새 제안·시뮬레이션·승인 |
| `knowledge_snapshot_changed` | 모델 호출 전후 검색 근거 변경 | 생성 결과 폐기 후 현재 스냅샷에서 다시 질의 |
| `identity_changed` | 요청 도중 credential 매핑·유효성이 변경 | 재인증 후 새 요청 |
| `principal_identity_changed` | 제안·승인 당시 actor kind/person binding과 현재 매핑 불일치 | 기존 승인 재사용 금지; 현재 사람으로 새 제안·승인 |
| `wiki_page_not_found` | page가 없거나 caller가 기존 published/stale/scrubbed head의 존재·revision을 알 권한이 없음 | revision을 추측하지 말고 승인된 HUMAN knowledge manager로 현재 head 자격과 원천·scope 객체를 대조 |
| `wiki_proposer_identity_required` | Wiki 작성자가 effective person에 결속되지 않음 | SERVICE나 person 없는 신원을 우회하지 말고 registry에 등록된 책임 있는 HUMAN 작성자로 새 compile |
| `wiki_proposer_identity_changed` | compile replay나 publish에서 작성자의 actor/person binding이 달라짐 | 과거 draft를 반환·게시하지 말고 현재 신원으로 새 request key를 사용 |
| `wiki_recompile_required` | server floor 또는 현재 raw 적격성이 저장 draft/page보다 엄격해짐 | 기존 head를 볼 자격이 있는 manager가 마지막 revision으로 새 compile·독립 검토 |
| `proposal_reproposal_required` / `proposal_reapproval_required` | 과거 미완료 제안에 신원 binding 없음 | 필드 수동 보정 금지; 새 제안 또는 새 승인 |
| `knowledge_schema_migration_required` | 알 수 없는 schema version | 자동 덮어쓰기 금지; 백업 후 명시적 마이그레이션 설계 |
| `state_busy` | SQLite 잠금 대기 초과 | 상태를 확인하고 같은 request key로 제한 재시도 |

단일 SQLite는 참조 구현의 경계입니다. 예상 동시성, 장애 복구 목표, 테넌트 격리, 감사 보존, 물리 삭제, 부하를 실제 조건에서 검증하고 필요하면 외부 DB와 불변 감사 저장소로 이전합니다.

## 감사 상태

`docs/evidence/v0.1.0/`의 Opus·Codex 감사는 v0.1 증거입니다. v0.2의 온보딩, JWT, 지식 변경, 릴리즈 게이트를 승인한 증거로 재사용할 수 없습니다. v0.2 감사와 현장 검증은 별도 버전·별도 증거 digest로 기록합니다.

## Wiki 운영

v0.2 DB에 v0.3을 처음 연결하면 기존 knowledge schema 4를 유지하며 Wiki schema 1을 추가합니다. Wiki 작성/검토/검색·원문 변경 전파·권한 회수·삭제·export·업그레이드 절차는 [v0.3 실행 가이드](V03_GUIDE.md)에 있습니다.

source watcher, 검토 알림, 의미 충돌 lint, 자동 재compile queue, 백업/인덱스/다운로드 삭제는 별도로 구성해야 합니다. `wiki lint`를 지속 감시 서비스로 해석하지 않습니다. 최소 운영 주기는 다음과 같습니다.

1. 원천 owner가 update·ACL·retire·tombstone·contract role 변경 사건을 Wiki 담당자에게 전달합니다.
2. 담당자는 `wiki lint`, 숨김 page 대조와 source dependency 재고로 영향 page를 찾습니다. lint가 숨은 page나 role 재분류를 모두 알려준다고 가정하지 않습니다.
3. 현재 head를 볼 수 있는 HUMAN knowledge manager가 마지막 revision으로 새 request key compile을 수행합니다.
4. 다른 HUMAN reviewer가 title·question·links, 모든 raw 입력, scope 객체, `generation_route`와 canonical review hash를 확인한 뒤 게시합니다.
5. 재게시 뒤 이전 독자와 축소된 독자 각각의 page·index·query·link·export를 확인합니다.

관계 ACL·민감도 변경도 원천 변경과 함께 영향 대조에 포함합니다. 저장 query를 현재 actor로 다시 탐색하므로 유일한 관계의 권한을 회수하면 객체·원문 ACL이 같아도 packet·page·index·lint·export는 숨겨질 수 있습니다. 관계 분류만 높아지면 낮은 분류의 조회·export가 차단되고 권한 있는 manager에게 `object_changed` lint가 제공됩니다. 새 분류로 compile하고 독립 게시한 뒤 위 표면을 다시 확인합니다. 같은 객체 전체를 연결하는 현재 허용된 대체 경로가 있으면 접근은 유지되므로, 과거 관계의 ID·type 변경 대조는 별도의 변경 장부로 수행합니다.

원천별 권한을 AND로 적용하므로 원천이 늘수록 독자층이 좁아집니다. 기본 floor는 RESTRICTED입니다. 개별 HR case처럼 ACL이 세밀하고 빈번히 바뀌는 영역은 stale와 재검토 비용이 커서 pilot 대상에서 제외하거나 page를 더 작은 권한 단위로 분리합니다.

참조 구현은 read에도 SQLite `BEGIN IMMEDIATE`를 사용하고, page별 current pack 재구성과 backlink 계산은 O(P²)입니다. page 하나의 무결성 실패는 해당 tenant Wiki 읽기 전체를 fail-closed로 닫을 수 있습니다. 동시성, page 수, lock timeout, tenant 장애 격리와 읽기 지연을 실제 목표 부하에서 측정하기 전에는 수평 확장이나 고가용성을 주장하지 않습니다.

API의 title·body·question·link ID는 plain data입니다. 이를 Markdown/HTML로 렌더링하는 클라이언트는 escape, URL scheme allowlist와 CSP를 적용합니다. `proposer_person_id`·`reviewer_person_id`는 개인정보 재고에 포함하고 독자별 노출, 로그·export, 보존·정정·삭제를 검토합니다. tombstone/scrub 뒤 남는 page ID, request key, version ID, source dependency, audit actor·event·시각·hash를 삭제 장부에 열거하고, legal hold가 있으면 hold 대상·승인자·종료 조건과 일반 삭제 SLA의 예외를 기록합니다.

새 검토가 게시돼 revision이 진행된 뒤 오래된 publish 요청을 재시도하면 `wiki_publish_replay_superseded`로 상태 확인을 요구합니다. 즉시 동일 검토자/동일 payload의 재시도만 멱등 반환합니다. Wiki의 draft·게시·원문 invalidation은 기존 감사 hash chain에 결속하지만 외부 서명을 제공하지 않습니다. v0.3 검증도 이전 감사와 구분하며 회사 배포 승인으로 승격하지 않습니다.
