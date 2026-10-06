# v0.2.0 독립 delta 검토

검토 시각: 2026-10-02 (Asia/Seoul)

## 판정

**PASS — 아래에 적은 delta 범위에서 열린 P0/P1을 재현하지 못했다.**

이 판정은 온보딩 핵심 정책 근거, 지식 상태 메타데이터 노출, tombstone ACL 보존과 legacy 결손 처리, snapshot 중복 ID 입력 경계에 한정한다. 실제 회사 배포, 기업 IdP·MFA, 현업 성과, 외부 원천 ACL 동기화, 외부 ERP 쓰기, 다중 인스턴스 운영, 운영 DB의 물리적 변조 방어 또는 외부 감사 anchor에 대한 판정이 아니다. 아래 해시 이후 소스가 바뀌면 이 판정은 다시 확인해야 한다.

기존 `independent-review.md`는 변경하지 않았다.

## 검토한 소스와 SHA-256

| 파일 | SHA-256 |
|---|---|
| `src/ax_starter/onboarding.py` | `c56bd551aed2267714b8e13b2a589f4dc6ae25cae560277f14996edb77fafefe` |
| `src/ax_starter/onboarding_contracts.py` | `b0223b946796c3d714faa05ef8aaf31ca697ab37821a86c07cf9af4294a42448` |
| `src/ax_starter/api.py` | `6034eb2449156af213a49d216d939154978deb75d578a999256ac723f8df3ae1` |
| `src/ax_starter/api_extensions.py` | `a07e6d45aa03a635fe1bbcb64ef0c100ddbf7ac2e9e0c1da4d63311cb235103e` |
| `src/ax_starter/v02_cli.py` | `696fb394c8fbe8bc6dbf24ef718d2ecc657f3aae4f39a5aa168d65b3a8d3dc75` |
| `src/ax_starter/local_input.py` | `229eb4ec645a7347074cc0149dc371cf0c43ecf55c8d77ec7efd48ed8f7760ae` |
| `src/ax_starter/knowledge.py` | `0837e577b0be563876d97d37a9b4987a7ce3dc2c7989b588c2b971ee92a9b094` |
| `src/ax_starter/knowledge_contracts.py` | `cbe6b3e10fbdd32056718bf4f7170f0b4e0f60952d72b2cd89fe90c9c61b6532` |
| `src/ax_starter/knowledge_binding.py` | `7822edef53f04ce1325d58491ad48dc47825c9d4b566bcbf402f0338a895acd8` |
| `src/ax_starter/knowledge_visibility.py` | `b13cb6ba9fb30f2d555f6fc05d0673c0fc23ca3dfc01a5f4b60208d008d7347f` |
| `src/ax_starter/knowledge_store.py` | `e13caad12615f645e473210f884a22c6de6f60de1173bf9f3e67829ce18fce6e` |
| `src/ax_starter/knowledge_schema.py` | `071974177fd02dd0b722d9de139c2a50532d0512514627aa5a44abc9d4f253a9` |
| `src/ax_starter/knowledge_mutations.py` | `6b70217dd40c35f8b587dc0c8a45dd611ad8790677e6a6d4366becfc36d460ce` |
| `src/ax_starter/policy.py` | `e7126f1716c842f5977b519eaa115af0d58cafef0194df2af94a48ec572a63bc` |

검증 입력 테스트의 SHA-256은 다음과 같다.

| 파일 | SHA-256 |
|---|---|
| `tests/test_onboarding.py` | `867b4c518aba55ffb6a6c47312bc05916fd4920b154a9da11cc0143f4ac56b76` |
| `tests/test_v02_cli.py` | `d9b7d147b4cc4a2251531225437cd4c8fdc7fed4a30201a8b0b9132973c70d36` |
| `tests/test_knowledge_state_visibility.py` | `33f9a508d680b9639e83f58aaf5bec9cb16637977ab8eef4442667b90a560840` |
| `tests/test_knowledge_snapshot_boundaries.py` | `a84f2836225826f7d00b72d5ed94f51ca28366993c41f23deb046d74f23354f9` |
| `tests/test_knowledge_acl_migration.py` | `77e1ca062351de991733c2bb94cf57bb65dadd886dca74b9dda42695a37ab121` |
| `tests/test_knowledge_integrity.py` | `9937d7d186869399b0091bd311e3be8efc3c9e2d7a83317a9f1f27c41519d660` |

## 관찰과 반례 판정

### 1. 온보딩 UNKNOWN 차단과 REPORTED 경계

- `region_policy`, `model_policy`, `tool_policy` 근거는 핵심 근거 집합에 포함된다(`onboarding.py:30-39`). `UNKNOWN`은 evidence gap으로 보존되고(`:70-93`), 핵심 gap이 있으면 `BLOCKED`가 된다(`:157-169`).
- 같은 필드의 `REPORTED`는 누락 근거로 계산하지 않는다. 그러나 모든 응답은 `assurance=self_reported_readiness`, `live_validated=false`, `security_certified=false`로 고정된다(`onboarding_contracts.py:139-149`). 이 결과에는 실행·출시·운영 승격 필드가 없다.
- HTTP는 인증된 principal에 `READ`를 요구한 뒤 같은 `assess_onboarding` 함수를 호출한다(`api_extensions.py:28-35`). CLI도 같은 함수를 호출하고 `BLOCKED`/`ON_HOLD`만 종료코드 2로 반환한다(`v02_cli.py:28-38`).
- 직접 HTTP·CLI 호출에서 세 근거를 모두 `UNKNOWN`으로 둔 입력은 `HTTP 200 / blocked / CLI 2`, 모두 `REPORTED`로 둔 입력은 `HTTP 200 / pilot_review / CLI 0`이었다. 두 응답 모두 자기신고·비현장검증·비보안인증 경계를 유지했다.
- 기존 테스트에는 `/v1/onboard` 전용 회귀가 없다. 이번 직접 호출로 현재 체인은 확인했지만, HTTP 경계의 장기 회귀 방지는 후속 테스트로 남는다. 현재 동작 결함은 재현되지 않았다.

### 2. 지식 상태 메타데이터의 ACL·계약 필터

- `KnowledgeService.state`는 `READ + MANAGE_KNOWLEDGE + AUDIT`를 요구하고, 트랜잭션 진입 뒤 credential과 현재 계약 registry를 다시 확인한다(`knowledge.py:76-93`).
- 문서 후보는 먼저 actor tenant로 제한된다(`knowledge_visibility.py:13-23`). 각 행은 현재 contract binding, 저장된 ACL snapshot의 `AUDIT` 가시성, managed 문서의 관리 가능한 현재 계약을 모두 통과해야 반환된다(`:54-80`). bootstrap 문서는 contract binding이 없으므로 실제 문서 ACL과 엄격한 bootstrap binding 규칙으로만 판단한다(`knowledge_binding.py:6-14`).
- source head는 actor가 관리할 수 있는 현재 계약의 source identifier만 반환한다(`knowledge_visibility.py:31-51`).
- 회귀에서 procurement steward는 `restricted-doc`과 private managed 문서의 ID·version·hash를 받지 않았고, 각 ACL을 가진 steward만 해당 메타를 받았다. 현재 계약 접근이 없는 source head도 숨겨졌다(`tests/test_knowledge_state_visibility.py:34-126`).

### 3. tombstone ACL snapshot과 legacy fail-closed

- schema v4는 내부 `access_json` 열을 만들고 bootstrap·본문 보유 legacy row의 검증 가능한 ACL을 채운다(`knowledge_schema.py:21-40`, `:54-60`, `:81-116`). 본문이 이미 제거된 legacy tombstone의 ACL은 추론하지 않는다.
- upsert와 ACL 변경은 현재 ACL snapshot을 저장하며, tombstone은 본문을 제거하면서 마지막 ACL snapshot을 유지한다(`knowledge_mutations.py:52-80`, `:123-140`).
- row read는 ACL JSON을 `Access`로 파싱하고 tenant·`access_sha256`을 대조한다. 본문이 있으면 ID, source version, tenant, content hash, ACL hash, ACL snapshot과의 일치도 확인하며 불일치는 `knowledge_integrity_failure`로 차단한다(`knowledge_store.py:115-157`).
- metadata 필터는 ACL snapshot이 없으면 행을 숨긴다(`knowledge_visibility.py:72-77`). 따라서 ACL을 복원할 수 없는 legacy tombstone은 공개되지 않는다. v3→v4 회귀는 active/bootstrap ACL backfill과 unknown tombstone 비노출을 함께 확인한다(`tests/test_knowledge_acl_migration.py:23-80`).

### 4. snapshot 중복 ID 입력 경계

- `SourceSnapshotInput`은 문서 ID의 exact duplicate를 모델 검증 단계에서 `duplicate_snapshot_document`로 거부한다(`knowledge_contracts.py:107-122`). 따라서 `mutation_batch_from_snapshot`과 DB 트랜잭션에 도달하지 않는다.
- FastAPI의 request validation handler는 이를 422 `{"error":"invalid_request"}`로 정규화한다(`api.py:130-132`). CLI는 공통 `read_input`에서 `ValidationError`를 `invalid_input_file`, 종료코드 1로 정규화한다(`local_input.py:67-75`, `v02_cli.py:67-69`).
- 회귀는 계약 오류 코드, API 422, `tenant_revision == 0`, CLI 오류 코드와 종료코드를 확인한다(`tests/test_knowledge_snapshot_boundaries.py:57-106`). 누락 문서를 삭제로 추론하지 않는 기존 snapshot 의미는 바뀌지 않았다.

## 독립 표적 검증

- 관련 회귀: **26 passed in 0.79s**
  - `tests/test_onboarding.py`
  - onboarding CLI 경계 2건
  - `tests/test_knowledge_state_visibility.py`
  - `tests/test_knowledge_snapshot_boundaries.py`
  - `tests/test_knowledge_acl_migration.py`
  - `tests/test_knowledge_integrity.py`
- TQE capsule: `20261002-114927424-a8b03143`
  - 원문 로그 SHA-256: `9a577677e6f13a5a5043e770f48627e2a31082f1525c8d8c83830520538b5538`
  - `manual_inspection_required=false`
  - `auto_evidence.hash_verified=true`
  - `all_detected_risk_lines_captured=true`
- Ruff: 위 delta 소스·테스트에서 `All checks passed!`
- basedpyright: **0 errors, 0 warnings, 0 notes**
  - TQE capsule: `20261002-114943150-0c7ea12e`
  - 원문 로그 SHA-256: `6851c16b34e045435cd01974bb0fdc7298759457a68f2f6739f1b742245a5341`

## 남은 명시적 경계

- `tenant_revision/state_hash`는 tenant aggregate이고, 허용된 source의 revision/hash도 source aggregate다. 문서 ID나 ACL hash는 필터링되지만 허용 범위의 변경 발생 여부는 드러난다. 이는 CAS용 상태 메타라는 현재 공개 계약의 일부다.
- `access_json` 원문은 canonical tenant state hash의 별도 필드가 아니다. 대신 canonical hash는 `access_sha256`을 포함하고, 읽을 때 snapshot을 그 해시와 대조한다. 신뢰된 운영자 filesystem 밖의 독립 anchor, 전체 DB 교체·동시 재작성 방어는 제공하지 않는다.
- ACL을 복원할 수 없는 legacy tombstone은 계속 숨겨진다. 자동 추론·복구를 하지 않는 것이 이 버전의 fail-closed 정책이다.
- snapshot 중복 판정은 exact ID 기준이다. 이 검토는 식별자의 Unicode 정규화 정책을 새로 정의하지 않는다.
- `REPORTED` 온보딩 결과의 CLI 성공 종료는 입력상 `pilot_review` 판정만 뜻한다. 실제 현장 통제, 보안 인증 또는 운영 배포 준비도를 뜻하지 않는다.
- 전체 suite, installed-wheel smoke와 후속 Opus delta 감사는 root 통합 검증 범위이며 이 문서의 표적 검증과 구분한다.
