# AX Ontology Starter v0.1 수정본 독립 재감사

공급된 수정본의 소스·테스트·문서·예제를 도구 없이 정적으로 검토했습니다. 이전 감사의 결론은 재사용하지 않고, B1–B3과 변경분을 현재 코드로 다시 추적했습니다. 보고된 실행 결과는 다시 실행하지 않았습니다(6절).

## 1. VERDICT: PASS

- 판정 대상은 위에 SHA-256이 표기된 공급 스냅샷과 선언 범위입니다. 선언 범위는 합성 데이터, 로컬 참조 런타임, 로컬 SQLite 검토 상태 변경 하나입니다.
- B1–B3은 코드 경로와 회귀 테스트 양쪽에서 해소됐습니다.
- 변경분에서 차단 수준의 보안·정확성 회귀를 찾지 못했습니다. **차단 결함: 없음.**
- 4절의 비차단 7건은 판정을 바꾸지 않습니다. 다만 N1(예외 출력에 토큰 노출)은 공개 배포 전에 고치길 권합니다. 수정은 한두 줄입니다.
- 이 판정은 운영 배포, 실데이터, 실제 모델 추론, 보안 인증에 대한 승인이 아닙니다.

## 2. 필수 결함 재확인

| 결함 | 수정 위치 | 확인한 동작 | 회귀 테스트 |
|---|---|---|---|
| B1 DB 경로 | `runtime.py:16-18`, `:27-28` | `AX_DB_FILE`이 없으면 `runtime_configuration_required`(503)로 기동을 거부합니다. `AX_DATABASE`와 상대 경로 기본값은 제거됐습니다. | `test_runtime.py:18`, `:34` |
| B2 검토 payload | `action_contracts.py:54-62`, `actions.py:110-125` | 적재 시 재해시로 검증된 동결 payload, `state`, `stale`, 현재 객체의 before/after를 반환합니다. `reviewed_payload_hash`는 그 payload의 해시입니다. | `test_review_contracts.py:32`, `:47`, `:120` |
| B3 만료 근거 | `actions.py:76-80`, `:130-131`, `:182-203` | 만료 검사는 PROPOSED/APPROVED에만 적용됩니다. EXECUTED 재실행은 근거 검사 전에 기존 영수증을 반환하고, rollback은 근거를 보지 않습니다. 새 승인·검토·효과는 `:94`, `:113`, `:138·151·163`에서 근거를 재검사합니다(simulate의 근거 검사도 유지). | `test_review_contracts.py:70`, `:93` |

객체 가시성과 operation 권한은 모든 경로에서 `_authorized`(`actions.py:71-73`)가 계속 검사합니다. 실행 시에는 현재 실행자·승인자·제안자의 권한과 근거를 모두 다시 확인합니다.

## 3. 변경분 회귀 점검: 차단 회귀 없음

- **동일 승인자 재시도** (`actions.py:92-93`)
  - 자기 승인·해시·권한·만료 검사를 모두 통과한 뒤에만 기존 승인을 반환하며, 상태와 감사는 바뀌지 않습니다.
  - 실행 시 승인자의 권한과 근거를 다시 보므로 우회 경로가 아닙니다.
- **숨은 제안 404** (`actions.py:59-72`)
  - 다른 테넌트 주체와 같은 테넌트의 비가시 주체 모두, 없는 ID와 같은 코드·상태를 받습니다.
  - 인증과 레지스트리 재조회 사이의 경합을 빼면, 남는 403은 객체를 이미 볼 수 있는 주체에게만 납니다.
- **그래프 한도** (`retrieval.py:83-88`)
  - 가시 링크와 가시 객체만 세므로, 숨은 자료가 거부 여부에 영향을 주지 않습니다.
  - 2 hop의 최대 범위는 101개라 전체 한도(100) 검사도 실제로 작동합니다.
- **분류 전파와 전송 최소화** (`retrieval.py:105-118`, `providers.py:76-85`)
  - DLP 검사 대상(`providers.py:111-114`)이 실제 전송 필드와 정확히 같습니다.
  - 경로·분류 검사가 게이트웨이 키 읽기(`generation.py:97`)보다 먼저 실행됩니다.
- **압축 응답 거부** (`generation.py:85`, `:134-135`): 본문을 읽기 전에 거부하며, 이 오류가 `model_backend_failed`로 덮이지 않습니다.
- **CLI 오류 사유 코드** (`client_cli.py:21-22`, `:57-64`): 응답 2 KB 상한과 `[a-z0-9_]` 패턴 때문에 터미널 제어문자를 주입할 수 없습니다.
- **나머지 변경**
  - DB 잠금 503(`store.py:58-61`), 운영 Host 분리(`api.py:41`), 평가 주체의 테넌트 결속(`evaluation.py:50-60`)은 의도대로 동작합니다.
  - init(`bootstrap.py:140-146`)은 배타적 mkdir 직후 ACL부터 적용합니다. ACL이 실패하면 자격증명을 만들거나 쓰기 전에 중단합니다.

## 4. 비차단 결함

### N1 [낮음] 예기치 않은 예외의 traceback에 토큰이 평문으로 출력될 수 있음

- **위치**: `cli.py:22`(루트 `typer.Typer`), `client_cli.py:27-66`, `bootstrap.py:147-169`
- **원인**
  - rich가 설치된 typer는 traceback에 지역 변수를 출력하는 것이 기본입니다(`pretty_exceptions_show_locals`).
  - `request_api`는 `url.hostname`만 검사하고 포트는 검증하지 않습니다.
  - httpx 계층에서 `InvalidURL`은 `HTTPError`의 하위 클래스가 아니어서 `:65`에서 잡히지 않습니다.
- **재현**
  - `AX_API_BASE=http://127.0.0.1:8o00`과 43자 센티널 `AX_TOKEN`으로 `ax audit`를 실행합니다.
  - `InvalidURL`이 전파되어 `request_api`의 `credential`과 httpx 호출 프레임의 `headers` 딕셔너리가 stderr에 출력됩니다. rich의 기본 문자열 한도(80자)보다 짧아 잘리지도 않습니다.
  - init 중 파일 쓰기가 `OSError`(경로 길이, 디스크 공간)로 실패해도, `initialize`의 `credentials` 토큰 네 개가 같은 방식으로 출력됩니다.
- **문서와의 불일치**: README:45의 "키 값을 터미널에 출력하거나…", `cli.py:39`의 "credential 값은 출력하지 않음"과 어긋납니다.
- **최소 수정**
  - 루트 `app`(`cli.py:22`)에 `pretty_exceptions_show_locals=False`를 지정합니다. 일관성을 위해 `pack_app`·`action_app`에도 지정합니다.
  - `request_api`에서 `urlsplit`과 `url.port` 평가를 try 블록 안으로 옮기고, `httpx2.InvalidURL`도 `api_request_failed`로 매핑합니다.
- **회귀 테스트**
  - CliRunner는 except hook을 거치지 않으므로 subprocess로 `python -m ax_starter audit`를 실행합니다.
  - 종료 코드는 1, stdout·stderr에 센티널이 없어야 하고, stderr는 `cli_requires_loopback_api`여야 합니다.
- **영향 범위**
  - 같은 OS 사용자는 이미 `demo-credentials.json`과 환경변수를 읽을 수 있으므로 권한 경계를 넘지는 않습니다. 화면 공유·전사·CI 로그의 위생 문제입니다.
  - 잠금된 typer 버전의 기본값과 httpx2의 예외 계층은 공급본으로 확인할 수 없었습니다. 위 회귀 테스트로 확정하세요.

### N2 [낮음] `AX_DB_FILE` 오타나 상대 경로가 새 비보호 DB를 조용히 만듦

- **위치**: `runtime.py:27`, `store.py:19`(`parents=True` mkdir)
- **재현**
  - 폴더명이 틀린 `AX_DB_FILE`로 기동하면, 상속 ACL을 받는 새 폴더와 초기 상태 DB로 정상 기동합니다. 기존 제안·감사가 보이지 않는 상태 분기가 생깁니다.
  - 상대 경로는 작업 폴더 기준으로 풀립니다.
  - 명시적인 관리자 설정이지만, B1이 약하게 남은 형태입니다.
- **수정**: `load_app`이 절대 경로와 이미 존재하는 상위 폴더를 요구하게 하고, 아니면 `runtime_configuration_required`로 거부합니다.
- **회귀 테스트**: 없는 상위 폴더를 지정하면 오류가 나고 폴더가 생성되지 않아야 합니다.

### N3 [낮음] 상태와 맞지 않는 거부 사유 코드

- **현상**
  - 되돌린 제안을 다시 execute하면 `independent_approval_required`(403)를 받습니다(`actions.py:132-137`).
  - 실행 또는 되돌림이 끝난 제안을 approve하면 근거 재검사 후 `stale_object_version`을 받습니다(`actions.py:94-98`).
- **영향**: 상태 효과는 없고, 운영자의 대응만 오도합니다.
- **수정**: 상태 판정을 근거·버전 검사보다 앞에 두고 `proposal_state_conflict`를 반환합니다.
- **회귀 테스트**: 되돌린 뒤의 execute와 approve가 모두 409 `proposal_state_conflict`여야 합니다.

### N4 [문서] 30분 만료가 실행 시한까지 묶음

- 코드(`actions.py:76-80`)는 APPROVED 상태도 만료시킵니다(`test_actions.py:117`로 확인).
- 그런데 `docs/OPERATIONS.md`는 "승인까지 30분"이라고만 쓰고, `docs/ARCHITECTURE.md:72`에는 실행 시한이 없습니다.
- "제안 후 30분 안에 승인과 실행을 모두 마쳐야 합니다"로 고칩니다.

### N5 [낮음] 평가 CLI가 보고서 없이 비정상 종료

- `evaluation.py:69-72`는 403·404만 거부로 처리하고, 그래프 한도 413은 다시 발생시킵니다.
- `cli.py:94-99`도 AXError(`evaluation_subject_missing` 포함)를 잡지 않아 traceback으로 끝납니다.
- **수정**: 413은 실패 사례로 기록하고, CLI는 AXError를 사유 코드로 출력합니다.
- **회귀 테스트**: fanout 51개인 팩에서 `passed=false` 보고서가 나와야 합니다.

### N6 [예제 자료] 예제 팩 근거의 유효기간 만료

- `examples/*/domain-pack.json`의 `valid_until`은 `2027-10-01T09:13:25.986513Z`입니다.
- 이 시각 이후에는 예제 팩 평가에서 SOP가 유보되어 실패하며, LEARNING_GUIDE 3절 연습도 영향을 받습니다.
- 유효기간을 문서에 명시하고 `ax assets`로 재생성하도록 안내합니다.

### N7 [증거] 검사 스크립트가 소스를 변경함

- `docs/evidence/checks.txt:1`의 "1 file reformatted"는 `scripts/check.ps1`(미공급)이 `ruff format`을 변경 모드로 실행했다는 뜻입니다.
- 해시를 고정한 뒤 이 스크립트를 돌렸다면, 공급본 중 1개 파일이 시험본과 바이트 단위로 다를 수 있습니다. 포맷 변경이므로 동작에 영향을 줄 가능성은 낮습니다.
- 검사는 `ruff format --check`만 사용하고, manifest는 검사 후에 산출하세요.

## 5. 운영 전제 (이번 판정 대상 아님)

모두 문서에 이미 명시된 항목입니다.

- 기업 IdP·MFA·세션 회수, TLS, 속도 제한·쿼터 (`SECURITY_MODEL.md:11`)
- 완전한 DLP, DNS·프록시·방화벽 반출 통제, 게이트웨이 계약·리전·보관 (`:14`, `:30-31`)
- KMS 서명·WORM·SIEM, 외부 체인 앵커, 거부·반출 시도 감사 (`:17`, `:32`, `:35`)
- 원천 ACL 동기화, 실제 커넥터와 보상 트랜잭션, 운영 마이그레이션, 부하·장애·복구 (`:12`, `:16`, `:26`)
- 실제 Ollama·게이트웨이의 JSON Schema 호환성과 답변 의미 품질 평가
- 승인은 사람이 payload를 직접 읽는 절차에 의존하며, 해시를 자동 전달하는 봇은 이 통제를 무력화합니다 (`:24`).
- local 모드는 loopback 포트를 점유한 프로세스를 신뢰하므로 다중 사용자 장비에는 적합하지 않습니다.

## 6. 근거 구분

- **정적 검토(이번 감사)**
  - 공급된 `src` 27개, `tests` 16개 파일과 문서·예제 전체를 읽었습니다.
  - 테스트 함수와 parametrize를 세어 86개로, 보고 수치와 일치함을 확인했습니다.
  - 도구는 실행하지 않았습니다.
- **공급된 실행 증거(재실행하지 않음)**
  - pytest 86개 통과, basedpyright 0 errors/0 warnings, Ruff 통과(`checks.txt`)
  - 세 분야 데모 통과와 감사 4건(`synthetic-demos.json`)
  - 검색 평가 18건 통과
  - httpx2 출처·해시 발췌
- **주장만 있고 원문은 공급되지 않은 증거**
  - uvicorn 스모크 로그
  - 원본 스냅샷 재현 로그와 manifest
  - Windows ACL 출력과 wheel 독립 설치 결과
  - `scripts/*.ps1`, `templates/`, `docs/reviews/*`
  - typer 버전을 포함한 `uv.lock` 전체
- **검토 모델**: claude-opus-5-5. effort 값은 응답 안에서 확인할 수 없으니 호출 기록의 `modelUsage`로 확인하세요.

IMPLEMENTATION_AUDIT_COMPLETE