# AX Ontology Starter v0.1 독립 구현 감사

도구 없이 공급된 소스와 테스트를 정적으로 검토했습니다. 보고된 실행 결과(pytest 59, basedpyright, Ruff, build, 평가 6건)는 다시 실행하지 않았습니다. 공급본의 테스트 함수 수가 파라미터 포함 59개로 보고 수치와 일치하는 것만 확인했습니다.

## 1. VERDICT: NEEDS_FIX

FAIL 수준의 결함은 찾지 못했습니다. 테넌트 격리 우회, 인증 우회, 숨은 자료가 응답이나 프롬프트로 새는 경로는 없었습니다. 다만 문서화된 통제와 실제 동작이 어긋나는 결함 3건이 있어, 수정과 회귀 테스트 뒤 다시 확인해야 합니다.

선언 범위 안에서 정상으로 판단한 경계는 다음과 같습니다.

- **검색**
  - 테넌트·그룹·등급·목적·READ를 점수화 전에 적용합니다.
  - 숨은 객체와 없는 객체는 같은 404, 같은 본문을 받습니다.
  - 그래프는 링크 자체 권한과 양 끝점 가시성을 모두 만족할 때만 확장합니다.
  - 근거 문서는 자체 권한·목적·유효기간을 통과하고, 연결 객체 전부가 범위 안에 있어야 합니다.
- **팩 검증**: 적재 단계에서 다음을 거부합니다.
  - 알 수 없는 필드
  - 타입·속성보다 낮은 객체 등급, 연결 객체보다 낮은 문서 등급
  - 교차 테넌트 링크·문서
  - `set_status` 외의 처리기
- **실행**
  - payload 전 필드(테넌트·제안자·전이·버전·근거 해시·목적·팩 해시·만료)가 해시에 묶이고, 적재할 때마다 재해시됩니다.
  - 자기 승인 금지와 30분 만료가 적용됩니다.
  - 실행 시 실행자·승인자·제안자의 최신 권한을 다시 조회하고, 버전과 이전 상태를 검사합니다.
  - `BEGIN IMMEDIATE` 한 트랜잭션에서 상태·제안·감사가 함께 커밋되거나 함께 롤백됩니다.
  - `(tenant, proposer, request_key)`는 유일하고, 같은 키에 다른 payload가 오면 거부합니다.
- **반출**
  - offline은 네트워크를 호출하지 않습니다.
  - 서버 하한·질의 등급·인용 등급의 최댓값을 모드 상한과 비교하고, 분류 거부 시 클라이언트 생성 전에 차단합니다.
  - 게이트웨이 키는 경로 검사를 통과한 뒤에만 읽습니다.
  - HTTPS, 정확한 허용 호스트, `egress_approved`가 필요합니다. `trust_env=False`, 리다이렉트 비추종, 응답 64KB 상한도 적용됩니다.
  - 모델 출력은 엄격 스키마와 인용 substring으로 검사합니다.
- **API**
  - 요청마다 신원 파일을 다시 읽습니다.
  - 본문의 역할 필드는 422로 거부합니다.
  - 헤더 값과 무관하게 실제 수신량 기준 128KB로 제한합니다.
  - 검증 오류 내용을 응답에 되돌리지 않고, 로그에는 사유 코드만 남깁니다.

## 2. 차단 결함

### B1 [중간] 런타임이 README의 DB 경로를 무시하고 보호 폴더 밖에 상태를 만듦

- **위치**: `README.md:51`은 `AX_DB_FILE`을 설정합니다. 그런데 `src/ax_starter/runtime.py:26`은 `AX_DATABASE`만 읽고, 없으면 작업 폴더 기준 `.runtime/state.db`를 씁니다. 상위 폴더는 `src/ax_starter/store.py:18`이 만듭니다.
- **트리거**: README 35–52행대로 `ax init .runtime\company-pilot`을 실행한 뒤, 안내된 환경변수로 uvicorn을 기동합니다.
- **결과**
  - 상태·제안·감사 체인이 `init`이 ACL로 잠근 `company-pilot` 밖, 상속 ACL을 받는 `.runtime\state.db`에 생깁니다.
  - 같은 작업 폴더에서 띄운 모든 파일럿이 이 파일 하나를 공유합니다.
  - 다른 도메인 파일럿은 `pack_changed_migration_required`로 기동이 실패합니다. 사용자가 엉뚱한 DB를 지우도록 유도하는 셈입니다.
  - 같은 도메인 파일럿 둘은 팩 해시가 같아 그대로 섞입니다. 주체명(`acme`/`operator`·`reviewer`)도 같으므로, 파일럿 A에서 만든 제안을 파일럿 B의 토큰으로 승인·실행할 수 있습니다.
- **최소 수정**: `runtime.py`가 `AX_DB_FILE`을 읽게 합니다. 미설정이면 상대 경로 기본값을 쓰지 말고 `runtime_configuration_required`(503)로 기동을 거부합니다.
- **회귀 테스트**: 현재 `load_app`을 다루는 테스트가 없습니다.
  - `monkeypatch.chdir(tmp_path)`로 이동하고 세 환경변수를 설정한 뒤 `load_app()`을 호출합니다. `tmp_path/pilot/state.db`가 있고 `tmp_path/.runtime/state.db`는 없어야 합니다.
  - `AX_DB_FILE`을 지우면 `AXError("runtime_configuration_required")`가 나야 합니다.

### B2 [중간] 승인자가 승인 해시의 원문을 볼 수 없음

- **위치**
  - `src/ax_starter/action_contracts.py:54`: `Simulation`
  - `src/ax_starter/actions.py:106`: `simulate`
  - `src/ax_starter/api.py:113`: 제안 조회 엔드포인트가 없음
  - 관련 문서: `docs/SECURITY_MODEL.md:24`
- **트리거**: operator가 제안한 뒤 reviewer가 `GET /v1/actions/{id}/simulate`를 호출합니다.
- **결과**
  - 응답은 `before`, `after`, `reviewed_payload_hash`뿐입니다.
  - 문서는 승인자가 제안자·목적·만료·`evidence_ids`/`evidence_hashes`를 검토한다고 적었지만, 이를 받을 API가 없습니다.
  - 그래서 `reviewed_payload_hash`는 서버가 준 값을 그대로 되돌려 보내는 토큰이 됩니다.
  - 서버 측 결속(저장 payload 재해시, `approval_hash == payload_hash`)은 정상입니다. 하지만 "사람이 검토한 payload에 승인이 묶인다"는 계약은 성립하지 않습니다.
  - 또 `before`는 `expected_version` 시점이 아니라 현재 엔티티이고, `will_execute`는 항상 `False`라 판단을 오도할 수 있습니다.
- **최소 수정**: `Simulation`에 `payload: ActionPayload`와 `state: ProposalState`를 추가합니다. `stale` 표시도 추가하면 좋습니다.
  - simulate는 객체 READ와 호출자 기준 근거 재검사를 통과해야 응답하므로, 새로 노출되는 정보는 없습니다.
  - B3를 고칠 때도 simulate의 근거 검사는 유지해야 합니다.
- **회귀 테스트**
  - reviewer의 simulate 결과가 다음을 만족해야 합니다.
    - `content_hash(sim.payload.model_dump_json()) == sim.reviewed_payload_hash`
    - `sim.payload.proposer == "operator"`
    - `sim.payload.evidence_ids == ("sop-1",)`
  - HTTP 경로로도 같은 내용을 검증합니다.
  - outsider는 없는 ID와 같은 404를 받아야 합니다.

### B3 [중간] 근거 재검증이 되돌리기와 멱등 재실행까지 막음

- **위치**
  - `src/ax_starter/actions.py:79`: `_authorized`가 조건 없이 `verify_evidence`를 호출
  - `src/ax_starter/actions.py:118`: EXECUTED 조기 반환이 그 뒤에 있음
  - `src/ax_starter/actions.py:171`: rollback도 같은 경로를 탐
  - 관련 문서: `docs/SECURITY_MODEL.md:25`, `docs/ARCHITECTURE.md:73`
- **트리거**: `sop-1.valid_until = T+20분`인 팩을 씁니다. T에 제안하고, T+1분에 승인하고, T+2분에 실행합니다. 그 뒤 T+25분에 `rollback`이나 `execute`를 다시 호출합니다.
- **결과**
  - 둘 다 403 `evidence_changed_or_revoked`를 받습니다.
  - 문서의 되돌리기 조건(24시간 이내, 더 최신 변경 없음)에 없는 조건 때문에 유일한 되돌리기 경로가 막힙니다.
  - 응답 유실 후 재시도한 클라이언트는 이미 커밋된 실행을 실패로 보고받습니다. "같은 제안의 재실행은 기존 영수증"이라는 문서와 어긋납니다.
  - 롤백 주체의 문서 그룹만 바뀐 경우에도 같은 일이 생깁니다.
- **최소 수정**: `verify_evidence`를 `_authorized`에서 뺍니다. 그리고 다음 세 곳에서만 호출합니다.
  - `approve`
  - `simulate`
  - `execute`의 EXECUTED 조기 반환 이후 경로(APPROVED → EXECUTED)

  rollback과 재실행 응답에는 현재 객체 권한과 operation 검사만 남깁니다.
- **회귀 테스트**
  - 양성: 위 시나리오에서 rollback이 성공하고, status가 `submitted`로 돌아오고, 감사 4건이 intact해야 합니다. 재실행 결과는 첫 영수증과 같아야 합니다.
  - 음성: 근거 만료 뒤의 approve와 APPROVED 상태의 execute는 계속 403이어야 합니다.

## 3. 운영 제한과 비차단 개선

### 3-1. 그대로 유지·명시해야 할 제한

- **범위**
  - 단일 운영자 장비용 합성 참조 런타임입니다. 인터넷 노출, 실데이터, 운영 준비를 주장하지 않습니다.
  - 실제 쓰기는 로컬 검토 상태 하나뿐입니다. `automate_candidate`는 승인 요구를 해제하지 않습니다.
- **신원**
  - 정적 토큰 파일을 씁니다. OIDC, MFA, 세션 만료는 없습니다.
  - `demo-credentials.json`의 평문 토큰은 합성 데모 전용입니다.
- **저장**
  - SQLite는 암호화와 RLS가 없습니다.
  - 해시 체인은 부분 변조만 감지하고, 전체 재작성이나 꼬리 삭제는 잡지 못합니다(`externally_anchored=false`).
  - 제안의 `state`·`approver`·`approval_hash`는 payload 해시 밖에 있으므로 DB 신뢰가 전제입니다.
- **반출**
  - 패턴 DLP는 최선 노력 수준입니다. 허용 호스트는 게이트웨이의 진위를 증명하지 않으며, DNS·프록시·방화벽 통제는 없습니다.
  - local 모드는 loopback 포트를 연 프로세스를 신뢰하므로, 여러 사용자가 쓰는 장비에는 맞지 않습니다.
- **생성**
  - 인용 substring 검사는 의미상 근거성을 증명하지 않습니다. 초안은 항상 사람이 검토해야 합니다.
  - 실제 Ollama 모델과 게이트웨이 추론은 시험하지 않았습니다.
- **부채널**
  - 시간·건수 비간섭은 증명되지 않았습니다.
  - 감사 검증의 테넌트 전체 이벤트 수는, 낮은 등급 감사자에게 제한 객체의 작업 수를 알려 줄 수 있습니다. 같은 범주의 제한으로 명시하길 권합니다.
- **미구현 항목**: 질의·거부·반출 시도의 영구 감사, 필드 단위 마스킹, 마이그레이션(팩이 바뀌면 기동 중단), 속도·동시성 제한이 없습니다. 검색은 키워드 방식뿐입니다.

### 3-2. 비차단 결함 (구체 버그)

1. **`--as-of`가 항상 실패** (`src/ax_starter/cli.py:89`)
   - 원인: Typer 기본 날짜 형식에 `%z`가 없습니다. 시간대를 넣으면 파싱 오류, 빼면 `TIMEZONE_REQUIRED`가 납니다.
   - 수정: `typer.Option(formats=["%Y-%m-%dT%H:%M:%S%z"])`
   - 테스트: `--as-of 2026-10-01T00:00:00+00:00`이 exit 0이어야 합니다.
2. **2028년부터 데모와 테스트가 깨짐** (`src/ax_starter/demo.py:218`, `src/ax_starter/demo_run.py:32`, API 실시간 시계)
   - 원인: 근거 유효기간이 2028-01-01로 고정되어 있습니다.
   - 결과: 2028-01-01 00:00 UTC부터 `ax demo`가 `ProposeRequest(evidence_ids=())` 검증 오류로 비정상 종료합니다. 데모·API·실소켓 테스트 8개도 실패합니다.
   - 수정: `run_demo(now=...)`, `create_app(..., clock=...)`처럼 시계를 주입합니다.
   - 테스트: 2028-06-01 시계로 데모가 `passed`여야 합니다.
3. **DLP 패턴 누락** (`src/ax_starter/providers.py:66`)
   - GitHub 토큰의 실제 접두사는 `ghp_`/`gho_`(밑줄)인데, 패턴은 `-`라 잡지 못합니다.
   - `\b`가 한글과 숫자 사이에 경계를 만들지 않아 `주민번호900101-1234567`이 통과합니다.
   - 외국인 번호(7번째 자리 5–8)와 하이픈 없는 형태도 놓칩니다.
   - 수정: `gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}`, `(?<!\d)\d{6}-?[1-8]\d{6}(?!\d)`로 바꾸고, 키 패턴의 경계도 lookaround로 바꿉니다.
   - 테스트: 위 문자열들을 parametrize해 `sensitive_content_egress_denied`와 네트워크 시도 0을 확인합니다.
4. **제안 ID 존재 오라클** (`src/ax_starter/actions.py:71`)
   - 같은 테넌트에서 객체를 못 보는 사용자는 실제 제안 ID에 403, 없는 ID에 404를 받습니다. ID를 알면 존재 여부를 알 수 있습니다.
   - 수정: `visible` 검사가 실패하면 `proposal_not_found` 404로 통일합니다.
   - 테스트: 다른 그룹 사용자에게 실제 ID와 임의 UUID의 응답이 같아야 합니다.
5. **승인 재시도가 409** (`src/ax_starter/actions.py:93`): 승인 응답을 놓친 같은 승인자가 다시 요청하면 409를 받습니다. 같은 승인자·같은 해시면 기존 결과를 반환하게 합니다.
6. **CLI가 오류 사유를 버림** (`src/ax_starter/client_cli.py:49`): 모든 4xx가 `api_request_failed`로 바뀌어 `self_approval_forbidden` 같은 사유가 사라집니다. 서버의 `error` 코드를 출력해야 합니다.
7. **잠금 대기 초과가 일반 500** (`src/ax_starter/store.py:49`): 5초를 넘기면 `sqlite3.OperationalError`가 일반 500으로 나갑니다. `state_busy` 503으로 매핑합니다.
8. **그래프 절단이 조용함** (`src/ax_starter/retrieval.py:82`)
   - 이미 범위에 있는 노드가 50칸을 차지하고, 사전순 절단이 아무 표시 없이 일어납니다.
   - `MAX_SCOPE_NODES=200`은 도달할 수 없습니다. 실제 최대는 101입니다.
   - 이웃이 50개를 넘으면, 주체마다 접근 집합이 달라 승인자 범위에서 근거 객체가 밀려날 수 있습니다. 그러면 거짓 `evidence_changed_or_revoked`가 납니다.
   - 수정: 새 노드만 절단하고, `truncated`를 표시하거나 명시적으로 거부합니다.
9. **평가 주체가 모호함** (`src/ax_starter/evaluation.py:49`): subject만으로 주체를 찾으므로, 두 테넌트에 같은 subject가 있으면 첫 항목으로 평가합니다. 케이스에 tenant를 추가하거나 모호하면 거부합니다.
10. **운영 Host 목록에 `testserver`** (`src/ax_starter/api.py:56`)
    - 허용 목록을 인자로 받고, 테스트에서만 `testserver`를 추가합니다.
    - `[::1]`은 Starlette의 Host 포트 분리 방식 때문에 일치하지 않을 가능성이 높습니다. 다만 실패 시 닫히는 쪽이라 보안 영향은 없습니다.
11. **init 경합** (`src/ax_starter/bootstrap.py:127`)
    - `exists()` 확인 뒤 `mkdir(exist_ok=True)`를 씁니다. 그 사이 다른 주체가 폴더를 만들면, `/grant:r`는 그 주체의 명시 ACE를 지우지 못합니다.
    - 수정: `exist_ok=False`를 쓰고, 계정은 환경변수 기반 `getpass.getuser()` 대신 현재 토큰의 SID로 지정합니다.

### 3-3. 개선 아이디어

- **외부 전송 최소화** (`src/ax_starter/generation.py:79`): 게이트웨이로는 `document_id`와 `quote`만 보내거나, DLP 검사 대상을 `title`·`source_uri`·`object_ids`까지 넓힙니다.
- **범위 지정 질의의 등급 반영** (`src/ax_starter/providers.py:85`)
  - `object_id`로 범위를 지정한 질의에서, 기준 객체와 통과한 링크의 등급을 반출 분류에 넣습니다.
  - 지금은 문서보다 민감한 객체에 대한 질문도, 사용자 선언 등급과 서버 하한만으로 클라우드 경로가 열릴 수 있습니다. 내보낸 cloud 예제의 하한은 INTERNAL입니다.
- **인용 최소 길이·중복 제거** (`src/ax_starter/generation.py:54`): 지금은 한 글자 인용으로도 계약을 통과합니다.
- **제안자 근거 재검사** (`src/ax_starter/actions.py:140`): 실행 시 제안자의 근거 가시성도 다시 확인합니다.
- **압축 응답 증폭** (`src/ax_starter/generation.py:126`): 모델 호출에 `Accept-Encoding: identity`를 쓰거나 원시 바이트 상한을 둡니다. 현재 64KB 검사는 압축 해제 뒤에 이루어져 청크 단위 증폭을 막지 못합니다.
- **공급자 스키마 호환**: strict `json_schema`의 `minLength`/`maxLength`/`pattern`이나 Ollama `format`의 `\w` 패턴은 공급자에 따라 거부되거나 무시될 수 있습니다. 회사 환경의 실제 연결 시험 항목에 넣어야 합니다.
- **`httpx2==2.13.1` 출처 확인**
  - 반출 통제(`trust_env`, 리다이렉트, TLS 검증)가 이 라이브러리 동작에 의존하는데, 공식 `httpx`와 배포명이 다릅니다.
  - 로컬 `uv.lock`의 출처·해시와 유지 주체를 확인하길 권합니다. 이번 감사에서는 확인하지 않았습니다.
- **`process_metrics` 성능**: 사례 수 × 이벤트 수만큼 반복하므로 이벤트 1만 건 근처에서 느려집니다. CLI 전용입니다.

## 4. 승인 범위

- 이 판정은 위에 SHA256이 표기된 공급 스냅샷과 선언 범위에만 적용됩니다. 선언 범위는 합성 데이터, 로컬 참조 런타임, 로컬 SQLite 검토 상태 변경 하나입니다.
- 판정이 NEEDS_FIX이므로 현재 스냅샷을 승인하지 않습니다. B1–B3 수정본이 나오면 바뀐 파일과 회귀 테스트를 다시 검토해야 합니다.
- 다음 파일은 공급되지 않아 검토하지 않았습니다.
  - `docs/OPERATIONS.md`, `docs/ADOPTION.md`, `docs/UPGRADE_GUIDE.md`, `docs/LEARNING_GUIDE.md`, `docs/VERIFICATION.md`, `docs/ENTERPRISE_PATTERNS.md`
  - `examples/`
  - `uv.lock`
- 이전 설계 호출의 승인과 점수는 사용하지 않았습니다. 이 판정은 운영 배포, 실데이터, 실제 모델 추론, 보안 인증에 대한 승인이 아닙니다.

IMPLEMENTATION_AUDIT_COMPLETE