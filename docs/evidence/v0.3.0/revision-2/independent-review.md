# Revision 2 독립 검증

VERDICT: NEEDS_FIX

기존 Opus 감사의 직접 반례 B1·B2와 설계 감사 R2–R5는 아래 실행에서 닫혔다. 그러나 B2와 같은 retrieval scope 경계에서 객체 ACL은 통과하지만 hop link ACL만 통과하지 못하는 reviewer·reader가 draft와 page를 열람하고 게시·export할 수 있는 새 차단 반례가 확인됐다. 이 상태는 새 정적 Opus 감사의 PASS 후보로 넘길 수 없다.

## 고정 범위와 무결성

- 검증 전후 범위: `src/ax_starter/**/*.py`, `tests/**/*.py`, `pyproject.toml`, `uv.lock`, `scripts`의 Python·PowerShell·shell 검사 파일 156개.
- 검증 전 aggregate SHA-256: `db31c329c3f6364a145e59c3c4efc357c0c6676280972ef8018bdd74fd324b15`.
- 검증 후 aggregate SHA-256: `db31c329c3f6364a145e59c3c4efc357c0c6676280972ef8018bdd74fd324b15`.
- `tested-source-manifest.json`: 148개, SHA-256 `4340075078c2a2c8fa61344a5a131e4d49b02c63188bdcce6ace9b739b3a952c`; 직접 재계산한 path·bytes·SHA 불일치 0개.
- 독립 보고서와 이후 갱신되는 실행 증거 문서는 위 source aggregate에서 제외했다. 최종 Opus 입력은 문서 freeze 뒤 별도 manifest로 다시 결속해야 한다.
- 읽은 감사 원문 직접 SHA-256:
  - `.omx/artifacts/wiki-final-audit-result.txt`: `2c7d161e56d123ebafdba75cd217ae1189c60e7560b757647c0a5261f5e3fbcd`.
  - `.omx/artifacts/wiki-design-retry-result.txt`: `a5b2c515d37fc2a3c0fcadfc42e9cb592b9256927dfdf0dd34d90d212b6c8669`.
- 감사 원문 TQE 캡처: `20261006-101252832-671edb5d` / raw SHA `f4737a6d02da0193fbcb454591eee91945c2be299396ff00b19a36ddee491f8a`, `20261006-101252832-16cd9541` / raw SHA `04515f9d66f2abe457f5239c5e396c994130f9b952eced1313cbacc2fe801827`. 외부 Windows PowerShell의 한글 인코딩 변환 때문에 의미 판독에는 쓰지 않고, 위 직접 원본 SHA를 고정한 뒤 UTF-8 원문 386줄을 전부 읽었다.

## 차단 이슈 재검증

### NEW-BLOCKER: hop link ACL을 재현하지 못하는 actor가 review·publish·page·index·export를 통과함

**원인**

- `retrieval.py:69-91`의 `scope_ids`는 actor가 볼 수 있는 link만 따라 scope를 만든다.
- `wiki_object_policy.py:10-41`은 그 결과의 객체 집합만 저장하고 link 또는 경로를 결속하지 않는다. `require_scope_objects_current`와 `require_scope_object_access`도 저장 객체의 ACL만 검사한다.
- publish, draft/page read, index, lint, export는 이 객체 검사만 공유한다. 반면 Wiki query는 `wiki_query_export.py:40`에서 caller의 `scope_ids`를 다시 계산하고 `wiki_query_policy.py:24-25`에서 저장 scope 객체 집합이 그 범위에 들어갈 때만 page를 선택한다.
- 따라서 같은 actor에게 직접 page 표면은 보이지만 query 표면에서는 page가 사라지는 권한 불일치가 생긴다.

**실제 반례**

1. anchor `restricted-case`와 source object `procedure-1`, raw document `sop-1`은 모두 `procurement` actor에게 보이게 했다.
2. 두 객체를 잇는 유일한 hop link만 `private-board` group·CONFIDENTIAL로 만들었다.
3. `procurement+private-board` author가 anchor에서 hops=1로 compile했다. 저장 scope 객체는 두 개였다.
4. link를 볼 수 없지만 두 객체·raw document를 볼 수 있고 RESTRICTED clearance인 `procurement` reviewer가 다음을 모두 성공했다.
   - `view_draft`
   - `publish`
   - `page`
   - `index` 1개
   - `export`
5. 같은 actor가 같은 query를 실행하면 link를 따라갈 수 없어 `query.pages == ()`였다.

직접 실행 표식은 `LINK_ACL_COUNTEREXAMPLE_CONFIRMED`; 관찰값은 `page=acme.review-procedure`, `index=1`, `export=acme.review-procedure`, `query_pages=0`이었다. mock이 없는 실제 `Store`·`WikiService` 경로다. draft/page의 저장 query와 두 scope object를 함께 보면 actor에게 숨긴 관계의 존재도 추론할 수 있고, 관계를 재현할 수 없는 reviewer가 그 관계로 검색된 초안을 승인하게 된다.

**수정·회귀 조건**

- 공통 helper에서 저장 page/draft의 query로 현재 actor의 `scope_ids`를 다시 계산하고, 저장된 `scope_object_bindings` 전체가 현재 actor가 재현한 scope 안에 있을 때만 proposer/reviewer/draft/page/index/lint/export를 허용한다. query의 기존 조건과 같은 fail-closed 경계를 사용한다.
- actor가 객체는 모두 볼 수 있지만 유일한 hop link만 볼 수 없는 위 반례를 회귀 테스트로 고정한다. reviewer의 draft 열람과 publish, reader의 page/index/export, manager lint가 모두 숨겨지고 query와 일치해야 한다.
- 구현이 특정 link 자체의 과거·현재 결속을 보장하려면 link snapshot/hash binding을 추가할 수 있다. 최소 조건은 현재 actor가 저장 scope를 실제 traversal 정책으로 재현할 수 있다는 것이다.
- 수정 뒤 전체 회귀, Ruff, basedpyright, no-excuse, isolated wheel smoke, source manifest 전후 일치와 독립 재검증을 다시 수행한다.

### B1 / R2: 기존 head 접근, 복구, 비노출

- compile tx1과 tx2는 각각 `wiki_compile_flow.py:54`, `:96`에서 같은 `require_revision`을 호출한다. 이 함수는 `wiki_compile_policy.py:85-97`에서 revision 비교 전에 `require_existing_head_access`를 거친다.
- `wiki_head_policy.py:36-61`은 scrubbed head를 404로 닫고, 저장 page purpose·page classification·server floor, 과거 source/object ACL snapshot과 남아 있는 현재 ACL을 모두 요구한다. stale head도 이 자격을 가진 manager에게만 revision을 노출한다.
- publish는 `wiki_publish_flow.py:47-60`에서 proposer와 reviewer 양쪽의 기존 head 자격을 hash 비교와 CAS보다 먼저 다시 확인한다.
- `test_wiki_audit_boundaries.py:58-96`은 실제 restricted head를 먼저 게시하고 낮은 권한 actor가 revision 0·1·99를 추측하는 경로, 낮은 권한 reviewer의 overwrite 경로를 호출한다. 모든 compile은 모델 callback 0회인 동일 404이고 원래 version이 유지된다.
- 별도 인라인 반례에서 tx1 뒤 compiler callback 중 원천 ACL을 회수했다. tx2는 `wiki_page_not_found` 404로 닫혔고 새 draft 수는 0, head version은 원래 값이었다: `B1_TX2_HEAD_RECHECK_PASSED`.
- `test_wiki_audit_boundaries.py:98-131`은 stale head의 마지막 revision과 `head_stale` reason이 자격 있는 manager lint에만 보이고 그 revision으로 복구 compile되는 실제 DB 경로를 실행한다.
- 미사용 ID 생성과 비가시 ID 404 차이로 남는 같은 tenant ID 사용 추론은 `LLM_WIKI_GUIDE.md:116`, `V03_GUIDE.md:69`, `SECURITY_MODEL.md:61-63`에 제한과 서버 할당 ID 대책으로 명시되어 있다.

### 기존 B2 / R1 직접 반례: anchor·hop 객체 결속과 객체 현재 권한

- `wiki_object_policy.py:10-41`은 모델 입력 citation 객체와 `scope_ids`가 만든 anchor·hop 전체 집합을 `WikiObjectBinding`에 넣고 object JSON hash, ACL hash, ACL snapshot을 reviewed payload에 결속한다. 100개 초과는 typed 422 `wiki_object_scope_limit`이다.
- publish proposer·reviewer(`wiki_publish_flow.py:92-117`), draft/page read와 index(`wiki_reads.py:49-65`, `:188-205`), lint(`wiki_query_export.py:94-115`), export(`wiki_query_export.py:130-163`)가 같은 현재 object 검사를 공유한다. query selection은 caller traversal scope도 별도로 요구한다(`wiki_query_policy.py:24-25`). 이 차이가 위 새 blocker를 만들었다.
- `test_wiki_scope_bindings.py:74-188`은 비공개 anchor와 hop 객체가 결속되는지, anchor를 못 보는 reviewer가 404인지, read·index·query가 숨기는지, 객체 hash/ACL 변화가 page를 숨기고 `object_changed` lint를 만드는지, 101개가 422인지 실제 SQLite 경로로 실행한다.
- 별도 인라인 반례에서 anchor 객체 자체를 볼 수 없는 reader의 index는 빈 목록, page/export는 동일 404, 좁은 query는 page 0개였고, 낮은 권한 manager의 lint도 빈 목록이었다: `B2_ALL_READ_SURFACES_PASSED`. 이 증거는 객체 ACL 반례만 닫으며 link-only ACL 반례를 닫지 않는다.

### R3: HUMAN 작성자와 사람 결속

- `Principal`은 SERVICE에 `person_id`를 허용하지 않고 SERVICE의 `effective_person_id`가 항상 `None`이다. `wiki_policy.py:37-46`은 compile에 non-null effective person을 요구하고 reviewer는 HUMAN·다른 subject·다른 person이어야 한다.
- `test_wiki_audit_boundaries.py:133-160`은 SERVICE 작성 거부와 subject 재할당 뒤 exact replay의 `wiki_proposer_identity_changed`를 실행한다. publish는 현재 proposer kind/person/권한도 다시 검사한다.
- 문서는 현재 SERVICE 위임 작성을 지원하지 않고 HUMAN 작성자가 필요하다고 `SECURITY_MODEL.md:132`, `OPERATIONS.md:183`에 명시한다.

### R4: 생성 경로 provenance

- `wiki_compiler.py:25-32`, `:46-67`은 model draft에만 `{mode, endpoint_host, model, provider_settings_sha256}`를 만든다. offline이면 route가 없고, model draft면 route가 없을 수 없다는 계약을 `wiki_contracts.py`가 검증한다.
- route는 `WikiDraftPayload` canonical JSON과 `compiler_mode`로 계산한 review hash에 들어가고, `wiki_publish_flow.py:165`의 page와 `wiki_query_export.py:142`의 export manifest까지 그대로 전파된다.
- `test_wiki_core_contracts.py:59-92`, `test_wiki_model_wire.py:34-107`, `test_wiki_core_visibility.py:99-130`이 route 필수성, 실제 loopback HTTP protocol, private/cloud transport fake, draft→page→export 동일성을 검증한다.
- `LLM_WIKI_GUIDE.md:121`과 `SECURITY_MODEL.md:103-107`은 LOCAL의 loopback 검사가 첫 hop일 뿐 실제 추론 위치·무반출 증명이 아니며 remote forwarding, cloud model, proxy, tunnel을 별도 통제해야 한다고 명시한다.

### R5: 파생물 재반입과 현재 raw 적격성

- `evidence_policy.py:24-39`은 BOM·앞 공백을 정규화하고 marker 본문 및 CLI JSON wrapper의 최상위 `text` marker를 차단한다.
- `test_wiki_source_roles.py:30-129`은 derived role 격리, plain/BOM/wrapper/wrapper+BOM marker, 잘못된 role registry, unmarked JSON의 한계를 분리해 검증한다.
- 별도 인라인 반례에서 published page와 미게시 draft의 원천 role을 raw에서 derived로 바꿨다. index는 빈 목록, page/export는 404, lint는 `source_changed`, 기존 draft publish는 404였다: `R5_CURRENT_RAW_ELIGIBILITY_PASSED`.
- `LLM_WIKI_GUIDE.md:198-213`, `SECURITY_MODEL.md:134-136`, `V03_GUIDE.md:69-71`, `UPGRADE_GUIDE.md:161-165`은 role 변경 전파, legacy `contract_id=None`·registry 없음의 raw 호환 기본값, marker 제거·frontmatter·metadata 위조 한계를 실제 구현과 같은 범위로 적는다.

## 실행 증거

| 검사 | 결과 | TQE capsule / raw SHA-256 |
|---|---|---|
| B1/B2/R3/R4/R5 선택 테스트 + branch coverage | 34 passed | `20261006-102302738-01d70b2a` / `4064ce884184874dd8418d320f646b8a4b9ebc58f7d61ab12a8ddfc0ad3b05ff` |
| 전체 pytest | 417 passed | `20261006-102338894-cf31d0bb` / `9a4ffc75683cc072f501a150c8fa627df3ad5b7d4312adca34b314fb11e81d00` |
| Ruff lint | `All checks passed!` | `20261006-102531580-f64a8c9c` / `af352a86840ad0af3d37ea0d9197f868363a6dac6b1c2ef5d2722f6b41d2d9af` |
| Ruff format | 204 files already formatted | `20261006-102556358-f8271c6d` / `439793a8778cd9de01e296202ff0117c8564555df8e98c1d1148d97ecbb6d844` |
| basedpyright | 0 errors, 0 warnings, 0 notes | `20261006-102531595-6f77afbb` / `6851c16b34e045435cd01974bb0fdc7298759457a68f2f6739f1b742245a5341` |
| no-excuse 47-file manifest | `no violations in 47 file(s)` | 직접 bounded 실행, exit 0 |
| 격리 wheel import + installed CLI help | PASS, wheel SHA `b58a67004bf3cf06a9d98f5f0ddde7dd3aa750b981f23436ba2877ae578a0521` | 직접 bounded 실행, exit 0 |

모든 성공 capsule은 `manual_inspection_required=false`, `auto_evidence.hash_verified=true`, `all_detected_risk_lines_captured=true`였다. wheel 설치의 TQE 중첩 PowerShell 캡처는 uv 스트림을 CLIXML로 두 번 오인해 증거로 쓰지 않았고, 출력이 세 표식과 SHA뿐인 직접 실행으로 다시 검증했다. 실패한 캡처를 성공 근거로 사용하지 않았다.

## 테스트 품질 판단

- B1/B2 테스트는 함수 return을 mock한 단위 테스트가 아니다. 실제 SQLite head·draft·document/object record를 만들고 compile/publish/read/query/lint/export public service 경로를 호출한다.
- branch coverage에서 숨은 head 반례가 `require_existing_head_access`의 source/object 검사까지 실행됐고, tx2 ACL 회수 반례는 두 번째 transaction 전에 상태를 바꿔 취약했던 TOCTOU 분기를 직접 통과했다.
- route 검증은 loopback HTTP 서버와 private/cloud wire transport를 사용한다. 이는 protocol 실행 증거이며 실제 모델 품질 증거는 아니다.
- marker와 role 테스트는 알려진 형식 차단과 등록 role 격리를 검증한다. 실제 기원 인증이나 임의 재작성 방어를 주장하지 않는다.

## WATCH — 판정 범위 밖

- 기업 IdP·connector, 실제 hosted/local LLM, KMS, HA/RLS, WAL·백업·다운로드 export의 물리 삭제, 외부 감사 서명, 의미 품질, KPI·ROI는 이 로컬 판정 범위 밖이다.
- review hash와 body/citation 문자열 검증은 byte 결속과 CAS 증거다. reviewer가 실제로 읽었는지, 문장이 의미적으로 맞는지, 출처가 진짜인지, 모델 품질이 충분한지는 증명하지 않는다.
- 먼저 hop link ACL blocker를 수정하고 새 고정 입력과 독립 실행 증거를 만들어야 한다. 그 뒤 실제 `claude-opus-5-5` max 정적 재감사를 받아야 한다. 현재 상태는 `NEEDS_FIX`다.
