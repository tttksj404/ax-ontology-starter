# v0.3 전달본과 회사 적용 조건

온톨로지·현재 원문 RAG에 검토된 LLM Wiki를 추가한 로컬 참조형 AX 스타터팩입니다. 업무 진단, 원천 계약, 권한에 따른 검색과 모델 경로 선택, 검토·게시·삭제 전파, 승인된 작업 실행과 rollback, 업종별 domain pack 및 L0–L4 강화 방법을 함께 제공합니다.

RAG는 현재 원문과 권한을 확인하는 근거 계층이고, Wiki는 여러 업무에서 재사용할 규정·용어·예외를 사람이 검토해 축적하는 파생 계층입니다. Wiki가 원천 문서나 작업 승인 근거로 자동 승격되지는 않습니다. 자주 바뀌는 개인별 case보다 안정된 절차·규정부터 적용합니다.

이 문서는 2026-10-06 revision-3 최종 감사 후 작성한 결과 정리와 회사 적용 지침입니다. Opus의 고정 감사 입력은 140개 파일이며, 이 후속 문서는 그 입력 이후에 추가했습니다. 감사한 코드·테스트·기존 문서의 바이트는 보존했습니다.

## 확인된 결과

| 검사 | 결과와 범위 |
|---|---|
| 전체 실행 검사 | 421개 테스트 통과, Ruff ALL, 145개 Python 파일 format 통과, basedpyright 오류·경고 0 |
| 별도 코드 규칙 | v0.2 대비 변경된 Python 48개 파일의 no-excuse 검사 통과 |
| 설치본 실행 | wheel 설치 후 runtime 70개 모듈의 바이트 일치, 실제 loopback HTTP·CLI·재시작·원문/Wiki 수명주기 통과 |
| 버전 이전 | 실제 v0.2 wheel이 만든 DB를 실제 v0.3 wheel로 여는 이전 검사 통과 |
| 독립 Sol 검토 | 두 링크 반례 직접 재실행, 핵심 38개와 전체 421개, 린트·타입 독립 실행 후 PASS |
| 실제 Opus 5.5 max | runtime 70개 전체·선택 테스트·문서·실행 증거의 정적 감사 PASS; 실행 검증은 별도 증거 |

[현재 실행 증거](evidence/v0.3.0/revision-3/verification-index.json), [독립 검토](evidence/v0.3.0/revision-3/independent-review.md), [실제 Opus 판정 전체](evidence/v0.3.0/revision-3/final-audit-public.json)에서 범위와 한계를 확인합니다. Opus의 응답은 실제 모델명을 확인하며, max는 CLI의 `--effort max` 호출 인수로 확인했습니다. 두 검토는 같은 검사 소스에 대해 병렬 진행했고, 새 Sol 보고서는 Opus 입력 이후에 작성되어 Opus가 그 보고서를 검토한 것은 아닙니다.

검사 소스 149개 manifest SHA-256은 `a82dab5666b1167e0f05bcd57853646823f42c4e065710bcd8696c4f484621d8`, Opus 감사 입력 140개 manifest SHA-256은 `249fb15a40b9f5265b79a364c3b160bed6235ca9f77728e03413000e36b715dd`입니다. 전달 ZIP 안의 `DELIVERY_MANIFEST.json`에는 동봉한 파일별 크기와 SHA-256이 있습니다. ZIP 외부의 `.delivery.json`과 `.zip.sha256`은 최종 패키지 대조 결과입니다. raw advisor JSON, 세션·사용량 metadata, `.omx`, runtime DB·캐시·환경과 비밀값은 전달 대상에서 제외합니다.

이전 394개·417개 결과와 NEEDS_FIX는 각 고정 입력의 역사 기록으로 보존했습니다. 현재 PASS는 로컬 참조 구현에서 식별한 차단 결함을 수정·검증한 결과이며, 합성 데이터의 성공을 기업 배포·보안 인증·실제 모델 품질·ROI로 확대하지 않습니다.

## 바로 실행하기

압축을 풀어 `ax-ontology-starter` 디렉터리에서 실행합니다. Python과 uv 설치 방법은 [README](../README.md)에 있습니다.

```powershell
uv sync --frozen
uv run ax wiki demo --domain procurement
uv run ax wiki demo --domain support
uv run ax wiki demo --domain hr
```

세 데모는 합성 원문을 추출하며 외부 모델을 호출하지 않습니다. 모델 wire 검사는 가짜 Ollama loopback HTTP와 gateway MockTransport를 사용했습니다. 실제 회사 모델의 답변 품질과 backend 실행 위치·보존·삭제는 회사 환경에서 확인해야 합니다.

회사 적용은 [v0.2 회사 적용 가이드](V02_GUIDE.md)에서 신원·원천 계약·domain pack·모델 정책을 정하고, [v0.3 실행 가이드](V03_GUIDE.md)와 [Wiki 가이드](LLM_WIKI_GUIDE.md)에서 검토·게시를 진행합니다. 단계별 강화와 운영 복구는 [업그레이드 가이드](UPGRADE_GUIDE.md), [운영 가이드](OPERATIONS.md)를 사용합니다.

## 최종 감사의 비차단 권고 8개

다음 항목은 현재 전달 코드에 남아 있는 동작·검증 공백입니다. 회사 pilot 전에 해당 환경에서 영향과 조치를 확인합니다. 이 표의 문서 정정은 기존 가이드·서식의 해당 표현을 읽을 때 함께 적용합니다.

| 항목 | 현재 동작·회사 적용 조치 | 다음 업그레이드의 수용 기준 |
|---|---|---|
| 1. 교체 draft의 기존 head metadata | 기존 head를 읽을 수 없는 reviewer도 공유받은 draft UUID와 새 원천 권한이 있으면 후보 packet의 page ID·예상 revision을 볼 수 있습니다. publish는 차단됩니다. head 자격이 없는 사람에게 교체 draft UUID를 배포하지 않습니다. | 작성자 외 draft 열람에도 기존 head 자격을 적용하고, 새 원천은 보이지만 기존 head는 숨긴 reviewer의 packet·publish가 모두 404인지 실제 서비스 회귀로 검증 |
| 2. 독자별 관계 분류 차이 | 현재 독자의 허용 관계 전체를 분류에 반영하므로, 추가 RESTRICTED 관계를 볼 수 있는 상위 권한자가 기존 INTERNAL page를 못 볼 수 있습니다. 그 사람의 재컴파일로 원래 독자층이 좁아질 수 있습니다. shared 규정은 안정된 procedure 객체와 목적별 pack에 연결합니다. | 실제 사용한 link ID·hash·권한·분류 결속을 설계하고, 병렬 저분류/고분류 관계에서 독자별 숨김·복구·원래 독자층의 결과를 고정 평가 |
| 3. action·상태 변경 뒤 Wiki 숨김 | 객체 전체 hash는 status·version도 포함합니다. `mark_reviewed`나 rollback만으로도 해당 객체에 anchor한 page가 숨겨질 수 있습니다. action 완료·rollback을 Wiki 영향 대조 사건에 포함하고 lint의 `object_changed`를 확인합니다. | 실제 HTTP·CLI에서 Wiki 게시→action 승인/실행→숨김·lint→재컴파일/게시→rollback까지 결합 회귀; 상태 의존 page와 안정된 procedure page의 정책 구분 |
| 4. 데모의 자기검토 증거 | `self_review_blocked=true`는 작성자의 검토 시도가 거절됐다는 관찰입니다. 현재 데모 작성자는 APPROVE가 없어 사람 독립성 분기까지 도달하지 않습니다. 같은 실제 사람의 alias 차단은 별도 단위 테스트 범위입니다. | READ·MANAGE_KNOWLEDGE·APPROVE를 모두 가진 HUMAN 작성자와 같은 person의 다른 subject를 실제 server registry에 등록해 각각 거절되는 통합 회귀 |
| 5. 오류 코드와 lint 신원 문서 정정 | raw 적격성 상실은 `wiki_source_stale` 409 또는 숨김 404이며, 항상 `wiki_recompile_required`는 아닙니다. lint는 READ+MANAGE_KNOWLEDGE와 목적·원천/head 자격을 검사하며 actor kind로 HUMAN만 제한하지 않습니다. compile과 독립 publish의 HUMAN 요건은 유지됩니다. | 운영 오류 표와 lifecycle 서식을 코드에 맞게 정정하고, raw role·retire·분류 변경과 HUMAN/SERVICE lint·compile의 결과를 대조 |
| 6. publish 권한 실패 코드 | proposer·reviewer와 원천·객체 분기 사이의 404·409 투영이 일관되지 않습니다. 권한 축소 시 409도 정상 데이터 변경으로 처리하며 자동 재시도·임의 revision 추측을 하지 않습니다. | reviewer 자신의 현재 권한 실패를 404로 통일하고, 두 사람 각각의 원천·객체 권한 회수를 잘못된 review hash와 함께 회귀 검증 |
| 7. ACL snapshot metadata | page·query에는 source/object ACL snapshot이 포함되어 독자가 가입하지 않은 group 이름도 보일 수 있습니다. ACL 이름·사람 ID를 보안·개인정보 재고에 포함하고 외부 공유/export의 대상 독자를 제한합니다. | 일반 독자 응답과 검토 packet 투영을 분리해 hash·필요 최소 metadata만 제공하고, 본문은 볼 수 있으나 다른 group 이름은 숨긴 독자의 응답을 검증 |
| 8. 생성 인용·관계 purpose 회귀 | 같은 문서를 두 번 인용한 모델 결과는 422입니다. 한 문서당 한 인용 계약을 지키도록 실제 모델을 평가합니다. 새 링크 회귀는 group 회수를 다루며 purpose 회수의 전용 회귀는 없습니다. | 동일 문서의 여러 quote 처리 계약을 정해 실제 모델·wire를 평가하고, link의 purpose만 회수해 draft·publish·page/index/query/lint/export가 차단되는 회귀 추가 |

위 권고에 따라 코드를 바꾸면 현재 PASS를 새 코드에 적용하지 않습니다. 새 source manifest, 관련 실패 반례→수정→전체 실행·설치 검증, 독립 검토와 Opus 재감사를 수행합니다. [회사 gold set 서식](../templates/wiki/company-gold-set.md)에는 숨긴 평가 case와 작성자·검토자와 분리된 현업 채점자를 사용합니다.

## 회사 적용의 완료 경계

현재 링크 회귀는 실제 Store·WikiService에서 template 변경을 주입한 정책 로직 검증입니다. 운영 runtime은 pack hash guard로 임의 변경을 거부하므로 실제 온톨로지 관계·분류 변경에는 별도의 버전 이전 절차를 검증해야 합니다. 관계 변경의 자동 stale 기록·재컴파일 queue와 source watcher는 구현 범위 밖입니다.

기업 IdP·업무 connector, 실제 hosted/local 모델 품질, DLP·반출·공급자 보존/리전 계약, 목표 부하, KMS·HA/RLS, 외부 감사 서명, WAL·백업·다운로드 사본의 물리 삭제, 의미 entailment와 업무 KPI/ROI는 회사의 데이터·인프라·담당자와 검증합니다. 이 스타터팩의 회사 적용은 현재 코드의 검증 결과, 위 알려진 동작, 업종별 평가와 운영 책임을 함께 확인하는 단계부터 시작합니다.
