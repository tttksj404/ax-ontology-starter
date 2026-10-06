# v0.2 지식 수명주기 hardening 독립 검토

- 검토 시각: 2026-10-02 KST
- 검토 방식: 현재 작업 트리의 소스·표적 테스트를 읽고, 별도 HTTP·DB 반례 probe와 정적 검사를 실행한 읽기 전용 검토
- 판정: **PASS — 이 검토 범위에서 재현 가능한 P0/P1 없음**

이 판정은 아래 SHA-256으로 고정한 지식 변경 경로에만 적용한다. 실제 IdP, 현업 권한 소유자, 외부 원천·ERP, 물리 삭제, 다중 인스턴스 DB와 운영 복구는 검증하지 않았다. 전체 suite, wheel/installed HTTP smoke, 외부 모델 감사의 최종 통합 판정도 이 문서의 근거가 아니다.

## 검토한 불변식

1. 기존 문서의 upsert, ACL 변경, retire, tombstone은 호출자가 저장 ACL snapshot의 tenant, group, clearance를 만족해야 한다. 권한 없음과 문서 없음은 `document_not_found` 404로 동일하게 닫혀야 한다.
2. 새 managed 문서 upsert와 기존 문서 ACL 변경은 빈 `groups`를 만들 수 없어야 한다. 비어 있지 않은 다른 그룹으로 자기 권한을 회수하는 변경은 계속 허용되어야 한다.
3. retire와 ACL 변경은 현재 계약 version/hash까지 정확한 binding을 요구한다. upsert는 같은 tenant/source/contract ID와 새 source version이면 현재 binding으로 재바인딩할 수 있다. tombstone만 저장 ACL 권한을 유지한 같은 소유 binding에서 version/hash drift 정리를 허용해야 한다.
4. tombstone은 현재 binding으로 기록하되 직전 ACL snapshot과 수락된 source-version history를 보존해야 한다.
5. 신규·replay 영수증의 `documents`는 현재 row의 exact contract binding과 actor의 `AUDIT` 가시성으로 투영되어야 한다. 저장 receipt, audit, 상위 revision/hash 필드는 바뀌지 않아야 한다.
6. 거부된 배치는 document row, tenant/source revision, audit와 source-version history를 함께 변경하지 않아야 한다.

## 소스 고정점

| 파일 | SHA-256 |
|---|---|
| `src/ax_starter/knowledge.py` | `785bc8db3fac69a1bf693f435f0dce8e486c8b43094c7031c9f0d416a339e1a7` |
| `src/ax_starter/knowledge_mutations.py` | `87fa54de3793706fca39161648af145904952cdd2798a42fdcfcf7a18a7ed7bd` |
| `src/ax_starter/knowledge_visibility.py` | `85d8df9286217e41d75e9ce69cfa3b40fe2eb12f5d103f927313df0f095a2a0c` |
| `src/ax_starter/knowledge_store.py` | `e13caad12615f645e473210f884a22c6de6f60de1173bf9f3e67829ce18fce6e` |
| `src/ax_starter/knowledge_contracts.py` | `cbe6b3e10fbdd32056718bf4f7170f0b4e0f60952d72b2cd89fe90c9c61b6532` |
| `src/ax_starter/knowledge_binding.py` | `7822edef53f04ce1325d58491ad48dc47825c9d4b566bcbf402f0338a895acd8` |
| `src/ax_starter/store.py` | `4a6b13fd86ca54577719a90536291c8ceebadd23f44a90db59f55ea943adceec` |
| `src/ax_starter/api.py` | `6034eb2449156af213a49d216d939154978deb75d578a999256ac723f8df3ae1` |
| `src/ax_starter/api_extensions.py` | `a07e6d45aa03a635fe1bbcb64ef0c100ddbf7ac2e9e0c1da4d63311cb235103e` |

| 표적 테스트 | SHA-256 |
|---|---|
| `tests/test_knowledge_empty_groups.py` | `74aa51f8d43230fa8d83fe6ee32ddd97874cc7e109518ede0c50065337de0b7f` |
| `tests/test_knowledge_mutation_acl.py` | `3255e9d24250afc719ab93f827ffac79810474a3b0934a91272ccf3babea5def` |
| `tests/test_knowledge_tombstone_drift.py` | `5332f8be40fd8c1d23a85caadebeff9c614a8748ee1f1d49deb593067c55efee` |
| `tests/test_knowledge_contract_binding.py` | `4b40edabd33e55892e5d51a7c52ec3eb3ddd09eb70b063a9e0218a1c3e230d75` |
| `tests/test_knowledge_atomicity.py` | `e0a6602bac93ced91fcd4c00e117217014d548f5665ed23b6fc4af68481f934f` |
| `tests/test_knowledge_state_visibility.py` | `33f9a508d680b9639e83f58aaf5bec9cb16637977ab8eef4442667b90a560840` |
| `tests/test_knowledge.py` | `42569bc6acb1bb8f779d78fdd171b2f4b165d3564de63101444dbe2d612cb0d1` |

Root가 별도로 작성 중인 installed HTTP smoke helper는 아직 고정 대상이 아니므로 이 manifest에서 제외했다.

## 코드 대조 결과

- `knowledge_mutations.py:92-111`은 기존 row가 있을 때 stable tenant/source/contract ID와 저장 ACL 가시성을 먼저 확인하고, `:100-101`에서 빈 candidate groups 또는 계약 validation 실패를 422로 거부한다. 새 source version 검사는 그 뒤에 있어 거부된 빈 ACL이 history를 선점하지 않는다.
- `knowledge_mutations.py:40-85,148-172`에서 retire와 ACL 변경은 `_owned_document(... exact_binding=True)`를 사용하고, tombstone만 `exact_binding=False`를 사용한다. 네 기존 문서 경로 모두 `management_access_visible`을 거치며, ACL 변경은 `:166`에서 빈 groups를 거부한다.
- `knowledge_visibility.py:58-65`의 쓰기 ACL은 tenant/group/clearance만 검사한다. 문서 purpose를 생략하는 현재 설계와 일치하며, 계약 수준 `READ`, `AUDIT`, `MANAGE_KNOWLEDGE` 검사는 `KnowledgeService` 진입 경로에서 별도로 유지된다.
- `knowledge_mutations.py:54-69`의 tombstone은 본문을 제거하고 lifecycle/revision/현재 contract version/hash만 갱신한다. `access_snapshot`과 source version은 저장 row에서 유지된다.
- `knowledge_visibility.py:87-96,128-140`은 receipt 문서 목록을 현재 row, 현재 exact contract binding, 현재 문서 ACL의 `AUDIT` 가시성으로 제한한다. `knowledge.py:144-150,187-201`은 replay와 신규 성공 모두 이 투영을 반환하며, 저장 receipt와 audit를 투영 결과로 덮어쓰지 않는다.
- `store.py:61-74`의 `BEGIN IMMEDIATE` 경계 안에서 지식 row, head, audit, watermark와 batch receipt가 처리되므로 예외가 발생한 표적 반례에서 함께 rollback됐다.

## 발견·수정된 P1 반례

초기 검토에서 빈 document groups가 계약 groups의 부분집합으로 수락되는 경로를 실제 재현했다. 기존 ACL을 빈 groups로 변경하면 응답 문서가 숨겨진 뒤 모든 principal에 대해 group 교집합이 성립하지 않아 upsert, ACL 변경, retire, tombstone이 모두 404가 됐다. 관찰값은 `cleanup_error document_not_found 404`, `row_lifecycle active groups 0 revision 2`였다. 이 상태는 정상 API 입력만으로 활성 문서를 수명주기 경로에서 고립시켰으므로 P1이었다.

수정 후에는 managed 신규/기존 upsert candidate의 빈 groups를 `knowledge_mutations.py:100-101`에서, ACL 변경의 빈 groups를 `:163-172`에서 `data_contract_violation` 422로 거부한다. 공통 `Access`의 deny-all 표현이나 bootstrap 동작은 바꾸지 않았다. 비어 있지 않은 다른 허용 그룹으로 바꾸는 자기 권한 회수는 계속 성공하며, 성공 응답의 `documents`만 현재 actor에게 빈 배열로 투영된다.

## 실제 표적 검증

### 자동 테스트

- 표적 pytest 7개 파일: **45 passed in 1.70s**
  - TQE capsule: `20261002-124141269-c59932e1`
  - 원문 로그 SHA-256: `9427853fd7127a8177509037fbee00ea9a15a2114569cfcf593a00ce844d4a23`
  - `manual_inspection_required=false`, `auto_evidence.hash_verified=true`, `all_detected_risk_lines_captured=true`
- empty-groups 3건, 새 source-version 재바인딩, tombstone contract drift cleanup, 비어 있지 않은 self-revoke를 다시 지정 실행: **6 passed in 0.60s**
- 관련 소스·테스트 Ruff: **All checks passed**
- 관련 소스·테스트 basedpyright: **0 errors, 0 warnings, 0 notes**

### HTTP·DB 반례

- 현재 소스의 실제 FastAPI 경로에서 비소유 그룹이 기존 문서에 시도한 upsert/ACL 변경/retire/tombstone 4건과 소유자가 없는 ID에 시도한 ACL 변경/retire/tombstone 3건이 모두 동일한 `404 {"error":"document_not_found"}`였다. tenant revision은 1로 유지됐다. 출력: `HTTP_UNIFORM_404_CURRENT_OK denied=4 missing=3 revision=1`.
- managed 신규 문서의 빈 groups는 API에서 422를 반환하고 tenant revision 0, accepted history 0, audit 0을 유지한다. 기존 문서 ACL을 빈 groups로 바꾸는 요청도 422이며 revision 1, history 1, audit 1과 기존 ACL을 유지한다. 근거는 `tests/test_knowledge_empty_groups.py:29-109`이다.
- schema 4 형식에 맞게 빈 ACL snapshot을 직접 주입해 legacy 상태를 모사했다. upsert/ACL 변경/retire/tombstone 4건은 모두 404였고 row는 active revision 1, audit 1, history 1로 유지됐다. 출력: `LEGACY_EMPTY_ACL_FAIL_CLOSED_OK denied=4 revision=1 audit=1 history=1`.
- 현재 계약 version/hash drift 뒤에도 같은 owner/source/contract ID의 tombstone은 현재 binding으로 정리하면서 원 ACL snapshot을 유지했고, source가 바뀐 drift는 404와 원자 불변이었다. 근거는 `tests/test_knowledge_tombstone_drift.py:48-118`이다.
- 같은 contract ID/source의 기존 문서는 새 source version upsert로 현재 contract version에 재바인딩됐다. 근거는 `tests/test_knowledge_contract_binding.py:137-174`이다.

## 명시적 경계와 잔여 리스크

- replay `documents`의 **포함 여부**는 현재 row의 binding/ACL로 결정되지만, 포함된 각 meta 값은 원래 저장 receipt의 역사적 source version/hash다. 현재 row 메타데이터로 다시 쓰는 계약이 아니다. 상위 revision/hash와 저장 receipt/audit도 원본 그대로다.
- 문서 purpose는 기존 문서 쓰기 ACL에서 의도적으로 사용하지 않는다. 대신 계약의 현재 `READ+AUDIT+MANAGE_KNOWLEDGE`와 저장 ACL tenant/group/clearance를 모두 요구한다.
- 이미 존재하는 빈 groups 또는 ACL snapshot 불명 legacy row는 자동 복원하지 않고 모든 일반 mutation에서 fail-closed 404가 된다. 원본·감사·권한 소유자를 대조한 별도 관리자 migration이 필요하다. 신규 managed upsert/ACL 변경의 empty-groups 422와 이 legacy 정리 경계를 운영 문서에 명시해야 한다.
- tombstone은 로컬 SQLite의 논리 삭제다. WAL, 미할당 페이지, 백업, 외부 검색 인덱스, 모델 공급자나 원천 시스템의 물리 삭제를 증명하지 않는다.
- registry 파일과 SQLite commit의 외부 원자성, DB 파일 전체 재작성 공격, 외부 불변 audit anchor, 다중 인스턴스 격리와 장애 복구는 검증하지 않았다.
- 실제 IdP/SSO/MFA, 현업 조직의 group 소유·공석 여부, 외부 SharePoint/ERP/FHIR/OPC UA 연동, 개인정보·분야별 법무 판정과 실제 고객 데이터 품질도 검증하지 않았다.
- 이 문서는 전체 suite, 패키징/설치 스모크, Root의 후속 HTTP helper, Opus 감사 결과를 대신하지 않는다. 해당 결과는 각 실행의 최신 SHA와 원문 증거로 별도 합쳐야 한다.
