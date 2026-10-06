# v0.2.0 독립 구현 검토

검토일: 2026-10-02

## 판정

**PASS — 저장소가 명시한 v0.2 참조 런타임 범위.**

현재 소스와 아래의 표적 회귀를 다시 확인한 결과, 검토 범위에 열린 P0/P1은 없다. 이 판정은 실제 회사 배포, 보안 인증, 독립 현업 평가, IdP 운영, 원천 시스템 연결 또는 외부 ERP 쓰기에 대한 PASS가 아니다. 전체 suite·패키지·HTTP 검증과 별도 Opus 최종 감사는 이 문서와 구분한다.

`design-review-output.json`은 설계 가설 자료로만 사용했다. 해당 결과 자체가 저장소를 읽거나 테스트를 실행하지 못했다고 밝히므로, 제안된 항목을 요구사항으로 그대로 복제하지 않고 현재 소스와 재현으로 판정했다.

## 닫힌 P0/P1

| 항목 | 최종 상태 | 소스와 회귀 근거 |
|---|---|---|
| 다른 tenant·source·contract가 같은 전역 문서 ID를 차지함 | 기존 row의 tenant, source, contract ID가 모두 같아야 upsert할 수 있고 다른 claim은 일률적인 404로 거부한다. 같은 contract ID의 live version/hash upgrade는 새 source version upsert로 다시 묶을 수 있다. | `src/ax_starter/knowledge_mutations.py:85-105`, `tests/test_knowledge_contract_binding.py:85`, `tests/test_knowledge_contract_binding.py:141` |
| 오래된 snapshot의 ACL/content 원복과 source version 재사용 | source별 `last_observed_at`은 엄격 단조이고, 수락된 문서 버전은 영구 history에서 재사용을 막는다. apply/import idempotency namespace와 snapshot envelope digest도 분리한다. | `src/ax_starter/knowledge.py:142-174,203-213`, `src/ax_starter/knowledge_schema.py:113-215`, `tests/test_knowledge_migration.py:69,140` |
| schema 2 마이그레이션 후 과거 snapshot 수락 | 기존 audit가 있으면 마지막 knowledge batch 시각을, 매핑할 audit가 없으면 migration 시각을 보수적 watermark로 둔다. 원래 `observed_at`을 복원하거나 인증한다고 주장하지 않는다. | `src/ax_starter/knowledge_schema.py:163-215`, `tests/test_knowledge_migration.py:69,140` |
| 요청 중 contract 변경 뒤 stale knowledge write | transaction 진입 직후 live registry에서 같은 tenant/contract의 version과 canonical hash를 다시 확인하고, 달라졌거나 registry가 사라지면 replay/read/write 전에 fail closed한다. | `src/ax_starter/knowledge.py:105-144`, `tests/test_knowledge_contract_toctou.py:14` |
| credential 회수 뒤 action/knowledge replay | request-local `SecretStr`에 보존한 바로 그 credential을 현재 registry로 다시 인증한다. action write와 knowledge state/apply/import는 `BEGIN IMMEDIATE` 안에서 replay/read보다 먼저 재인증한다. raw credential은 응답·감사·DB에 들어가지 않는다. | `src/ax_starter/api.py:65-118`, `src/ax_starter/store.py:62-75`, `tests/test_knowledge.py:241`, `tests/test_knowledge_snapshot.py:223` |
| 같은 사람의 다른 subject/auth 방식 또는 subject 재할당으로 자기 승인·기존 승인 재사용 | human 승인과 effective person 분리를 검사하고 proposer/approver의 actor kind와 person ID를 payload/approval에 고정한다. pending 제안은 현재 매핑이 바뀌면 중단하고, v0.1의 필드 없는 pending 제안은 재제안/재승인을 요구한다. | `src/ax_starter/action_contracts.py:41-71`, `src/ax_starter/action_authorization.py:36-63`, `tests/test_v02_action_binding.py:12,80` |
| query의 낮은 self-label로 외부 반출 | provider의 서버 소유 기본 query floor는 `RESTRICTED`이고 query, answer, citation의 최대 등급으로 route를 판정한다. 더 낮은 floor는 분류된 입력 경로와 회사 승인 뒤 operator가 명시하는 설정이다. | `src/ax_starter/providers.py:24-116`, `tests/test_egress_regressions.py` |
| Windows JSON CLI 입력이 UNC/device/ADS/reparse/outside-root를 통과 | 파일 시스템 접근 전 문자열 검사를 하고, 지정 root 안의 일반 로컬 파일만 strict resolve 후 크기 제한과 Pydantic 계약으로 읽는다. runtime 운영 설정 경로는 별도 신뢰 경계다. | `src/ax_starter/local_input.py:16-67`, `src/ax_starter/cli.py`, `src/ax_starter/v02_cli.py` |
| contract hash가 frozenset 순서에 따라 프로세스마다 달라짐 | `required_provenance`를 정렬 직렬화해 같은 계약의 canonical hash를 안정화했다. | `src/ax_starter/data_contracts.py:119-121`, `tests/test_data_contracts.py` |
| release rubric/case-set 미결합, 임계값 전 반올림, 중복 case 가중 | runtime criteria와 fixture set digest를 manifest에 대조하고 원값으로 임계값을 판정한다. case ID 중복은 평균 계산 전에 거부한다. 출력은 계속 `input_derived_recommendation`, `live_validated=false`, `evidence_origin_verified=false`다. | `src/ax_starter/release_gate.py:117-134,148-215,222-264`, `tests/test_release_gate.py:48,60,92` |
| NFC 질의와 NFD 한글 문서의 false abstain | 검색 비교 문자열만 NFC+casefold로 정규화하고 citation quote와 content hash는 원본을 보존한다. | `src/ax_starter/retrieval.py:122-130`, `tests/test_v02_unicode_retrieval.py:11` |
| document JSON의 부분 변조가 meta hash를 우회해 검색·실행 근거가 됨 | document read 때 파싱 실패, id/source version/tenant/content/access meta 불일치를 `knowledge_integrity_failure`로 닫는다. 전체 document canonical JSON과 state head의 외부 무결성 증명은 이 버전의 범위가 아니다. | `src/ax_starter/knowledge_store.py:129-164`, `tests/test_knowledge_integrity.py:18` |

## Opus 가설 중 현재 결함으로 복제하지 않은 항목

- 문서 ID는 tenant별 복합키가 아니라 pack 전체에서 유일한 ID라는 명시적 불변식이다. 다른 tenant/source/contract의 collision은 별도 row 생성 대신 uniform 404로 차단한다.
- snapshot import는 명시된 문서의 upsert만 수행한다. 누락 문서를 삭제로 추론하지 않으므로 partial snapshot 대량 삭제 반례는 현재 기능에 없다.
- managed document에서 graph edge를 추출하지 않는다. pack link는 자체 ACL을 가진 정적 입력이므로 document ACL 축소 뒤 파생 edge가 남는 경로가 없다.
- knowledge와 action은 같은 SQLite 파일과 `BEGIN IMMEDIATE` transaction을 사용한다. 현재 구현에 별도 index/cache/connector write connection이 없어 connection authorizer 분리는 현 기능의 재현 결함이 아니다.
- onboarding 결과는 self-reported readiness이고 runtime provider policy를 생성하거나 승격하지 않는다. release gate도 입력 기반 현업 검토 자격만 출력하며 배포 또는 `productionReady`를 만들지 않는다.

## 독립 검증

표적 회귀 11개 파일을 다시 실행했다.

- 결과: **66 passed in 2.13s**
- token-quality-engine capsule: `20261002-105543689-5e17c417`
- 원문: `C:/Users/SSAFY/.codex/artifacts/tool-output/20261002-105543689-5e17c417.log`
- SHA-256: `5d6dc13f96b9f2f73fbdbec188bfa3eadb30f9491a1ecbd0fadd5a7a085727ab`
- 증거 게이트: `manual_inspection_required=false`, `auto_evidence.hash_verified=true`, `all_detected_risk_lines_captured=true`

포함 범위는 release binding/중복/임계값, proposer·approver identity와 legacy proposal, contract ownership/drift/TOCTOU, schema 2→3 watermark migration, document row integrity, Unicode retrieval, snapshot lifecycle·atomicity다. 전체 suite는 중복 실행하지 않았고 root의 최종 검증 대상으로 남겼다.

## 검증하지 않은 운영 경계

- 실제 기업 IdP의 발급 정책, SSO/MFA, `sub` 안정성, 사용자·서비스 등록 통제, 키 회전 전파, sender-constrained token과 replay 방지는 검증하지 않았다.
- SharePoint, ERP, CRM, FHIR, OPC UA 등 원천 connector와 원천 ACL 평탄화, 원천 삭제·보존 전파, snapshot `observed_at`의 진위는 구현하거나 검증하지 않았다.
- action 실행은 로컬 SQLite 객체 상태 변경이다. 외부 ERP side effect, outbox, 재시도, 중복 delivery, 보상 transaction과 이미 시작된 외부 전송의 원자적 회수는 검증하지 않았다.
- tombstone은 논리 삭제다. SQLite/WAL, 백업, provider, 검색 서비스의 물리 삭제와 법적 삭제 SLA를 증명하지 않는다.
- 실제 network default-deny, TLS termination, KMS/WORM/SIEM, DB 암호화, 백업 복원, HA·부하·장애 주입은 외부 운영 통제다.
- field reviewer의 자격·독립성, 사례 대표성, 실제 회사 문서의 품질·보안·ROI, evidence digest의 원천과 실제 배포 상태는 검증하지 않았다.
- DB와 운영 설정 파일은 운영자 ACL·배포 승인·호스트 무결성 안의 신뢰 입력이다. read 시 핵심 document/meta 불일치는 차단하지만 전체 canonical document/state head, DB 파일 전체 교체와 audit chain 재작성은 외부 anchor 없이 증명하지 않는다.

## 후속 업그레이드 우선순위

1. 원천 connector·ACL/삭제 propagation과 reconciliation SLO
2. 전체 document canonical digest, state-head 검증과 외부 audit anchor
3. 실제 IdP/SCIM/MFA 및 단기 workload identity 운영 검증
4. 외부 시스템용 outbox·idempotency·retry·compensation
5. 서명된 field evaluation, 독립 reviewer binding, 현장 gold set과 운영 관찰
