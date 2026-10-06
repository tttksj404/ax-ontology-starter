# AX Ontology Starter 최종 전달 델타 독립 정적 감사

공급본을 도구 없이 읽기만 했습니다. 테스트·린트·타입 검사는 실행하지 않았고, 실행 결과는 실행자가 낸 산출물로만 다룹니다(7절).

## 1. VERDICT: PASS

- **판정 대상**: 새 manifest(`ac5b4828…`)가 고정한 트리와, manifest 밖에서 공급된 파일 3개입니다.
- **판정 범위**: 이전과 같습니다. 합성 데이터, 로컬 참조 런타임, 로컬 SQLite 검토 상태 변경 하나입니다.
- **N1–N7**: 코드·문서·스크립트 기준으로 해소됐습니다. N4만 예외로, 운영 문서는 고쳐졌지만 설계 문서의 누락이 남았습니다. 판정에는 영향이 없습니다.
- **차단 결함: 없음.** 델타와 그 통합 지점에서 재현 가능한 차단 회귀를 찾지 못했습니다.
- 공급된 최종 델타를 같은 합성 참조 범위로 수용합니다. 이 판정은 운영 보안 인증이 아닙니다.

## 2. 델타 범위 확인

- **manifest 대조**: 두 manifest를 항목별로 비교했습니다(47 → 48항목). 결론은 실행자 설명과 같습니다.
  - 변경: `actions.py`, `cli.py`, `client_cli.py`, `evaluation.py`, `runtime.py`
  - 신규: `tests/test_final_review.py`
  - 나머지 42항목은 해시가 같습니다. README·pyproject·SECURITY_MODEL·ARCHITECTURE도 여기에 포함됩니다.
- **해시**: 공급 파일 머리말의 SHA-256은 새 manifest 항목과 문자열로 일치합니다. 해시를 직접 계산하지는 않았습니다.
- **manifest 밖 파일**: `docs/OPERATIONS.md`, `scripts/check.ps1`, `docs/evidence/checks.txt`는 머리말 해시로만 식별됩니다.
- **숨은 편집 점검**
  - 소스별 바이트 증감은 actions +260, cli +352, client_cli +89, evaluation +455, runtime +128입니다. 다섯 개 모두 기술된 수정만으로 정확히 설명됩니다.
  - 이전 감사가 인용한 줄 번호도 삽입된 줄 수만큼 정확히 밀려 있습니다. 예를 들어 실행 영수증은 `actions.py:130-131` → `:132-133`, rollback은 `:182-203` → `:186-207`입니다.
  - LF 기준으로 이전 원문 없이 재구성한 계산이라 증명은 아닙니다. 다만 기술되지 않은 편집이 섞였을 가능성은 낮습니다.

## 3. N1–N7 상태

| 항목 | 상태 | 코드 근거 | 회귀 테스트 |
|---|---|---|---|
| N1 토큰·traceback | 해소 | `cli.py:22-25`, `client_cli.py:17-19`·`:29-46`·`:68-69`, `cli.py:41-43` | `test_final_review.py:24-46`(subprocess 3건), `:49-61` |
| N2 DB 경로 | 해소(원 권고 범위) | `runtime.py:19-21` | `:64-80` |
| N3 종단 상태 오류 | 해소 | `actions.py:88-89`, `:134-135` | `:83-113` |
| N4 시한 문구 | 운영 문서 해소, 설계 문서 미변경 | `OPERATIONS.md:43` ↔ `proposal_builder.py:79`, `actions.py:76-80` | 기존 `test_actions.py:117` |
| N5 413·평가 CLI | 해소 | `evaluation.py:73-79`·`:86-92`, `cli.py:99-111` | `:116-152`, `:155-177` |
| N6 예제 만료 안내 | 해소(문서) | `OPERATIONS.md:7` | 해당 없음 |
| N7 읽기 전용 검사 | 해소 | `check.ps1:5-12`, `checks.txt:1-7` | 해당 없음(5절) |

**N1**
- **루트 `app`의 설정이 결정적입니다.**
  - `python -m ax_starter`(`__main__.py:3`)와 콘솔 진입점은 모두 루트 `app()`을 호출합니다.
  - Typer는 호출된 앱의 `pretty_exceptions_*` 설정을 예외에 붙입니다. Typer 0.6 이후 구현 기준이며, 잠금된 버전은 확인하지 못했습니다.
  - 따라서 `pack_app`·`action_app`에 같은 값을 준 것은 일관성을 위한 것입니다.
- **URL 검증**: `urlsplit`과 `url.port`가 try 안으로 옮겨졌습니다(`client_cli.py:30-31`). 테스트 입력 세 개는 서로 다른 이유로 같은 `ValueError` 분기(`:42-43`)에 들어갑니다.
  - `8o00`: 포트를 정수로 바꿀 수 없음
  - `70000`: 포트 범위 초과
  - `http://[`: `urlsplit` 자체의 IPv6 괄호 오류
- **토큰 읽기 시점**: 토큰은 URL 검증이 끝난 뒤(`:44`)에 읽힙니다. 따라서 세 입력에서는 토큰이 지역 변수로 존재하지도 않습니다.
- **`InvalidURL` catch(`:68`)는 여전히 필요합니다.** 경로 속 제어문자처럼 urllib는 통과시키지만 httpx 계열은 거부하는 입력이 있기 때문입니다.
- **init**: `OSError`가 나면 사유 코드를 출력하고 `typer.Exit`로 끝납니다. click은 `Exit`에 traceback을 남기지 않습니다.
- **테스트 방식**
  - URL 3건은 실제 subprocess로 except hook 경로까지 거칩니다. 토큰은 합성 센티널만 씁니다.
  - init·평가 CLI 테스트는 `CliRunner`를 씁니다. 검증 대상이 사유 코드 변환이라 이것으로 충분합니다.

**N2**
- 절대 경로가 아니거나 상위 폴더가 없으면 503으로 거부합니다.
- 이 검사는 팩·ID 읽기와 `Store`의 `mkdir(parents=True)`(`store.py:19`)보다 먼저 실행됩니다. 그래서 거부할 때 아무것도 만들지 않으며, 테스트도 파일·폴더가 생기지 않았음까지 확인합니다.
- Windows의 `C:state.db`(드라이브 상대 경로)와 `\state.db`(드라이브 없는 루트)도 `is_absolute()`가 거짓이라 거부됩니다.

**N3**
- **approve**: EXECUTED·ROLLED_BACK 상태면 `_authorized` 직후 409 `proposal_state_conflict`를 냅니다. 자기 승인·해시·근거·버전 검사보다 앞입니다.
- **execute**: EXECUTED면 영수증을 그대로 반환하고, ROLLED_BACK이면 409를 냅니다. 그 밖의 미승인 상태는 기존대로 403입니다.
- **상태 노출 없음**: 상태 판정은 테넌트·폐기·가시성·operation 권한 검사 뒤에 있습니다. 권한이 없는 주체에게는 상태가 드러나지 않습니다.
- **상태 변경 경로 증가 없음**: 바뀐 것은 오류 코드뿐입니다. 종단 상태에 대한 approve는 이전에도 항상 `stale_object_version` 오류였습니다. 버전이 단조 증가하기 때문입니다.

**N4**
- 코드는 제안 시각부터 30분을 PROPOSED·APPROVED 두 상태 모두에 `now >= expires_at` 조건으로 적용합니다. 새 문구 "제안 후 30분 안에 승인과 실행을 모두"와 일치합니다.
- `docs/ARCHITECTURE.md`는 해시가 그대로입니다(`8624ceaf…`). 따라서 원 감사가 지적한 `:72`의 실행 시한 누락도 남아 있을 것입니다.

**N5**
- **413 기록 방식**: 413 사례는 `failure_code`를 남기고 `citation_exact=false`, `denied=false`로 기록됩니다.
- **정상 거부와 구분**: `passed`는 `failure_code is None`을 요구합니다. 그래서 `expected_denial=true`인 사례에서도 413은 정상 거부로 집계되지 않습니다. 테스트가 두 경우를 모두 고정합니다.
- **재발생 분기**: `retrieve`가 내는 AXError는 403·404·413뿐이라 재발생 분기에는 사실상 도달하지 않습니다.
- **CLI**: `evaluation_subject_missing`, `identity_registry_unavailable`은 사유 코드를 출력하고 종료 1로 끝납니다. 실패한 보고서는 출력한 뒤 종료 1입니다.
- **상수**: `HTTPStatus.REQUEST_ENTITY_TOO_LARGE`는 3.13에서도 `CONTENT_TOO_LARGE`의 별칭으로 남아 있어 413과 같습니다.
- **해석 주의**: 기대 문서가 없는 413 사례도 recall은 1.0으로 집계됩니다. 판정은 `passed`와 `failure_code`로 해야 합니다.

**N6**
- 안내 내용은 코드와 맞습니다.
  - 만료된 문서는 검색에서 빠집니다(`retrieval.py:100`).
  - init은 현재 시각 기준으로 팩을 만듭니다(`bootstrap.py:160`).
- `ax assets`도 현재 시각 기준인지는 `assets.py`가 다시 공급되지 않아 직접 확인하지 못했습니다.
  - 다만 이전 감사가 기록한 예제 `valid_until`은 `2027-10-01T09:13:25.986513Z`입니다.
  - 마이크로초까지 있는 값이라, 실행 시각에 1년을 더해 만든 형태로 보입니다(추론).
- LEARNING_GUIDE 3절은 공급되지 않았습니다.

## 4. 차단 회귀 점검: 없음

- **새 분기의 성격**: 모두 오류 코드를 바꾸거나 더 일찍 거부할 뿐입니다. 상태 변경이나 감사 기록을 추가하는 경로는 없습니다.
- **검사 순서**: approve·execute 모두 `_authorized`(권한·가시성·만료·팩 해시)가 새 분기보다 먼저 실행됩니다.
- **기존 통제**: B1–B3, 동일 승인자 재시도, 숨은 제안 404는 줄 위치만 바뀌었습니다.
- **기존 테스트**: 공급된 기존 테스트 4개 파일의 기대값을 새 검사 순서로 다시 추적했고, 모두 유지됩니다. 예는 다음과 같습니다.
  - 동일 승인자 재시도는 APPROVED 상태라 종단 검사에 걸리지 않습니다.
  - 미승인 execute는 여전히 403입니다.
  - 등록부에서 승인자를 폐기한 뒤의 실행은 여전히 403 `approver_revoked`입니다.
- **루프백 검증은 약해지지 않았습니다.**
  - 포트 평가가 앞당겨져서 `http://127.0.0.1:8000\host` 같은 입력도 토큰을 읽기 전에 거부됩니다.
  - 허용되는 형태가 정규 IP 리터럴뿐입니다. urllib와 httpx의 파서 차이를 이용해 루프백이 아닌 곳으로 보내는 입력은 찾지 못했습니다.
- **`CaseResult.failure_code`**: 기본값이 None이라 기존 소비 측과 호환됩니다. 출력 JSON에는 `"failure_code": null`이 추가됩니다.

## 5. N7: 이전 로그 1행과 현재 스크립트의 구분

- **스크립트 동작(`check.ps1:5-12`)**: 네 명령 모두 `uv run --frozen`으로 실행되고, 실패하면 즉시 종료합니다.
  - `ruff check src tests`: `--fix`가 없습니다.
  - `ruff format --check src tests`: 검사 모드입니다.
  - `basedpyright`, `pytest -q`: 소스를 쓰지 않습니다.
- **이전 1행은 이 스크립트에서 나올 수 없습니다.**
  - **문구로 본 근거**
    - `1 file reformatted`는 쓰기 모드 `ruff format`만 출력합니다.
    - `--check`는 파일을 쓰지 않습니다. 출력은 `N files already formatted`, 또는 `Would reformat: …`와 `N file(s) would be reformatted`뿐입니다.
  - **순서로 본 근거**
    - 현재 스크립트라면 첫 출력은 `ruff check`의 `All checks passed!`입니다.
    - 따라서 1행의 포맷 문구는 스크립트보다 먼저 실행된 별도 명령의 출력이어야 합니다.
  - 두 근거 모두 "바깥 준비 명령이 한 번 포맷했다"는 설명과 맞습니다. 이전 감사의 N7은 스크립트가 공급되지 않은 상태에서 그 한 줄만 보고 한 추정이었습니다.
- **새 로그가 보여 주는 것**
  - 일곱 줄이 스크립트 네 단계와 순서대로 대응합니다.
  - `reformatted`나 `fixed` 문구가 없습니다.
  - `44 files`는 새 manifest의 Python 파일 수(src 27 + tests 17)와 같습니다.
  - 진행 점은 72 + 26 = 98개입니다. 72/98은 표시된 73%와 맞습니다.
- **소스가 아닌 부산물**: 다음은 모두 manifest 대상이 아닙니다.
  - `uv run`의 `.venv` 동기화
  - pytest의 `.pytest_cache`·`__pycache__`
  - 테스트의 `tmp_path` 쓰기
  - `uv.lock`은 `--frozen` 때문에 갱신되지 않습니다.
- **확인할 수 없는 것**
  - **ruff 자동 수정 설정**
    - 설정에 `fix = true`가 있으면 `ruff check`도 파일을 수정할 수 있습니다. pyproject는 이번에 공급되지 않았고, 해시는 이전과 같습니다.
    - 다만 수정이 일어났다면 `Found N errors (N fixed, …)`가 찍혔을 것입니다. 따라서 이번 실행에서는 수정이 없었습니다.
  - **실행자 진술**: 이전 스크립트 해시는 공급되지 않았습니다. 따라서 다음 두 가지는 실행자 진술에 의존합니다.
    - 스크립트가 예전부터 `--check`였다는 이력
    - 새 로그가 이 트리에서 이 스크립트만으로 생성됐다는 점
  - **산출 순서**: 스크립트가 소스를 쓰지 않으므로, manifest 산출과 검사의 선후는 이제 소스 해시에 영향을 주지 않습니다.

## 6. 남은 한계 (비차단)

1. **N1 설정 자체를 고정하는 테스트가 없습니다.**
   - 이제는 예외가 전파되지 않으므로, `pretty_exceptions_show_locals=False`를 지워도 새 subprocess 테스트는 통과합니다.
   - 보완 방법: subprocess에서 `ax_starter.client_cli.provider_client`를 예외를 던지는 함수로 바꿉니다. 그다음 센티널 토큰을 넣고 `app(["audit"])`를 실행합니다. stderr에 traceback은 있되 센티널은 없어야 합니다.
2. **사유 코드 대신 traceback으로 끝나는 경로가 남아 있습니다.** 다만 지역 변수는 이제 출력되지 않습니다.
   - `pack validate`·`pack eval`·`action propose`·`assess`·`process`에 없거나 잘못된 파일을 준 경우
   - 2자 미만의 `ask` 질문
   - 비ASCII 문자가 섞인 `AX_TOKEN`: httpx와 같은 동작이라면 헤더 인코딩 오류로 끝나며, 메시지에 문제 문자 하나와 위치가 나옵니다.
   - 정적으로 본 범위에서는 토큰 전체가 메시지에 들어가는 경로를 찾지 못했습니다.
3. **N2 잔여**
   - 존재하는 폴더 안에서 파일명을 잘못 쓰면, 여전히 빈 상태의 새 DB로 기동합니다.
   - 상위 폴더가 보호돼 있는지는 검사하지 않습니다. 경로 확인과 ACL 검증은 `OPERATIONS.md:5`가 운영자 책임으로 둡니다.
   - 더 막으려면 두 가지 방법이 있습니다. init이 `state.db`를 미리 만들고 런타임은 기존 파일만 열게 하거나, 명시적인 생성 플래그를 둡니다.
4. **N2 통합은 확인하지 못했습니다.**
   - README(미변경·미공급)와 기동 스크립트가 `AX_DB_FILE`을 절대 경로로 설정하는지 알 수 없습니다. 상대 경로라면 이번 변경 때문에 기동이 `runtime_configuration_required`로 실패합니다.
   - 새 증거에는 uvicorn 기동 기록이 없습니다. README 절차를 한 번 실행해 보길 권합니다.
5. **N4 잔여**
   - `ARCHITECTURE.md:72`의 실행 시한 누락이 남아 있습니다.
   - "새 제안"은 "새 `request_key`로 새 제안"이라고 써야 정확합니다. 같은 키로 다시 제출하면 `proposal_builder.py:26-46`이 만료된 기존 제안을 그대로 돌려주고, 승인할 때마다 `proposal_expired`가 반복됩니다.
6. **N3 문서(선택)**: 운영 장애 표에 `proposal_state_conflict` 항목이 없습니다.
7. **init 부분 실패 뒤의 정리 안내가 없습니다.**
   - 파일 쓰기 도중 실패하면 보호 폴더에 일부 산출물이 남습니다. 쓰는 순서상 `demo-credentials.json`도 남을 수 있습니다.
   - 재실행은 `initialization_directory_not_empty`로 막히므로 수동으로 정리해야 합니다. 이는 `bootstrap.py`의 기존 동작입니다.
8. **이전 실행 증거는 델타 전에 만들어졌습니다.**
   - 데모 JSON, 검색 평가 18건, uvicorn 스모크 기록이 여기에 해당합니다.
   - 저장된 평가 보고서에는 `failure_code` 필드가 없을 수 있습니다.

기업 운영 전제는 이전 감사 5절 그대로이며, 이번 판단 대상이 아닙니다.

## 7. 근거 구분

- **정적으로 검토한 것(이번 감사)**
  - 이전 감사 `OPUS_REAUDIT.md`는 N1–N7의 정의를 확인하는 데만 썼고, 결론은 재사용하지 않았습니다.
  - manifest 2개를 항목별로 대조했습니다.
  - 변경된 소스 5개와 신규 테스트는 전문을 읽었습니다.
  - 통합 확인을 위해 미변경 파일도 읽었습니다.
    - 소스: `__main__`, `common`, `action_contracts`, `store`, `proposal_builder`, `auth`, `policy`, `retrieval`, `providers`, `bootstrap`
    - 테스트: `test_actions`, `test_api`, `test_runtime`, `test_review_contracts`
  - manifest 밖 파일 3개도 읽었습니다.
- **정적 일관성 확인**
  - 신규 사례는 3+1+2+2+1+2+1 = 12건이고, 86 + 12 = 98입니다.
  - 12건 모두 이전 동작에서는 단언이 실패함을 추적했습니다. "처음에 12건이 실패했다"는 진술과 맞습니다.
  - 2절의 바이트·줄 번호 대조와 5절의 로그 대응도 여기에 속합니다.
- **실행자 산출물(직접 재실행할 수 없음)**
  - 수정 전 12건 실패
  - 98 passed, Ruff ALL, format `--check`, basedpyright 0/0
  - 실제 Typer·rich·httpx2 버전에서의 subprocess 동작
  - Click 버전에 따라 달라지는 `CliRunner`의 stderr 분리 동작
  - 로그가 이 트리에서 `check.ps1`만으로 생성됐다는 점
- **공급되지 않아 확인하지 못한 것**
  - 소스: `api.py`, `assets.py`, `demo*.py`, `generation.py`
  - 테스트: `conftest.py`, `live_server.py`, 나머지 테스트
  - 문서: README·ARCHITECTURE·SECURITY_MODEL 본문, LEARNING_GUIDE
  - 설정·자료: pyproject, `uv.lock`, `examples/`, httpx2 소스
- **검토 모델**: claude-opus-5-5