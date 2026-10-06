# v0.3 검증: LLM Wiki와 원문 RAG

2026-10-06 revision-3 수정본은 **421개 테스트**, Ruff ALL, 145개 Python 파일의 format, basedpyright 0 errors/0 warnings, 변경된 Python 48개 파일의 no-excuse 검사를 통과했습니다. [검증 index](evidence/v0.3.0/revision-3/verification-index.json)는 실제 로그 SHA-256과 전달 로그·149개 검사 소스의 hash를 결속합니다. 전체 검사·규칙 검사의 원문은 [전체 검사](evidence/v0.3.0/revision-3/final-checks.txt)와 [규칙 검사](evidence/v0.3.0/revision-3/final-no-excuse.txt)에서 확인합니다.

설치된 wheel의 **70개 runtime 모듈 바이트**가 작업 소스와 일치함을 확인하고 실제 loopback HTTP·CLI로 원문 수명주기, 기존 action 승인·실행·rollback, Wiki 작성·검토자 packet 읽기·독립 게시·재시도·검색·export·재시작·원문 retire/tombstone 차단을 실행했습니다. retire 이후 권한 있는 manager의 lint는 복구 revision을 반환하고 tombstone 이후에는 이를 숨기는 경로도 [설치 실행 로그](evidence/v0.3.0/revision-3/final-wheel-smoke.txt)에 포함됩니다. 실제 v0.2 wheel이 만든 DB를 새 v0.3 wheel로 열어 기존 원문 수를 유지하고 Wiki schema를 추가하는 [DB 이전 검증](evidence/v0.3.0/revision-3/cold-db-compatibility.txt)도 통과했습니다.

revision-2의 [417개 실행 결과](evidence/v0.3.0/revision-2/verification-index.json)는 당시 소스의 역사 기록입니다. 이후 [독립 검토](evidence/v0.3.0/revision-2/independent-review.md)가 숨은 hop link의 ACL 우회를 실제 재현해 NEEDS_FIX를 반환했습니다. revision-3는 모든 표면에 저장 query의 현재 traversal 권한을 적용하고, 관계 민감도만 상승해도 기존 page·export가 낮은 분류로 노출되지 않도록 현재 관계 분류를 다시 계산합니다. ACL 회수와 분류 상승의 네 회귀를 포함한 현재 421개 결과와 이전 394개 [index](evidence/v0.3.0/verification-index.json)를 구분합니다.

구매·고객지원·인사 Wiki 데모는 합성 데이터와 원문 추출만 사용합니다. 모델 wire 검증은 실제 loopback HTTP의 가짜 Ollama 서버와 gateway MockTransport이며 실제 회사 모델 성능이 아닙니다. 회사의 gold set·KPI·ROI·실제 IdP·업무 connector·보안 인증은 미검증입니다.

[이전 독립 Sol 검토](evidence/v0.3.0/wiki-independent-review.md)는 당시 고정 입력에서 PASS였습니다. 실제 Opus 5.5 max의 [설계 검토](evidence/v0.3.0/wiki-design-retry-public.json)와 [최초 최종 감사](evidence/v0.3.0/wiki-final-audit-public.json)는 NEEDS_FIX를 반환했습니다. 기존 head의 덮어쓰기 권한, query anchor·hop 객체 결속, 사람 신원과 생성 경로 provenance를 수정했고 재감사는 새 고정 입력과 별도 판정으로 기록합니다. 최초 설계 요청의 API timeout [실패 기록](evidence/v0.3.0/wiki-design-failure-public.json)도 보존합니다. 실패 응답과 이전 PASS를 현재 감사로 사용하지 않습니다. 외부 모델의 정적 감사는 실제 실행 검증을 대체하지 않습니다.

검증을 다시 실행하려면 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1`과 `scripts/check-package.ps1`을 사용합니다. 변경 뒤에는 새 소스 digest·평가·감사 증거를 만들고 ZIP의 `DELIVERY_MANIFEST.json` 항목별 크기와 SHA-256을 대조합니다.
