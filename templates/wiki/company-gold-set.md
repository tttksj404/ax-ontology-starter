# 회사 LLM Wiki gold set·비교 평가서

RAG-only, Wiki-only, Hybrid를 같은 회사 원천과 조건에서 비교합니다. 현재 Wiki runtime과 lint가 실행됐다는 사실은 의미 정확성, 회사 KPI, 보안 인증이나 ROI 증거가 아닙니다.

현재 공개 route는 RAG-only `/v1/ask`와 Hybrid `/v1/wiki/query`입니다. Wiki-only는 보이는 page body와 저장된 raw citation만 쓰는 평가용 ablation이며 운영 API 기능으로 기록하지 않습니다.

## 1. 동결 범위

| 항목 | version / SHA-256 / 위치 | owner / reviewer |
|---|---|---|
| source snapshot·contract·`evidence_roles`·ACL |  |  |
| identity·purpose·clearance matrix |  |  |
| domain pack / ontology |  |  |
| Wiki page revision / payload hash / source bindings |  |  |
| provider / prompt / policy |  |  |
| case set / hidden split / rubric |  |  |
| page 집합 freeze 시각 / compile query digest |  |  |
| 평가 code / 실행 환경 |  |  |

- 회사 / 업무 / 평가 기간:
- 합성 / 복사된 비운영 / shadow / 실제 운영 중 해당 상태:
- dev case 작성자 / Wiki 작성자·검토자:
- hidden case 보관자(hidden을 Wiki 작성자·검토자에게 공개하지 않음):
- 현업 독립 채점자 1 / 채점자 2 / 불일치 조정자:
- RAG-only, Wiki-only, Hybrid가 같은 source head를 사용했는가:
- hidden query가 compile query와 겹치지 않는가:

## 2. case 명세

| case ID | 유형 | 질의·fixture | actor / purpose | 기대 답·유보 | 필수 raw 원천 | 금지 원천·위험한 오답 | reviewer |
|---|---|---|---|---|---|---|---|
|  | single / multi-source / conflict / unknown / stale / ACL / tombstone / derived-reingest / domain |  |  |  |  |  |  |

최소한 다음 사건을 포함합니다.

- 서로 다른 group의 원천을 모두 볼 수 있는 actor와 하나만 볼 수 있는 actor
- current revision이 의존하는 source의 update·retire·ACL change 뒤 영향 page 비노출
- 과거 revision의 source만 변경됐을 때 독립된 current revision 유지
- tombstone 뒤 의존 draft·revision만 scrub하고 독립된 clean current revision 유지
- server query floor 상향 뒤 낮은 분류 draft·page 재compile 요구
- `object_id`·`hops` scope 밖 input object가 하나라도 있는 Wiki page 제외
- anchor·hop scope 객체의 현재 ACL 회수 뒤 page·query·export 비노출
- 숨은 existing/stale/scrubbed head의 revision 탐색과 overwrite가 미존재와 같은 404
- 최종 10개 citation 예산 안에서 page 선택 후 남는 자리를 raw citation으로 보충
- `derived_output` 계약과 marker가 있는 오분류 raw export
- inline·reference·angle-bracket·protocol-relative Markdown 이미지와 HTML tag export 차단
- marker가 제거된 raw 오등록이 현재 자동 인증되지 않는 한계
- `Wiki query generate=true`의 422와 action 미연결

## 3. 방식별 결과

| case ID | 방식 | 답변·유보 | raw citations / Wiki pages | 품질 | 근거 충실도 | 권한·삭제·오염 veto | 지연·provider 사용량·비용 | 검토·재작업 시간 |
|---|---|---|---|---|---|---|---|---|
|  | RAG-only / Wiki-only / Hybrid |  |  |  |  |  |  |  |

## 4. 현재 자동 검사와 사람 평가를 분리한다

| 항목 | runtime 자동 증거 | 별도 현업·보안 평가 |
|---|---|---|
| source binding | document/content/ACL hash, source/contract version·hash, valid until | 원천 기원·업무 효력의 진위 |
| citation | 서버 raw citation의 ID·메타데이터·substring | 두 채점자의 claim별 semantic entailment·완전성·공정성 |
| 권한 | source별 live ACL AND, page classification, purpose | 회사 역할 설계와 권한 부여의 타당성 |
| lifecycle | stale·scrub 상태와 일반 읽기 차단 | backup·download·provider 물리 삭제 |
| lint | 권한 있는 manager에게 `source_changed` 또는 `recompile_required`와 source/object/head/floor reason | 모순·누락·orphan·업무 최신성·poisoning 의도·숨은 head 전체 재고 |
| 결과 | case별 응답·유보·지연 원값 | KPI·현업 시간·재작업·ROI |

빈 lint 결과를 의미 정확성 PASS로 사용하지 않습니다.

runtime은 semantic entailment를 인증하지 않습니다. 두 채점자는 서로의 점수를 보기 전에 독립 판정하고, 불일치는 정한 조정자와 rubric에 따라 기록합니다. hidden case 결과를 본 뒤 page·prompt·rubric을 바꾸면 새 평가 세대로 다시 freeze합니다.

## 5. 집계와 오류 분류

| 범주 | RAG-only | Wiki-only | Hybrid | 현업 판정·근거 |
|---|---|---|---|---|
| 답변 품질 |  |  |  |  |
| raw citation entailment·source coverage |  |  |  |  |
| 다중 원천 종합·모순 제시 |  |  |  |  |
| 필요한 유보 / 불필요한 유보 |  |  |  |  |
| source update·ACL·tombstone 반영 |  |  |  |  |
| server floor·object scope·citation budget 경계 |  |  |  |  |
| derived 재수집·검색조작 내성 |  |  |  |  |
| 지연·provider 사용량·인프라 비용 |  |  |  |  |
| 사람 검토·재작업·교육·운영 시간 |  |  |  |  |
| 원천별 AND로 줄어든 독자 비율·stale 재검토 빈도 |  |  |  |  |

| 발견한 오류 | 고칠 층 | 변경안 | 새 회귀 case | owner |
|---|---|---|---|---|
|  | source contract / evidence role / domain pack / Wiki compile / retrieval / policy / review |  |  |  |

## 6. 안전 veto와 결정

- [ ] 권한 밖 raw source·Wiki page·link metadata 노출이 없다.
- [ ] retire·tombstone·stale source를 사용하지 않았다.
- [ ] 최종 citation은 raw 문서까지 역추적된다.
- [ ] derived output과 marker export가 raw evidence로 승격되지 않았다.
- [ ] action 권한·실행이 Wiki body나 query에서 직접 생기지 않았다.
- [ ] source update·ACL·tombstone이 실제 의존 Wiki 항목에만 전파되고 독립 current revision은 유지됐다.
- [ ] `WikiPageHit.input_citations`와 `source_bindings`가 출력 `citations`보다 넓은 실제 compiler 입력을 보존했다.
- [ ] scope 객체와 generation route가 검토 hash·page·export에 결속되고 secrets가 포함되지 않았다.
- [ ] hidden case를 Wiki 작성자·검토자에게 공개하지 않았고 두 현업 채점자가 독립 평가했다.

하나라도 실패하거나 확인할 수 없으면 평균 점수와 관계없이 승격을 중단합니다.

- 선택: RAG-only 유지 / Hybrid 추가 검토 / Wiki 재설계 / 중단
- 허용 사용자·업무·자료 등급·기간:
- 미구현 통제와 owner:
- dry run / shadow / staged promotion 다음 조건:
- rollback 대상과 중단 신호:
- 결정자 / 현업 reviewer / 보안 reviewer / 시각:

이 평가는 동결한 입력과 실행 범위에 한정됩니다. field review를 실제 출시 승인, 정확성 개선 또는 검증된 ROI로 보고하지 않습니다.
