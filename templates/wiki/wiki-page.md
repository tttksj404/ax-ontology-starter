# Wiki draft·page 검토서

이 서식은 `WikiDraft.payload`와 게시될 `WikiPage`를 원문과 함께 검토하기 위한 운영 기록입니다. 서버의 `payload_hash`를 직접 다시 쓰지 않고 draft 응답의 값을 사용합니다. 독립 reviewer가 원문 의미를 확인한 뒤 같은 hash로 publish합니다.

## 1. compile 요청

| 필드 | 값 |
|---|---|
| request key |  |
| page ID (`<tenant>.<점 없는 suffix>`) |  |
| title / kind |  |
| query question / purpose / object ID |  |
| query top_k / hops / sensitivity / generate |  |
| expected page revision |  |
| links |  |

- 작성자 subject / non-null `effective_person_id`:
- 작성자 권한: server registry의 HUMAN, `READ+MANAGE_KNOWLEDGE` (SERVICE 작성은 현재 지원하지 않음)
- compile mode: `offline_extractive` / `model_draft`
- `generation_route.mode` / `endpoint_host` / `model` / `provider_settings_sha256` (`generate=true`만):
- provider 설정 hash에 credential·API key·token 원문이 없음을 확인:
- LOCAL이면 backend 원격 forwarding·cloud model·proxy/tunnel 차단과 outbound deny 증거:

## 2. 저장 draft

| 항목 | draft 응답 값 | 확인 |
|---|---|---|
| draft ID / state |  | `draft`인가 |
| request SHA-256 |  | 같은 request replay인가 |
| payload hash |  | publish에 사용할 정확한 값인가 |
| page classification / server query floor |  | reviewer clearance가 충분한가 |
| proposer actor kind / `person_id` |  | 게시 전까지 동일한가 |
| input citation / source binding / output citation 수 |  | 전체 입력·결속·출력 부분집합이 각각 1~10개인가 |
| `scope_object_bindings` |  | anchor·hop과 원천에 연결되어 classification에 기여한 객체가 모두 포함됐는가(최대 100개) |
| `generation_route` |  | payload·page·export에 같은 `mode`/`endpoint_host`/`model`/`provider_settings_sha256`이 전파되는가 |

세 집합을 섞지 않습니다. `input_citations`는 컴파일러가 받은 전체 raw citation, `source_bindings`는 그 모든 입력 원천의 hash·ACL 결속, `citations`는 body가 실제 채택한 출력 인용 부분집합입니다.

## 3. 원천 binding

| document ID | source ID / version | document / content / ACL SHA-256 | contract ID / version / SHA-256 | tenant·groups·sensitivity·purposes | valid until | reviewer 접근 |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  | 허용 / 거부 |

모든 원천에 대해 작성자와 reviewer가 현재 ACL을 각각 통과해야 합니다. group 이름을 합집합 ACL로 만들지 않습니다. page classification은 server/query/source/entity/compiler의 최고 민감도 이상이어야 합니다.

| scope object ID | anchor / hop | tenant·groups·sensitivity·purpose | 작성자 현재 접근 | reviewer 현재 접근 |
|---|---|---|---|---|
|  |  |  | 허용 / 거부 | 허용 / 거부 |

문서 자체의 `object_ids`뿐 아니라 query anchor와 hop traversal에서 분류에 기여한 객체를 모두 검사합니다. 하나라도 현재 보이지 않으면 검토·게시·독자 공개를 진행하지 않습니다.

## 4. 전체 입력과 출력 인용 대조

| input document ID / content hash | `source_bindings`에 존재 | 출력 `citations`에 채택 | 누락·상충·선택 편향 검토 |
|---|---|---|---|
|  | 예 / 아니요 | 예 / 아니요 |  |

출력에 채택되지 않은 input citation도 reviewer가 읽습니다. `GET /v1/wiki/drafts/{id}`는 현재 원천을 모두 볼 수 있는 독립 HUMAN reviewer에게 전체 packet을 반환합니다. reviewer는 `READ+APPROVE`가 필요하며 `READ`만으로는 조회할 수 없습니다.

## 5. 의미검토

| 질문 | reviewer 판정 | 원문 근거·수정 |
|---|---|---|
| body의 각 핵심 문장이 citation 원문에 의해 지지되는가 | 통과 / 수정 / 반려 |  |
| 사실·추론·미확인을 구분했는가 |  |  |
| 효력일·관할·업무 범위와 예외를 보존했는가 |  |  |
| 상충하는 원천을 숨기지 않았는가 |  |  |
| page link를 근거로 오인하지 않았는가 |  |  |
| 작성자 metadata인 title·query question·object ID·links가 민감정보를 드러내거나 원문보다 강한 주장을 하지 않는가 |  |  |
| Wiki page나 export를 raw source처럼 자기인용하지 않았는가 |  |  |
| action 권한이나 실행을 body가 부여한다고 쓰지 않았는가 |  |  |

substring·hash 검사는 원천 일치 검사이며 의미 정확성 인증이 아닙니다.

검토 hash preimage는 schema 순서의 `WikiDraftPayload` JSON, 줄바꿈 하나, `compiler_mode`입니다. 독립 도구로 재계산한 SHA-256을 기록합니다. hash 일치와 head CAS는 같은 byte 묶음 및 동시 수정 방지만 확인하며, 실제 열람·검토 수행을 증명하지 않습니다.

## 6. 게시 결정

- reviewer subject / non-null `effective_person_id`:
- reviewer 권한: 실제 human, `READ+APPROVE`
- proposer와 subject·유효 `person_id`가 모두 다른가:
- publish에 제출할 `reviewed_payload_hash`:
- 결정: 게시 / 수정 후 새 draft / 반려
- 게시 page revision / version ID / page hash:
- 다음 검토를 촉발할 원천·ACL·계약 사건:
- 현재 server query floor가 draft classification보다 높지 않은가:
- 과거 revision 게시 재시도라면 `wiki_publish_replay_superseded` 409가 예상되는가:
- proposer/reviewer person ID의 API·로그·export 노출과 보존이 개인정보 정책에 맞는가:

게시 성공은 이 payload의 독립 검토 기록입니다. 기업 배포, 의미 정확성 전체, 보안 인증이나 KPI 개선을 승인하지 않습니다.
