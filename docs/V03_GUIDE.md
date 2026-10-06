# v0.3: 원문 RAG와 LLM Wiki를 함께 운영하기

Wiki를 포함하는 편이 적절합니다. 자주 쓰는 업무 용어, 절차, 예외와 원문 간 관계를 지속적으로 정리할 수 있기 때문입니다. 원문 검색과 Wiki의 생성 지식을 별도 계층으로 유지하고, 기업별 gold set으로 효과를 확인합니다. 현재 compile은 요청당 page 하나, page당 raw 원천 최대 10개이며 Wiki→Wiki synthesis와 source watcher가 없습니다. 원안과 보안 자료의 판단 근거는 [LLM Wiki 가이드](LLM_WIKI_GUIDE.md)에 있습니다.

## 먼저 직접 실행하기

```powershell
uv sync --frozen
uv run ax wiki demo --domain procurement
uv run ax wiki demo --domain support
uv run ax wiki demo --domain hr
```

모델·외부 서비스 없이 합성 원문으로 실행됩니다. `self_review_blocked`, `persisted_after_restart`, `expired_source_hidden`, `export_non_authoritative`가 true인지 확인합니다. 자동으로 게시하는 이 데모의 역할은 테스트용 합성 사람입니다. 실제 회사의 사람이 검토했다는 증거로 사용하지 않습니다.

## 회사 파일과 서버를 연결하기

먼저 [회사 적용 가이드](V02_GUIDE.md)의 domain pack·신원·원문 계약·API 설정을 완료합니다. Wiki 작성자는 server registry의 HUMAN이며 non-null `effective_person_id`와 `READ+MANAGE_KNOWLEDGE`가 필요합니다. 현재 SERVICE compile은 403이고 서비스 위임 작성은 지원하지 않습니다. 검토자는 다른 실제 HUMAN으로 `READ+APPROVE`를 가져야 합니다. 두 사람 모두 테넌트·목적·등급·모든 원천과 anchor·hop scope 객체의 현재 접근권한을 충족해야 합니다.

서버의 기본 `minimum_query_sensitivity`는 RESTRICTED(3)입니다. 작성자·검토자의 clearance와 모델 경로를 이 분류에 맞춥니다. 구매·지원의 기본 합성 init 계정은 INTERNAL(1)이므로 기본 설정에서 높은 분류의 Wiki 초안을 만들 수 없습니다. 아래 설정은 원문과 질문이 INTERNAL임을 확인한 **로컬 합성 데모**에서만 쓰는 예입니다. 실제 회사 정책을 낮추는 지침으로 사용하지 않습니다.

```json
{"mode":"offline","minimum_query_sensitivity":1}
```

회사별 provider 파일에 명시하고 `AX_PROVIDER_FILE`로 선택합니다. local은 loopback endpoint, private/cloud는 승인한 정확한 HTTPS 호스트·반출 승인·분류 ceiling·최소 패턴 필터·별도 모델 credential을 요구합니다. loopback은 첫 hop일 뿐 오프라인 추론의 증명이 아닙니다. Ollama를 쓰면 `disable_ollama_cloud: true` 또는 `OLLAMA_NO_CLOUD=1`을 적용하고 재시작 뒤 `Ollama cloud disabled: true` 로그를 확인합니다. 회사는 backend가 원격으로 forward하거나 cloud model·proxy·tunnel을 쓰지 않는지 확인하고, 무반출이 필요하면 OS/container outbound deny와 DNS·proxy·tunnel 차단을 적용합니다. 설정과 로그 하나를 회사 보안 인증으로 확대하지 않습니다. 지역·보존·망·게이트웨이 실제 통제는 기존 [보안 모델](SECURITY_MODEL.md)과 도입 진단을 따릅니다.

`wiki-request.json`은 다음 형태입니다. page ID는 `tenant.local-id`이고 nested suffix는 거부합니다. 소스 ID는 원문 계약의 namespace를 따릅니다.

```json
{
  "request_key":"wiki-review-1",
  "page_id":"acme.review-policy",
  "title":"검토 절차",
  "kind":"procedure",
  "query":{"question":"검토 절차","purpose":"operations","object_id":"request-1","hops":1,"sensitivity":1,"generate":false},
  "expected_page_revision":0,
  "links":[]
}
```

```powershell
uv run ax wiki compile wiki-request.json
uv run ax wiki draft DRAFT_ID
# 실제 별도 검토자 credential을 AX_TOKEN에 지정한 뒤 실행합니다.
uv run ax wiki publish DRAFT_ID --reviewed-hash REVIEWED_PAYLOAD_HASH
uv run ax wiki index
uv run ax wiki query "검토 절차" --object-id request-1 --sensitivity 1
uv run ax wiki page acme.review-policy
uv run ax wiki lint
uv run ax wiki export acme.review-policy
```

CLI는 기존 `AX_API_BASE`, `AX_TOKEN`, `AX_INPUT_ROOT`를 사용합니다. 기본 purpose는 operations이고 `wiki query`의 기본 sensitivity는 CONFIDENTIAL(2)이므로 위 INTERNAL 예시는 `--sensitivity 1`을 명시해야 합니다. export는 Markdown과 manifest를 담은 JSON 응답이며 서버가 임의 파일에 쓰지 않습니다. 같은 request_key의 정확한 재시도는 모델을 다시 호출하지 않고 저장된 초안을 반환하지만, 현재 작성자 신원·clearance·floor·원천·scope 객체가 유효해야 합니다. 수정 게시에는 새로운 request_key와 head의 마지막 revision 번호가 필요합니다. 기존 head를 볼 수 없는 caller는 존재·상태·revision과 무관하게 같은 404를 받습니다.

## 검토 묶음을 확인하기

- `input_citations`: 컴파일러에 전달한 모든 원문. 검토자는 누락된 입력까지 읽습니다.
- `source_bindings`: 그 원문의 버전·본문/ACL/전체 문서 hash·문서 객체·원천 계약에 대한 결속. 모든 원문에 과거와 현재의 권한을 적용합니다.
- `scope_object_bindings`: query anchor와 hop traversal 및 원천에 연결되어 classification에 기여한 객체 집합, 최대 100개. 작성자·검토자·독자는 각 객체의 현재 접근권한을 가지며 저장 query를 현재 권한으로 탐색해 전체 결속 객체에 도달할 수 있어야 합니다.
- `citations`: 모델 또는 추출기가 결과에 선택한 직접 인용. 연속 문자열 존재 검사는 의미적 타당성을 증명하지 않습니다.

관계의 ACL만 회수해도 필요한 scope가 사라지면 초안·게시·페이지·index·lint·export가 숨겨집니다. 현재 관계의 민감도가 저장 분류보다 높아지면 조회·export를 차단하고 권한 있는 manager에게 `object_changed` lint를 제공해 재컴파일·독립 검토를 요구합니다. 현재 허용된 대체 경로로 전체 scope가 재현되면 접근은 유지됩니다. 이 검사는 현재 관계 권한·분류를 확인하며, 과거 링크 ID·type·경로 snapshot의 동일성을 보증하지 않습니다.

검토 hash는 schema 순서의 payload JSON, 줄바꿈, compiler mode를 SHA-256한 값입니다. payload는 page ID·kind·query·title·본문·links·페이지 revision·원문 입력·source/scope binding·분류·server floor·작성자와 `generation_route`를 포함합니다. `generation_route`는 `mode`, `endpoint_host`, `model`, 비밀값 없는 `provider_settings_sha256`이며 page와 export manifest에도 남습니다. 이는 설정 provenance이고 backend의 실제 모델·실행 위치·원격 forwarding이나 사람의 검토 수행을 증명하지 않습니다. 실제 검토자는 작성자 metadata인 title·question·links까지 원문 의미, 예외, 상충, 삭제 대상과 함께 확인합니다. `generate=false`는 offline_extractive, true는 모델 초안이며 실패 시 조용히 원문 추출로 대체하지 않습니다. Wiki query는 모델을 호출하지 않고 현재의 검토 페이지와 원문을 검색합니다. `generate=true`를 보내면 422입니다.

## 원문이 바뀌었을 때

원문 갱신·ACL 변경·retire는 해당 원문을 사용하는 현재 페이지와 초안을 stale로 처리합니다. 이전 revision만 의존하면 현재의 무관한 clean revision은 유지합니다. tombstone은 해당 원문에 의존한 **모든 버전과 초안**의 본문·제목·질문·인용을 live SQLite 레코드에서 제거합니다. 현재 revision이 삭제 대상이면 페이지를 숨기고 해당 identity의 재게시를 차단합니다. source 변경과 Wiki 전파는 같은 transaction이며 실패하면 함께 rollback합니다.

현재 권한·계약·원천 role·분류 floor가 달라진 경우 조회 시에도 검사합니다. role을 `derived_output`으로 바꾸면 다음 `current_pack`에서 raw 원천이 제외되고 영향 page도 숨겨지므로 승인된 raw 원천으로 재컴파일·재검토해야 합니다. 더 낮은 분류로 작성된 페이지를 current server floor가 넘을 때도 같습니다. `wiki lint`는 과거 snapshot과 현재 접근을 모두 가진 knowledge manager에게만 `source_changed` 또는 `recompile_required`와 `revision`, `state`, `reason`을 반환합니다. reason은 `source_changed`, `object_changed`, `head_stale`, `classification_floor`입니다. 이 값을 복구 compile에 쓰되 권한 밖·scrubbed page는 제목·개수까지 숨깁니다. 미사용 ID의 생성과 비가시 ID의 404 차이로 같은 tenant 안의 ID 사용 여부 추론은 남으므로 서버가 민감한 의미 없는 ID를 할당해야 합니다. 현재 구현은 의미 충돌, 자동 수정, 지속 감시나 재컴파일 예약을 수행하지 않습니다.

Wiki는 원문 `DomainPack.documents`에 들어가지 않고 직접 action evidence가 되지 않습니다. 알려진 Wiki export marker와 서버 `DataContractRegistry.evidence_roles`의 derived_output 계약은 원문 검색에서 제외합니다. raw 필터는 BOM·앞 공백과 CLI 원형 export JSON의 `text`를 다루지만, 임의 frontmatter를 붙이거나 marker를 제거하고 거짓 raw로 등록하거나 출처를 위조한 경우의 실제 기원을 hash만으로 인증하지는 못합니다. role이 없는 legacy 계약, contract가 없는 bootstrap 문서와 registry 없는 실행은 v0.2 호환상 raw로 허용되므로 기업 적용에서는 모든 관리 원천 계약과 role을 완전 등록합니다.

head 복구 자격은 과거 binding의 ACL과 남아 있는 원천 record의 현재 ACL을 함께 검사합니다. retire·만료·derived role 때문에 raw 검색에서 빠진 원천도 record와 문서가 남고 필요한 권한이 있으면 manager가 마지막 revision을 확인할 수 있습니다. 새 draft와 게시에서는 별도로 현재 active·계약 적합·raw 원천만 허용하므로, 복구를 위해 제거된 원천을 다시 근거로 쓰지는 않습니다. tombstone으로 문서가 scrubbed됐거나 record가 없으면 기존 identity는 404이며 복구할 수 없습니다.

## 분야를 강화하는 방법

L0는 source·owner·목적·접근·용어를 정합니다. L1은 반복 규정과 예외를 reviewed Wiki로 만들고 원문에 연결합니다. L2는 회사 gold set으로 RAG-only와 hybrid의 정답·유보·권한·삭제·지연·비용을 같은 조건에서 비교합니다. hidden case는 Wiki 작성자·검토자에게 공개하지 않고 page 집합을 먼저 freeze하며, 현업 두 사람이 독립 채점하고 불일치를 조정합니다. 현재 substring 검사는 semantic entailment를 인증하지 않습니다. L3는 source watcher, 검토 대기열, 서명/백업·검색 인덱스 삭제, 의미 충돌 검토를 구현하고 실패를 재현합니다. L4는 현업 기준을 통과한 좁은 작업만 승인·시뮬레이션·복구 가능한 외부 connector에 연결합니다. 단계별 서식과 실습은 [Wiki 강화 가이드](LLM_WIKI_GUIDE.md)와 [업그레이드 가이드](UPGRADE_GUIDE.md)를 따릅니다.

다운로드된 export 회수, 디스크/WAL·백업의 물리 삭제, 외부 감사 서명, 기업 connector·실제 IdP·실제 모델 품질은 이 참조 구현으로 검증되지 않습니다. 회사의 평가·감사를 통과해야 운영 적용을 판단할 수 있습니다.
