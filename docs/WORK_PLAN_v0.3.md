# v0.3 LLM Wiki 실행 계획

LLM Wiki는 AX의 업무 규정·예외·용어·판단 이유를 누적하는 파생 지식 계층으로 추가합니다. 원천 RAG는 현재 권한과 원문을 확인하고, 온톨로지는 업무 객체·관계를 연결하며, Wiki는 원문에 결속된 초안을 검토해 게시합니다. Wiki 페이지를 원천 문서로 섞거나 작업 승인 근거로 자동 승격하지 않습니다.

## 현재 기준선

v0.2 ZIP과 325개 테스트·Opus 5.5 max 최종 PASS는 해당 버전의 증거로 보존합니다. v0.3의 이전 394개·417개 테스트와 기존 NEEDS_FIX 판정도 고정 입력별 기록입니다. 2026-10-06 revision-3 수정본은 421개 전체 테스트, 145개 파일 format, Ruff ALL·타입 오류/경고 0, 변경 Python 48개 no-excuse, 설치된 70개 runtime 소스 일치와 실제 HTTP·CLI·재시작·지식 수명주기, 실제 v0.2→v0.3 wheel DB 이전을 통과했습니다. 새 독립 검토와 Opus 재감사 판정·배포본은 이 수정 소스의 149개 검사 파일 manifest에 별도로 결속합니다.

## 실행 범위

1. Karpathy 원안과 OWASP 1차 자료, 기존 runtime을 대조해 기업용 hybrid 경계를 판단합니다.
2. 동일 SQLite에 회사별 페이지·초안·버전·검토·원천 결속을 저장합니다.
3. 짧은 transaction의 원천 snapshot → transaction 밖 컴파일 → 재인증·원천 재검사 후 초안 저장을 구현합니다.
4. 실제 서로 다른 human의 payload hash 검토를 거친 게시와 CAS·멱등·감사를 구현합니다.
5. 현재 원천까지 내려가는 질의, 권한별 index·backlink·lint, 정적 Markdown export를 제공합니다.
6. 원천 변경·ACL·retire는 사용을 차단하고 tombstone은 종속 초안·게시 버전의 본문을 논리 제거합니다.
7. offline extractive와 local/private/cloud model draft를 기존 모델 경로로 구분하며 전체 입력 원문을 권한·분류에 결속합니다.
8. API·CLI·합성 데모, 학습 다이어그램·업종 강화·회사 gold set 평가 서식을 제공합니다.
9. 전체 회귀·타입·정적 검사, 설치 wheel의 실제 HTTP/CLI·재시작, 독립 Sol 검토와 실제 Opus 5.5 max 재감사를 수행합니다.
10. 새 배포본의 모든 내부 파일과 감사·검사 manifest 해시를 대조합니다.
11. page당 raw 원천 최대 10개·요청당 단일 page·Wiki→Wiki synthesis 없음·수동 source 관리·기본 RESTRICTED floor·원천별 AND로 독자가 축소되는 제품 경계를 문서와 gold set에 고정합니다.
12. existing/stale head의 권한 없는 overwrite·revision 탐색은 동일 404로 닫고, query anchor·hop scope 객체를 검토 hash와 현재 권한 검사에 결속합니다.
13. compile 작성자는 non-null effective person의 HUMAN으로 제한하고, `generation_route`의 `mode`·`endpoint_host`·`model`·`provider_settings_sha256`을 검토 hash·page·export에 전파합니다.
14. raw/derived role 재분류, marker BOM·공백·원형 export JSON, v0.3→v0.2 rollback, 개인정보·legal hold·Markdown/API 렌더링과 SQLite 규모 한계를 회귀·운영 문서에 반영합니다.
15. 저장 query를 actor의 현재 graph 권한으로 재탐색하여 모든 bound 객체가 현재 scope에 들어가는지 확인하고 관계 민감도도 분류 하한에 반영합니다. 숨은 link ACL과 관계 분류 상승의 실제 실패 반례를 수정·회귀 검증합니다. 현재 허용된 대체 경로는 인정하며 과거 링크 ID·type·경로 snapshot은 별도의 확장 범위로 명시합니다.

## 완료 경계

페이지의 생성 주장과 원문 인용 문자열이 존재한다는 사실을 semantic entailment나 의미 정확성으로 표현하지 않습니다. 회사의 숨긴 case, Wiki 작성자·검토자와 분리된 두 명의 현업 채점자, 불일치 조정을 포함한 gold set이 필요합니다. 원천과 scope 객체 권한의 유효 조건은 각각에 대한 AND이고, group 이름의 단순 교집합과 다릅니다. 자기 생성 Wiki를 원천으로 재수집하는 운영 경로는 server role과 provenance로 구분해야 합니다. 저장된 Markdown의 다운로드 이후 회수, SQLite/WAL·백업의 물리 삭제, 실제 기업 connector·IdP·모델 성능은 회사 환경에서 확인합니다.

현재 설계 재검토와 최종 감사 파일의 판정은 모두 `NEEDS_FIX`입니다. 계획이나 문서 수정으로 이 판정을 바꾸지 않습니다. B1·B2와 R1–R5를 코드·문서·회귀 테스트에 반영하고 새 tested-source manifest와 실행 증거를 만든 뒤, 새 고정 입력으로 Opus 5.5 max 재감사를 받아야만 v0.3 최종 판정을 갱신합니다.

## 역할

Codex는 통합·컴파일러·API·CLI·실행 증거를 담당합니다. Sol xhigh는 독립 설계, Wiki 저장·권한·생명주기 구현, 독립 검증을 구분해 담당합니다. Opus 5.5 max는 설계 반례와 고정한 최종 소스의 정적 감사를 담당합니다. 구현자와 최종 감사자를 구분합니다.
