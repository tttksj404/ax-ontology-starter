# Wiki source role·compile 검토서

원천 계약의 역할과 Wiki compile 경로를 함께 검토합니다. source role은 문서 frontmatter나 모델이 정하지 않고 서버 `DataContractRegistry.evidence_roles`가 정합니다.

## 1. 원천 계약과 role

| 항목 | 값 | 확인자 |
|---|---|---|
| tenant / contract ID / contract version·hash |  |  |
| document ID / source identifier / source version |  |  |
| content·ACL hash / valid until |  |  |
| groups / sensitivity / purposes |  |  |
| evidence role | `raw_source` / `derived_output` |  |
| role 변경 승인·배포 세대 |  |  |
| 원천 인증·서명·connector 증거 |  |  |

- role 항목은 등록된 `(tenant, contract_id)`를 정확히 가리키는가:
- 같은 계약 role이 중복되지 않는가:
- role 생략 계약, `contract_id=None` bootstrap 문서, registry 없는 legacy 실행이 v0.2 호환상 `raw_source`가 됨을 승인자가 이해했는가:
- 기업 관리 원천의 모든 계약·role을 server registry에 완전 등록했는가:

## 2. derived output 재수집 검사

| 검사 | 결과 | 증거·조치 |
|---|---|---|
| Wiki export 본문이 `AX_DERIVED_WIKI_V1`로 시작하는가 | 통과 / 실패 |  |
| export를 반입할 계약이 `derived_output`인가 |  |  |
| marker가 본문 맨 앞에 남은 오분류 raw 문서가 검색에서 제외되는가 |  |  |
| BOM·앞 공백이 있는 marker와 CLI 원형 export JSON의 `text`가 제외되는가 |  |  |
| derived role 문서가 DB에는 남고 raw current pack에서 제외되는가 |  |  |
| raw→derived role 재분류 뒤 current pack과 영향 page가 숨겨지고 재compile 대상이 기록되는가 |  |  |
| marker 제거 후 raw 오등록을 막는 connector·승인 절차가 있는가 |  |  |

임의 frontmatter로 marker를 감추거나 marker를 제거하고 raw 계약으로 등록하거나 source metadata를 위조한 문서의 기원과 의미를 현재 runtime이 인증해 알아내지는 못합니다. 이 항목이 미확인이면 자동 ingestion을 열지 않습니다.

## 3. compile 요청

| 항목 | 값 |
|---|---|
| request key / page ID / expected revision |  |
| title / kind / links |  |
| query / purpose / object ID / sensitivity |  |
| generate | `false` / `true` |
| 예상 compiler mode | `offline_extractive` / `model_draft` |
| `generation_route.mode` / `endpoint_host` / `model` / `provider_settings_sha256` |  |

`generate=false`는 provider를 호출하지 않고 `generation_route=null`입니다. `generate=true`는 현재 `ProviderConfig`의 local/private/cloud 경로를 사용하므로 분류·egress·host·보존 정책을 다시 확인합니다. loopback은 첫 hop만 제한하므로 LOCAL이면 원격 forwarding·cloud model·proxy/tunnel 차단과 필요 시 OS outbound deny를 확인합니다.

## 4. 사전검사

| 검사 | 결과 | 증거·조치 |
|---|---|---|
| 작성자에게 `READ+MANAGE_KNOWLEDGE`와 query purpose가 있는가 |  |  |
| 작성자가 non-null effective person의 HUMAN인가(SERVICE는 현재 거부) |  |  |
| page·link ID가 tenant namespace를 만족하는가 |  |  |
| request key와 expected revision이 현재 head에 맞는가 |  |  |
| raw retrieval에 citation이 1개 이상 있는가 |  |  |
| `input_citations`가 실제 컴파일러 입력 전체이고 `source_bindings`가 모든 입력 원천을 결속하는가 |  |  |
| query anchor·hop scope 객체가 검토 hash에 결속되고 작성자·reviewer가 모두 현재 볼 수 있는가 |  |  |
| 출력 `citations`가 `input_citations`의 검증된 부분집합인가 |  |  |
| 숨은 문자·prompt injection·키워드 stuffing을 검토했는가 |  |  |
| source title·본문·ACL·binding이 모델 호출 전후 같은가 |  |  |
| 독립 human reviewer와 검토 시간이 확보됐는가 |  |  |
| title·question·object ID·links 작성자 metadata를 별도 검토했는가 |  |  |

## 5. 결정

- compile 허용 / 격리 / 반려:
- draft ID / payload hash:
- reviewer와 publish 기한:
- 남은 미확인 source authenticity·semantic risk:

compile 성공은 review candidate 생성이며 publish나 의미 정확성 승인이 아닙니다.

로컬 합성 흐름은 `uv run ax wiki demo --domain procurement`, `uv run ax wiki demo --domain support`, `uv run ax wiki demo --domain hr` 중 필요한 도메인을 실행해 확인합니다. 이 데모는 `generate=false`, `model_executed=false`이며 실제 회사 데이터·성과 증거가 아닙니다.
