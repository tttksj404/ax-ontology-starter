# 독립 Sol 검토: v0.3 LLM Wiki

판정: **PASS / CLEAR — 로컬 참조 구현 범위**. 검토자는 구현을 맡지 않은 `gpt-5.6-sol / xhigh` Architect였습니다. 읽기 전용 검토자가 제공한 최종 보고를 부모가 이 파일로 게시했습니다. 실제 Opus 정적 감사와 회사 운영 검증은 다른 범위입니다.

독립 검토는 객체/hops 범위 우회, lint의 과거 ACL 메타데이터 노출, stale 초안 replay, clearance downgrade replay, current server floor, 검토자의 draft 조회, superseded publish, 과거 revision 의존 원천의 과잉 삭제, 전체 모델 입력 provenance, 원격 이미지 export, 중복 links 입력을 직접 재현했습니다. 수정 뒤 해당 반례와 전체 회귀를 다시 실행했고 차단 이슈가 남지 않았습니다.

확인한 구조는 다음과 같습니다.

- 모델은 SQLite transaction 밖에서 호출하고 fresh clock·exact credential·원천·ACL·객체·계약·revision을 다시 검사합니다.
- 전체 raw 입력을 `input_citations`와 전체 JSON/본문/ACL/계약 hash의 `source_bindings`에 결속합니다. 출력 인용 subset과 구분합니다.
- 서로 다른 HUMAN reviewer가 전체 packet을 읽고 같은 payload hash를 게시합니다. READ-only, 서비스 actor, 같은 person, 권한 회수와 낮은 분류는 거부합니다.
- 모든 입력 object가 요청 scope 안에 있는 page만 검색하고 최종 인용은 최대 10개로 유지합니다. lint는 과거와 현재 ACL 모두 아래에서만 metadata를 제공합니다.
- source 변경과 Wiki invalidation은 같은 SQLite transaction입니다. 실제 종속 revision/draft만 scrub하고 독립적인 clean current head는 유지합니다.
- export는 비권위 snapshot이며 HTML과 모든 Markdown image 표기를 거부합니다. 알려진 derived 역할과 marker는 raw 재수집에서 제외합니다.
- 중복 link는 공개 입력 계약에서 422이며 정상적인 과거 publish retry는 superseded 409로 구분합니다.

실행 증거:

| 범위 | 실제 결과 | 원본 TQE artifact |
|---|---|---|
| 고위험 반례 묶음 | 22 passed | 독립 검토 실행 |
| Wiki 범위 | 69 passed | `20261002-165016653-38bd73d4` |
| 전체 회귀 | 394 passed | `20261002-165026256-c5e9b10f` |
| 격리 wheel | 실제 HTTP·CLI·재시작·원천 수명주기 통과, runtime 66개 | `20261002-165115129-6e03e168` |
| 현재 검사 source | 141개, hash 불일치 0 | `tested-source-manifest.json` |

Wiki 로그 SHA-256: `68371e32ca5128faf637e67c3f74f2f584ec27356709a6a386b3fa3e78009b75`.

전체 로그 SHA-256: `4af0f70f9819d19d43119126704ca49cb0ce9dbc83518b51a1cbe9e6a3d81501`.

검사 source manifest SHA-256: `159a6beab10384be3ec30e19872db692cf0e47e3ac153f4f9c71b0ad3ae49571`.

독립 실행 wheel SHA-256: `d3814aba58f36a07ab50f8fb91af292cb9769e44395fbfbe273e270fef5e8c1f`.

남은 경계는 실제 기업 운영에서 WATCH입니다. 의미·완전성·업무 효력을 자동 판정하지 않고 회사 gold set·현업 검토가 필요합니다. 정확한 model ID·system/prompt hash·provider 정책 버전은 현재 Wiki 기록에 저장하지 않습니다. marker 제거 후 거짓 raw 등록과 DB/audit 전체 재작성의 기원을 인증하지 않습니다. WAL·백업·다운로드 export의 물리 삭제와 회수, 실제 모델/IdP/기업 connector·KPI·ROI는 미검증입니다.

최초 v0.3 Opus 설계 호출의 timeout은 PASS가 아닙니다. 후속 설계/최종 정적 감사는 실제 응답과 별도 고정 manifest로 확인해야 합니다.
