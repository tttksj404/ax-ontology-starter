# v0.2 managed document namespace 독립 검토

- 검토 시각: 2026-10-02 KST
- 판정: **PASS — Opus가 지적한 cross-tenant document ID 존재 구분·선점 경로는 현재 고정 소스에서 닫힘**
- 방법: 현재 소스와 문서 원문 대조, 표적 pytest, Ruff, basedpyright, 별도 DB 반례 probe

이 문서는 이전 독립 검토와 Opus 원문을 대체하지 않는다. 이번 판정은 아래 해시의 managed upsert namespace 변경에 한정한다. 전체 suite, wheel/installed HTTP smoke, Root가 별도로 수정하는 smoke helper, 실제 IdP·현업 권한·외부 원천은 판정 범위 밖이다.

## 입력 감사와 소스 고정점

Opus 원문 `docs/evidence/v0.2.0/hardening-output.json`의 SHA-256은 `0148caf96643760857d99a9f21f989ac2a58657e2ca5ac514a736997e33f9a23`이다. 원문 판정은 `NEEDS_FIX`였고, `knowledge_documents.document_id`가 전역 기본 키인 상태에서 upsert가 문서 조회를 먼저 수행해 cross-tenant ID의 존재 여부에 따라 404와 422가 갈리고 미사용 foreign ID를 선점할 수 있다는 P2를 제시했다.

| 구현·예제 파일 | SHA-256 |
|---|---|
| `src/ax_starter/knowledge_mutations.py` | `d2653b8a1b448e46ab36e3cfa31740df02dd1581623dbee6980e6f1fb0b011e6` |
| `src/ax_starter/knowledge_schema.py` | `071974177fd02dd0b722d9de139c2a50532d0512514627aa5a44abc9d4f253a9` |
| `src/ax_starter/v02_examples.py` | `3e99eb236898b8f3f8b192a98feddc19214b1dc867a87cf42e335be50897ca21` |
| `examples/v0.2/document-candidate.json` | `8defd8589da8ea88ed813b910486b41c69ce48cb6878b350f26fba139da95dfd` |

| 표적 테스트 파일 | SHA-256 |
|---|---|
| `tests/knowledge_fixtures.py` | `545e0d97403db19b5d4219fa56027f3ec3f7736aa0304c87ca2f553952474c71` |
| `tests/test_knowledge_tenant_namespace.py` | `096cc8c06d14aa4fbf7c0863b3b6655e20cd8f2457905f976a569b30f4fd2f04` |
| `tests/test_knowledge_tombstone_drift.py` | `4cb4dd7615118d4fad73f5088ea36bd1786da69fec31d4177de698c875be9a9e` |
| `tests/test_knowledge_atomicity.py` | `03429c0c2631506b3352252c76c7460a169b23abbb332cd7415910003601dbf9` |
| `tests/test_knowledge_empty_groups.py` | `d1dd27e0147a184a8dfb67f846a54cfa1c508130db2bbe29071fc02bf459729f` |
| `tests/test_knowledge_contract_binding.py` | `8bd7450779e0a7343b8a153160664ccba119c6977e320779d284d013fce61281` |

| 사용자·운영 문서 | SHA-256 |
|---|---|
| `README.md` | `9442c3dda7fcf789677e36a6d2eda3bf5eae03ec3ee4ce0cf4645b32b73c1f97` |
| `docs/ARCHITECTURE.md` | `e703d904b9d760ea5ad6a8e5a7ebe9b4a404e7181885675147a7fdc88528d5de` |
| `docs/OPERATIONS.md` | `1e2909c7fb931653c7a86a715354b61ee9fa859f89601104fd17b61c2be28a17` |
| `docs/UPGRADE_GUIDE.md` | `2f39f293d318a200937bc3593aa8b61a278815a28b575a368d2290bcafed93cc` |
| `docs/V02_GUIDE.md` | `c07cd9064bd8c7c82aced7f2f99ec2142b927f4d8b946792cf85e2df4aef35fd` |
| `docs/SECURITY_MODEL.md` | `a4d776c88f2079974f67ddef66e753ca1c81d6c3d556dc96fce76af188e90ec7` |

Root 소유의 runtime/installed smoke helper는 수정 중인 통합 산출물이므로 이 manifest에 포함하지 않았다.

## 코드 판정

### P2 경로 차단

- `knowledge_schema.py:54-60`은 `document_id TEXT PRIMARY KEY`를 유지한다. tenant별 복합 키로 마이그레이션한 구현은 아니다.
- `knowledge_mutations.py:92-102`는 `_require_document_namespace`를 `document_record`보다 먼저 호출한다. 따라서 ID가 이미 다른 tenant row에 있든 비어 있든 저장소 조회 결과가 오류 코드를 바꾸지 않는다.
- `knowledge_mutations.py:176-179`의 규칙은 `document_id.rpartition(".")`의 prefix가 현재 계약 tenant와 정확히 같고, separator와 suffix가 존재하며, suffix 안에 점이 없어야 한다는 것이다. `acme` 계약에는 `acme.<점 없는 접미부>`만 허용된다.
- 이 검사는 upsert에만 적용된다. retire, tombstone, ACL 변경의 `_owned_document` 경로에는 namespace 검사를 추가하지 않아 기존 비정규 managed ID의 통제된 cleanup을 유지한다.

수정 전에는 beta 계약이 `acme.secret-like`를 제출할 때 기존 ID이면 소유 binding 검사에서 404가 되고, 미사용 ID에 빈 groups를 결합하면 422가 됐다. 미사용 foreign ID에 유효 candidate를 제출하면 beta row가 전역 ID를 선점할 수도 있었다. 현재 구현은 네 경우 모두 문서 조회 전 namespace 422로 닫는다.

### 정상 동작 보존

- `acme.same`과 `beta.same`은 서로 다른 전역 ID이므로 같은 DB에서 함께 존재한다.
- tenant 자체에 점이 있는 `acme.eu`는 `acme.eu.same`을 허용한다. 마지막 점 기준 prefix가 tenant 전체와 일치하기 때문이다.
- 같은 tenant/source/contract ID의 새 source version upsert, 저장 ACL 검사, 빈 groups 422, tombstone drift cleanup은 기존 경로를 유지한다.
- `tests/test_knowledge_tombstone_drift.py:121-168`은 계약 제거 상태에서 tombstone이 `data_contract_changed`로 원자 차단되고, 같은 owner binding을 version 2로 통제해 재등록하면 drift tombstone이 성공하는 순서를 고정한다.
- `src/ax_starter/v02_examples.py:72-90`과 JSON 예제는 각각 계약 tenant prefix를 가진 managed ID를 사용한다.

## 실제 검증

### 표적 테스트와 정적 검사

- 독립 표적 pytest 8개 파일: **52 passed in 2.08s**
  - TQE capsule: `20261002-132856006-ee791e2f`
  - 원문 로그 SHA-256: `27a75bdefa53a563942f674506255b3eff12ece20ad18ade11188c1c78da32a1`
  - `manual_inspection_required=false`, `auto_evidence.hash_verified=true`, `all_detected_risk_lines_captured=true`
- 구현 담당 범위의 보조 증거: **126 passed**, TQE capsule `20261002-132725747-4a90d317`, 원문 SHA-256 `eafbf011c39521c7c98377ef6f017b2655bc7fad70d9df7a8b4ebba8320cffe0`. 이 수치는 독립 52개 실행을 대신하지 않는다.
- 관련 구현·테스트 Ruff: **All checks passed**
- 관련 구현·테스트 basedpyright: **0 errors, 0 warnings, 0 notes**

### 독립 반례 probe

1. acme에 실제 존재하는 `acme.secret-like`, 존재하지 않는 `acme.missing-like`를 beta 계약에서 각각 유효 groups/빈 groups로 제출한 네 경우가 모두 `data_contract_violation` 422였다. acme revision/audit는 1, beta revision/audit는 0으로 유지됐다.
2. 같은 DB에서 `acme.same`과 `beta.same`을 모두 생성하고 각 tenant audit가 독립 증가함을 확인했다.
3. 같은 tenant의 claimant 계약은 이미 owner 계약이 점유한 `acme.managed-1`에 404를 받았지만 미사용 `acme.free`는 생성했다. 이는 문서화된 same-tenant 존재 추론 경계를 실제로 확인한 결과다.
4. namespace 도입 전 행을 모사한 `legacy-doc`에 retire와 tombstone을 각각 적용했다. 두 cleanup 모두 성공했고 audit가 증가했으며 tombstone은 본문을 제거했다.
5. `acme`, `acme.`, `acme.a.b`, `beta.same`을 acme 계약에 제출한 네 경계값은 모두 422였다. tenant revision 0, audit 0, 해당 ID의 accepted-version history 0을 확인했다. 출력: `NAMESPACE_EDGE_OK invalid=4 revision=0 audit=0 target_history=0`.
6. 한 배치에서 먼저 `beta.good`을 upsert하고 이어서 foreign `acme.foreign`을 upsert하도록 구성했다. 두 번째 mutation의 422가 첫 번째 document/history까지 rollback했다. 출력: `NAMESPACE_BATCH_ROLLBACK_OK documents=0 revision=0 audit=0 history=0`.
7. JSON 예제의 ID prefix, tenant, access tenant와 dot-free suffix를 파싱해 대조했다. 출력: `EXAMPLE_NAMESPACE_OK id=synthetic-tenant.support-record-1 tenant=synthetic-tenant`.

통합 probe 요약은 `NAMESPACE_PROBE_OK cross_tenant_422=4 same_suffix=2 same_tenant_boundary=404_then_create legacy_cleanup=2`였다.

## 문서 정합성

- `ARCHITECTURE.md:92-102`는 기존 문서 404 통일을 모든 ID 존재 은닉으로 확대하지 않고, namespace 검사 순서·dot tenant·upsert 전용 범위·계약 제거 순서를 구분한다.
- `OPERATIONS.md:71-100`은 신뢰 가능한 ID 발급, contract별 접미부 규칙, tenant별 DB 선택, 비정규 legacy cleanup/migration, 계약 제거 전 tombstone을 운영 순서로 둔다.
- `UPGRADE_GUIDE.md:53-92`는 같은 tenant 안의 ID 존재 추론, ACL groups/purposes/등급 확대 권한, empty groups 금지, accepted history를 포함한 ID migration을 명시한다.
- `SECURITY_MODEL.md:61-75`는 전역 PK를 tenant 격리로 과장하지 않고, legacy/bootstrap prefix 충돌을 다중 tenant 전 재고·migration 대상으로 둔다.
- `README.md:100-104`와 `V02_GUIDE.md:33-45`도 같은 경계를 사용자 관점에서 반복한다.

## 남은 경계와 운영 조건

- 이 규칙은 cross-tenant **신규 managed upsert**의 탐색·선점을 막는다. 같은 tenant 안에서는 미사용 ID 생성 성공, 타 계약·비가시 기존 ID 404, candidate 계약 오류 422가 구분될 수 있다. ID에 고객·사건·질환 같은 민감한 의미를 넣지 않고 신뢰 가능한 서버 발급자와 계약별 할당 범위를 사용해야 한다.
- 전역 `document_id` PK는 유지된다. 더 강한 tenant 격리나 같은 tenant의 독립 계약 간 충돌 방지가 필요하면 tenant별 DB 또는 후속 스키마 변경이 필요하다.
- 과거 acme 소유 row가 `beta.doc`처럼 다른 tenant prefix를 이미 점유한 경우 namespace guard가 자동 수정하지 않는다. 다중 tenant 활성화 전에 실제 owner·저장 tenant·prefix를 대조하고, ID와 accepted history를 통제된 migration으로 이동해야 한다. retire/tombstone은 사용을 중지하지만 전역 ID row 자체를 재할당하지 않는다.
- bootstrap·trusted admin 파일, entity/action/object와 일반 ontology ID는 이 신규 upsert 규칙의 대상이 아니다.
- 계약 제거 뒤에는 API가 contract ID를 해석할 수 없어 일반 cleanup도 막힌다. 제거 전에 정리하거나, 같은 tenant/source/contract ID를 승인된 설정으로 재등록하고 저장 ACL을 확인한 뒤 drift tombstone해야 한다.
- `change_acl` 관리자는 계약 범위 안에서 groups, purposes, 민감도를 확대할 수 있다. purpose 추가는 본문 열람 범위를 늘릴 수 있으므로 회사가 이 권한의 위임·승인·대조를 별도로 운영해야 한다.
- legacy migration, 실제 ID 발급자, tenant별 물리 격리, 외부 원천·ERP, 실제 IdP와 현업 권한은 이 코드 검토에서 검증하지 않았다.
- Root의 최종 전체 suite, package/wheel, installed HTTP smoke와 최신 소스 manifest가 이 판정 뒤 별도로 필요하다.
