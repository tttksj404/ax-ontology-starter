# v0.1 검증 결과와 직접 재현

기준일: 2026-10-01, 사용자 시간대 Asia/Seoul. 범위는 합성 자료의 로컬 참조 런타임입니다. 실제 회사 데이터·실제 업무 시스템의 쓰기·실제 로컬 LLM 또는 기업 게이트웨이의 추론 품질은 검증하지 않았습니다.

## 직접 실행한 검증

| 검증 | 결과 | 증거 |
|---|---|---|
| pytest | 98 passed | [실행 로그](evidence/checks.txt) |
| basedpyright `all` | 0 errors / 0 warnings | 같은 실행 로그 |
| Ruff `ALL`와 format | 통과 | 같은 실행 로그 |
| 업무 전체 진단 | 세 분야 각각 6단계; 행정 후보 4개, 예외 승인 필요, 최종 판단 보조 | [실제 합성 진단 출력](evidence/synthetic-workflow-assessments.json) |
| 세 분야의 완결 흐름 | 구매·고객지원·입사서류 모두 `passed=true` | [실제 CLI 결과](evidence/synthetic-demos.json) |
| 합성 검색 gold set | 분야별 6개, 합계 18개 통과 | [분야별 평가 결과](evidence/synthetic-retrieval-evaluations.json) |
| 전체 흐름 기준선 | 합성 3건, lead 중앙값 32분, step-2 대기 비중 0.8 | [계산 결과](evidence/synthetic-process-metrics.json) |
| 실제 프로세스 API/CLI | uvicorn factory 시작 → health → 인증된 한국어 질의 → SOP 인용 → 소유 프로세스 종료 | [스모크 로그](evidence/live-runtime-smoke.txt) |
| 모델 프로토콜 | 실제 loopback HTTP의 가짜 Ollama 응답, gateway MockTransport | `test_wire.py` |
| 패키지 | 최종 코드의 wheel / sdist 빌드, 분리한 offline wheel 설치로 support 데모 통과 | [빌드·독립 실행 로그](evidence/package-build-smoke.txt) |
| 예기치 않은 CLI 예외 | subprocess의 합성 토큰이 실제 기본 설정에서 숨겨짐; locals를 켜는 대조군은 노출 재현 | [추가 고장 주입 결과](evidence/unexpected-cli-traceback.json) |
| 전달 ZIP | 항목별 SHA-256·크기·누락·중복 검사, runtime/credential/cache 제외 | [ZIP 검증 스크립트](../scripts/verify-package.ps1), ZIP 내부 `DELIVERY_MANIFEST.json` |
| Windows 새 폴더 ACL | 상속 제거, 현재 계정 FullControl만 확인 | 실제 `Get-Acl` 확인; 자격증명 값 출력 없음 |
| 공개 자산 export | 17개 예제·스키마·설정, credential/identity 제외, 기존 폴더 보존 | `test_cli.py`, `ax assets examples` 실행 |

98개 테스트는 검증 범위의 설명이며 현실의 오류율·누출 확률을 수치로 보증하지 않습니다. 18개 검색 평가는 합성 gold set의 근거 회수·인용·거부 검증이며 생성 답변 의미 품질의 실측 정확도가 아닙니다.

## 안전 회귀에서 확인한 동작

다른 테넌트·그룹·등급·목적의 자료 차단, 숨은 객체와 없는 객체의 동일 404, 숨은 문서 제거 전후 사용자 답변의 동일성, 문서 만료, 타입/속성 분류 하향과 임의 처리기 거부를 확인했습니다. 인증 없는 요청과 본문 역할 위조, 실제 수신 크기 제한도 시험했습니다.

승인 없는 실행·자가 승인·검토 해시 불일치·승인 만료·권한 회수·DB payload 변조를 거부합니다. 동시 실행과 중복 요청에서 상태 효과를 한 번만 적용하고, 최신 수정 또는 24시간 경과 후 되돌리기를 차단합니다. 상태·영수증·감사는 같은 DB 트랜잭션에 기록됩니다. 단순 감사 변조는 체인 검증에서 발견하며 전체 재작성에 대한 외부 불변성은 주장하지 않습니다.

모델은 도구를 받지 않고 근거를 포함한 JSON 초안만 반환합니다. 허위 인용과 `tool_calls`가 있는 응답을 거부합니다. 제한 자료의 cloud 전송 거부는 네트워크 요청 수 0으로 확인합니다. 실제 모델·게이트웨이에서 같은 계약이 지원되는지, 분야 답변이 올바른지는 별도 파일럿에서 검증해야 합니다.

## 모델 협업과 독립 감사

설계 호출은 실제 `claude-opus-5-5` / `max`이며 응답 `is_error=false`, `modelUsage`의 모델 이름을 확인했습니다. [Opus 설계 원문](reviews/OPUS_DESIGN.md)을 보존합니다. 원본 JSON SHA-256은 `99afd76ffcae8f404932f6fe23a842da6ed97d12dc1cf49e748101405129f84b`입니다.

공동 설계의 전체 흐름·인계·통제점, 미확인 입력 유보, 보수적인 분류, 검토 해시 승인, 최신 권한/근거 확인, 멱등/복구, 업종팩과 업그레이드 단계를 반영했습니다. 서수 평가 대신 가중 휴리스틱을 사용하되 점수의 의미를 제한했고, 필드 단위 투영 대신 객체 전체를 가장 높은 속성 등급으로 제한했습니다. 실제 커넥터 쓰기 대신 로컬 검토 상태만 변경하는 범위를 선택했습니다.

독립 구현 감사는 설계 대화와 분리한 새 Opus 5.5 max 호출로 코드·테스트 전체와 실제 검사 결과를 전달했습니다. 초기 스냅샷은 43개 파일이며 [초기 SHA-256 manifest](evidence/audit-input-manifest.json)를 보존합니다. 최초 판정은 **NEEDS_FIX**였습니다. [초기 감사 원문](reviews/OPUS_IMPLEMENTATION_AUDIT_INITIAL.md)을 그대로 보존합니다.

DB 환경변수 불일치, 승인 검토 payload 누락, 근거 만료 후 영수증·복구 차단을 [원래 스냅샷에서 실제 재현](evidence/initial-regressions-red.txt)했습니다. 복원한 원본 소스 27개 파일의 해시도 초기 manifest와 일치했습니다. 해당 문제와 감사의 구체적인 비차단 결함을 수정하고, 27개 회귀를 추가해 86개 검사 전체가 통과했습니다. 47개 파일을 대상으로 한 [독립 재감사](reviews/OPUS_REAUDIT.md)는 **PASS**, 차단 결함 없음으로 판정했습니다. [모델 호출 기록](evidence/reaudit-model-run.json)과 [감사 입력 manifest](evidence/reaudit-source-manifest.json)를 보존합니다.

추가 수정은 시간대 있는 평가 CLI, 현재 시각 기준 합성 데모와 테스트 시계 주입, 같은 테넌트의 숨은 제안 404, 승인 재시도, CLI의 안전한 서버 사유 코드, DB 잠금 503, 명시적 그래프 한도 거부, 평가 주체의 테넌트 결속, 운영 Host와 테스트 Host 분리, 새 폴더 생성 경합 차단 및 Windows 현재 토큰 SID ACL입니다. 모델 전송을 질문·문서 ID·본문으로 줄이고, 실제 전송문 전체의 패턴 검사와 관계 분류·압축 응답 차단도 추가했습니다.

재감사의 비차단 지적도 반영했습니다. 잘못된 URL/포트를 토큰 읽기 전에 거부하고, 모든 Typer 앱에서 traceback의 지역 변수 출력을 끕니다. DB는 절대 경로와 준비된 상위 폴더를 요구합니다. 종단 제안 상태 오류, 그래프 한도 초과 평가의 실패 기록과 CLI 사유 코드도 보완했습니다. [수정 전 12개 실패 요약](evidence/final-delta-regressions-red.txt)을 보존하고, 추가 회귀로 최종 98개 검사가 통과했습니다.

5개 소스와 신규 테스트의 마지막 변경분을 새 Opus 5.5 max 호출로 검토한 [최종 델타 감사](reviews/OPUS_FINAL_DELTA_AUDIT.md)도 **PASS**, 차단 결함 없음입니다. [호출 기록](evidence/final-delta-model-run.json), [48개 파일의 감사 입력 manifest](evidence/final-source-manifest.json)를 제공합니다. 원본 응답 SHA-256은 `c5f6a825472958d98243d5f142659f793327a3801f63340b79fb32fa9b5f3c4c`입니다. 모델 이름은 실제 `modelUsage`로 확인했고, 추론 강도 `max`는 고정 CLI 인자와 실행 기록으로 확인했습니다.

최종 감사 이후에는 코드·테스트를 바꾸지 않았습니다. 문서의 실행 시한·새 요청키·부분 초기화 실패 안내를 고치고 구조도에도 30분 실행 시한을 표시했습니다. 따라서 감사 입력 manifest의 `ARCHITECTURE.md` 해시는 당시 문서에 해당합니다. 전달 ZIP에는 보완된 문서가 들어가며 현재 내용은 ZIP 내부 manifest로 확인합니다. 검토된 소스 27개와 테스트 17개의 해시는 그대로 일치합니다.

Opus는 공급된 코드를 **정적으로 검토**했으며 검사를 직접 실행하지 않았습니다. 실제 로컬 검사·HTTP/CLI·합성 데모·18개 검색 평가·독립 wheel 실행은 Codex가 수행했습니다. 마지막 코드 변경 뒤 데모/검색 평가/API/패키지 증거를 새로 수집했습니다. locals를 켜는 대조군과 실제 기본 설정의 예기치 않은 예외도 별도 subprocess로 비교했습니다. 실제 회사 모델 품질이나 운영 보안 감사의 승인을 의미하지 않습니다.

## 재현 명령

```powershell
uv sync --frozen
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1
uv run ax demo --domain procurement
uv run ax demo --domain support
uv run ax demo --domain hr
uv run ax process examples\process-log.json
uv build
uv run --isolated --no-project --offline --with dist\ax_ontology_starter-0.1.0-py3-none-any.whl python -m ax_starter demo --domain support
```

API 스모크와 권한 회수/모델 wire 검증은 `tests/test_api.py`, `tests/test_wire.py` 및 README의 실제 서버 실행법으로 재현합니다. 가짜 모델 서버의 성공을 실제 모델 호출 성공으로 표기하지 않습니다.

## 남은 운영 조건

[보안 모델](SECURITY_MODEL.md)의 기업 IdP/MFA, 완전 DLP와 네트워크 반출 통제, KMS/WORM/SIEM, 원천 ACL/자료 갱신·삭제, 운영 마이그레이션, 부하/장애/복구, 분야별 의미 품질, 외부 쓰기 커넥터 검증은 별도 도입 작업입니다. 이번 결과를 실고객 성과, 운영 채택 완료, 법률 준수 또는 보안 인증으로 표현하지 않습니다.
