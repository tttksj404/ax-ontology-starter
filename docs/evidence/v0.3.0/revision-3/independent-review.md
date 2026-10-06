# v0.3 revision-3 독립 검토

**VERDICT: PASS**

이 판정은 revision-3의 로컬 참조 구현, 테스트, 패키지 실행 증거와 문서 정합성에 대한 독립 검토 결과다. revision-2에서 재현한 숨은 hop link ACL 우회와 새로 추가한 관계 민감도 상승 반례는 현재 코드와 실제 실행에서 모두 차단됐다. 최종 Opus 5.5 max 정적 재감사는 이 판정 뒤의 별도 배포 게이트이며, 아직 이 보고서의 PASS에 포함하지 않는다.

## 고정 범위와 무결성

- 검사 소스 범위는 revision-3 `tested-source-manifest.json`에 열거된 `pyproject.toml`, `uv.lock`, 검사 스크립트 2개, `src/ax_starter/**/*.py` 70개, `tests/**/*.py` 75개로 총 149개다.
- aggregate 알고리즘은 정렬한 각 `path NUL file_sha256 NUL bytes` 레코드를 LF로 이어 UTF-8 바이트의 SHA-256을 계산했다.
- 독립 검증 전 source aggregate SHA-256: `90ed16b3908e3056090c9670f94b0bb42b5e0dfd5eaf2fb660ff0a9cdaea5b6a`.
- 독립 검증 후 source aggregate SHA-256: 아래 최종 무결성 검사와 같이 동일하다.
- `tested-source-manifest.json`: 149개, SHA-256 `a82dab5666b1167e0f05bcd57853646823f42c4e065710bcd8696c4f484621d8`; path·bytes·SHA를 현재 파일에서 직접 재계산한 불일치 0개.
- 검토 문서 6개(`LLM_WIKI_GUIDE.md`, `SECURITY_MODEL.md`, `ARCHITECTURE.md`, `OPERATIONS.md`, `V03_VERIFICATION.md`, `WORK_PLAN_v0.3.md`)의 같은 방식 aggregate SHA-256은 검증 전 `f199b5c13fe68dfa91fc119f32b00258473aecd6bd61bbe164990fd6fa8bec17`이다. 독립 보고서 자체와 revision-3 실행 증거 파일은 source aggregate에서 제외했다.
- 역사 감사 원문 SHA-256은 `.omx/artifacts/wiki-final-audit-result.txt` = `2c7d161e56d123ebafdba75cd217ae1189c60e7560b757647c0a5261f5e3fbcd`, `.omx/artifacts/wiki-design-retry-result.txt` = `a5b2c515d37fc2a3c0fcadfc42e9cb592b9256927dfdf0dd34d90d212b6c8669`다. 그 판정은 입력별 역사 증거로 사용했고 현재 PASS로 대체 해석하지 않았다.

## revision-2 blocker 폐쇄

### 숨은 hop link ACL

`wiki_object_policy.py:49-75`와 `78-97`은 draft/page에 저장한 객체 집합만 검사하지 않고, 저장 query를 현재 actor로 다시 실행한다. `_require_query_scope`(`100-115`)는 `scope_ids`가 반환한 현재 허용 graph scope에 모든 저장 binding ID가 들어가는지 요구한다. `retrieval.py:69-91`의 traversal은 현재 link ACL을 적용한다. 이 검사는 compile replay(`wiki_compile_policy.py:72-76`), 기존 head 자격(`wiki_head_policy.py:58`), publish의 proposer/reviewer(`wiki_publish_flow.py:92-118`), draft read(`wiki_reads.py:49-61`), page/index/query/export 공통 투영(`wiki_reads.py:158-212`)에 연결된다.

실제 Store와 WikiService를 사용하고 mock을 쓰지 않은 revision-2 반례를 다시 실행했다. 두 endpoint 객체와 raw 문서는 low reviewer에게 보이지만 유일한 hop link만 보이지 않는 상태에서 `view_draft=404`, `publish=404`, `index=0`, `page=404`, `export=404`, `query=0`, `lint=0`을 확인했다. `tests/test_wiki_link_scope_acl.py:56-128`의 세 회귀도 같은 분기를 고정한다.

### 관계 민감도 상승

`context_sensitivity`(`retrieval.py:107-120`)는 현재 actor가 볼 수 있는 현재 scope 객체와 관계의 민감도를 계산한다. `wiki_object_policy.py:30`, `59`, `87`은 compile/current/access 경로 모두에 그 하한을 포함한다. 따라서 endpoint, link ID와 ACL을 유지한 채 link 분류만 INTERNAL에서 RESTRICTED로 높여도 기존 INTERNAL page는 보이지 않는다.

실제 반례 재실행 결과는 `index=0`, `page=404`, `export=404`, `query=0`, manager lint `object_changed`, 복구 compile 분류 `RESTRICTED`였다. `tests/test_wiki_link_scope_acl.py:131-175`가 이 흐름을 고정한다.

현재 정책은 같은 결속 객체 전체에 도달하는 다른 **현재 허용 경로**가 있으면 접근을 허용한다. 과거 link ID·type·정확한 traversal path의 snapshot 동일성은 attestation 대상이 아니다. 이는 요청된 정책이며 blocker로 판정하지 않았다.

## B1·B2와 R3–R5 재검토

| 항목 | 판정 | 현재 근거 |
|---|---|---|
| B1 existing/stale head 권한·overwrite | 폐쇄 | `wiki_head_policy.py:36-61`은 scrubbed head와 저장 page purpose/classification, server floor, 과거·현재 source/object ACL을 먼저 검사한다. `wiki_compile_flow.py:44-54,87-96`은 모델 호출 전후 transaction에서 head 자격·revision을 재검사하고, `wiki_publish_flow.py:31-60`은 proposer와 reviewer 모두 같은 head 자격을 요구한다. 숨은 head와 revision은 404로 투영된다. |
| B2 anchor·hop scope | 폐쇄 | `wiki_object_policy.py:15-46`은 answer object와 anchor/hop scope를 최대 100개로 결속한다. `49-115`는 객체 hash·ACL snapshot·현재 ACL과 저장 query의 현재 scope subset 및 현재 관계 분류를 모두 재검사한다. |
| R3 실제 사람·독립 검토 | 폐쇄 | `common.py:53-65`에서 service에는 effective person이 없고, `wiki_policy.py:37-67`은 작성자 person 결속과 HUMAN reviewer, 서로 다른 subject/effective person을 요구한다. replay와 publish는 저장 person을 현재 registry와 다시 대조한다(`wiki_compile_policy.py:30-34`, `wiki_policy.py:70-102`). |
| R4 generation route | 폐쇄 | `wiki_compiler.py:25-32,46-66`이 model draft에 mode·host·model·provider settings hash를 생성한다. `wiki_contracts.py:58-73,105-152,155-194`가 mode/route 일치를 강제하며 route는 canonical payload hash, page와 export manifest까지 전달된다. |
| R5 derived output 격리 | 폐쇄 | `knowledge_store.py:49-64`가 current pack마다 현재 contract binding과 `raw_source_allowed`를 다시 적용한다. `evidence_policy.py:13-39`는 registry derived role과 plain/BOM/JSON-wrapper known marker를 제외한다. role 변경과 marker 회귀는 `tests/test_wiki_source_roles.py`에서 실제 current-pack/read 경로로 검사된다. |

publish는 권한·현재 원천·객체·분류 검사를 review hash 비교보다 먼저 수행한다(`wiki_publish_flow.py:31-131`). 모델 호출 전후 source/object/head 재검사와 route 결속도 별개로 확인했다. 선택한 38개 회귀는 이 helper들의 취약 분기를 서비스 표면에서 통과하며, 단순 직렬화 mirror test에 머물지 않는다.

## 독립 실행 증거

| 검사 | 결과 | TQE capsule / raw SHA-256 |
|---|---|---|
| 링크 ACL·관계 분류 4개, branch coverage 포함 | `4 passed` | `20261006-104732213-c334d6dc` / `50b7125a32f5539468a2b25302df9a2b0a7b23a870453d1775645830e9caf8bf` |
| B1·B2·R3·R4·R5와 링크 회귀 6파일 | `38 passed in 1.77s` | `20261006-105144765-946d9656` / `7a76b7fb6877eb9a16625479f027049cb77038347296a9bd71093bf5848f246e` |
| 전체 pytest | `421 passed in 21.33s` | `20261006-105154988-fc064b19` / `51c4cda3329344d54f7e5bc2bb81f47f5b9af61711e6ef5273a6e5fdc61a6a87` |
| Ruff check + Ruff format + basedpyright | `All checks passed`, `145 files already formatted`, `0 errors, 0 warnings, 0 notes` | `20261006-105342109-4e773ae4` / `1ae2a6c0b8e95f407fe961ce5c2ccc8a9391b15f35b1896377616eb0935887ea` |

네 독립 capsule 모두 exit 0, 기대 marker 1개 이상, `manual_inspection_required=false`, raw hash 검증 성공, 감지 위험 줄 누락 0이었다.

부모 실행 증거의 `verification-index.json` SHA-256은 `972ed8966e867a2d91f0682504bfdf974464864bac6442e1ab73ff5308e8d7f6`다. 5개 capsule의 실제 `~/.codex/artifacts/tool-output/*.log`와 `.meta.json`, 전달 로그를 직접 다시 읽어 raw/meta SHA, exit code, 기대 marker, 수동 검사 flag와 전달 SHA가 모두 index와 일치함을 확인했다.

- `20261006-104610286-fe321887`: 421 tests, Ruff ALL, 145 format, basedpyright 0/0; raw SHA `23138ae40ae0da7785cbc21c8d703b8894df0282a731719cce8b2a8aea13126c`.
- `20261006-104610286-bdd1845c`: 새 wheel의 설치된 runtime 70개 byte 일치, 실제 subprocess CLI·loopback HTTP·재시작·Wiki source lifecycle과 세 synthetic domain demo; raw SHA `4d9199fa98d93de2456eb22df0ec5ee7f7cab770ceeb465bffa73414b5fb1d6b`. 전달 로그의 `NativeCommandError` 문자열은 PowerShell이 build progress stderr를 감싼 표기였고 같은 전체 로그에서 build/install 성공, 모든 성공 marker와 최종 exit 0을 직접 확인했다.
- `20261006-104610286-60e30073`: no-excuse 48개 위반 0; raw SHA `6cbf862052a00caaa3efad058e5756187fed43e85ec093c01a14692bbd9d0d85`.
- `20261006-104745107-091336d2`: 실제 v0.2 wheel DB를 새 v0.3 wheel로 연 cold compatibility 성공; raw SHA `b2f3b0219778098aa678c1bf2c9743fd4d25209e693c8d3fcaf19304175de734`.
- `20261006-105327358-aacdf334`: 문서 19개 local link 135개 성공; raw SHA `5f762a94d0e37e27006f037789468c3a991b5a268218766b15175ab5f47ea2fd`.

wheel/cold 실행은 이 독립 검토에서 다시 빌드하지 않고, 현재 149-file manifest와 결속된 부모 raw/meta를 재검증했다. 반면 취약 분기 38개, 전체 421개, Ruff·format·basedpyright와 두 실반례는 독립 실행했다.

## 문서 정합성

구현과 문서의 보장 범위가 일치한다. `LLM_WIKI_GUIDE.md:173`, `SECURITY_MODEL.md:132`, `ARCHITECTURE.md:150`, `OPERATIONS.md:208`, `WORK_PLAN_v0.3.md:25`, `V03_VERIFICATION.md:7`은 현재 query 재탐색, 관계 ACL 회수, 관계 민감도 상승, 대체 허용 경로, 과거 link 동일성 미증명을 구분한다. `V03_VERIFICATION.md`는 revision-2의 417개와 NEEDS_FIX를 역사 기록으로 보존하고 revision-3의 421개를 별도 증거로 결속한다.

## 최종 무결성 검사

- 독립 검증 후 source aggregate SHA-256: `90ed16b3908e3056090c9670f94b0bb42b5e0dfd5eaf2fb660ff0a9cdaea5b6a` — 전과 동일.
- 독립 검증 후 검토 문서 6개 aggregate SHA-256: `f199b5c13fe68dfa91fc119f32b00258473aecd6bd61bbe164990fd6fa8bec17` — 전과 동일.
- `tested-source-manifest.json` 재검증: 149개, mismatch 0.

## WATCH — PASS 범위 밖

- 같은 bound object ID 집합에 도달하는 현재 허용 대체 경로는 의도적으로 인정한다. 과거 link ID·type·정확한 path의 provenance, 자동 stale 기록과 재compile queue는 구현하지 않는다.
- marker 검사는 알려진 plain/BOM/JSON wrapper만 방어하며 작성자 metadata, arbitrary frontmatter나 알려지지 않은 포맷의 의미를 인증하지 않는다. 관리 원천은 registry에 role을 완전 등록해야 한다.
- `synthetic_only=true`, `live_validated=false`다. 기업 IdP·connector, 실제 hosted/local LLM 품질, KMS, HA/RLS, 부하, WAL·백업·다운로드 export의 물리 삭제, 외부 감사 서명, semantic entailment, 고객 성과와 ROI는 검증하지 않았다.
- 이 PASS는 최종 Opus 5.5 max 정적 재감사와 새 ZIP 생성 승인을 대신하지 않는다.
