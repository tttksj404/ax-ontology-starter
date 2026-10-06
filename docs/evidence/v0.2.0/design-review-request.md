# Opus 5.5 max 독립 설계 검토 요청

사용자 요청: 여러 업종에서 업무 전반을 진단하고 온톨로지 기반 RAG와 보안 프로필(로컬/사설/게이트웨이/혼합)을 사용해 AX할 수 있으며, 분야별로 강화·업그레이드할 수 있는 실제 스타터팩. 인터넷 조사 후 추가 개선을 실제로 수행하라고 승인했다. 최초부터 Opus 5.5 max 공동 설계·검증을 요구했다.

현재 v0.1은 Python 3.12, FastAPI/Pydantic frozen 계약, permissioned keyword/2-hop graph, 권한 필터 후 extractive citation, 선택적 quote-verified model draft, opaque credential -> server Principal(매요청 identity 파일 reload), 승인된 SQLite set_status/rollback, hash-chain 감사와 pack_hash 불일치 차단을 갖췄다. 외부 쓰기/IdP/vector 검색/전체 ingest·삭제 동기화는 미구현이다. 기존 감사·배포물은 보존한다.

이번 v0.2 최소 연결 범위:

1. CompanyProfile와 BusinessIntake를 결합한 결정적 도입 진단. 업종/회사/소유자/관할/배치·전송·등급·보존·허용 모델/도구·승인·현업평가 조건. unknown/누락은 제한 또는 차단. 결과는 입력에 따른 진단이며 보안인증·현장 검증으로 표현하지 않는다.
2. DataContract에 tenant/owner/source URI+identifier/version/허용 객체와 ACL/갱신·삭제·재대조를 명시. source snapshot 기반 읽기 전용 normalized JSON 커넥터가 문서를 계약과 대조한 후 관리 작업으로 승격한다. 원천 API·망 연결이 없으면 실제 기업 커넥터 검증이라 주장하지 않는다.
3. Document upsert/retire/tombstone/ACL 갱신을 SQLite transaction에 리비전·idempotency·감사와 저장. API 검색은 현재 문서 snapshot 사용. 인용을 참조한 대기 중인 승인 작업은 source/version/content hash/ACL/유효기간을 현재 상태로 재검증한다. 사용자/관리자/원천 계약은 tenant 경계를 지킨다. pack template와 기존 업무 state/proposal을 삭제하거나 임의 이관하지 않는다.
4. opt-in JWT access-token 신원 검증: 신뢰된 HTTPS issuer, API audience, pinned PUBLIC JWKS, RS256 allowlist, kid와 RSA 강도, signature/iss/aud/exp/iat/nbf/access-token typ at+jwt 검사. 토큰의 roles/tenant는 권한이 아니며 등록 issuer+subject의 서버 Principal만 사용한다. 기존 opaque 데모 방식 호환, 키·신원 등록 파일 매요청 reload, 임의 jku/jwk/x5u/crit/alg 및 네트워크 키 발견 금지. 실제 SSO 로그인 전체를 만들었다고 표현하지 않는다.
5. ReleaseGate는 고정 사례 결과/평가 기준/모델·프롬프트·데이터 버전/증거 해시/현업 검토자에 연결. 안전·권한·삭제 실패는 다른 점수로 상쇄 금지, synthetic은 실운영 준비로 승격 금지.
6. CLI/API 통합, 합성 시나리오, 업종팩 확장 방법·위험/개인정보 서식·모델/도구 운영/장애 대응·자료 목록·학습 다이어그램·동작 증거를 갱신한다. 실제 provider/ERP/IdP credentials 없이 환경 연결을 주장하지 않는다.

이 계획의 누락, 잘못된 신뢰 가정, tenant 누수, 문서 변경과 업무 state 결합, stale 승인·TOCTOU, 계약 권한 상승, JWKS 회전/ID token 오용, 평가 점수 오용, 과도한 추상화와 구현 순서를 공격적으로 검토해 주세요. 필요 수정은 재현 가능한 시나리오와 최소 인터페이스로 제시하세요. 표준 자료를 읽었다는 자체가 구현 보증은 아닙니다. 실제 코드나 테스트를 실행하지 못했으므로 실행 검증을 했다고 주장하지 마세요.

한국어로 답하고 DESIGN_ACCEPT / NEEDS_FIX / REJECT 판정을 명시하세요. 막아야 하는 문제와 조직 현장 검증에 남기는 경계를 나누고, 최종 감사에서 필수로 확인할 실패 사례를 제시하세요. 이 요청은 설계 검토이며 최종 구현 PASS를 대신하지 않습니다.
