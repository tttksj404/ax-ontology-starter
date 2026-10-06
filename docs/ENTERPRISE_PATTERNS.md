# 기업 AX 형태와 설계에 반영한 원칙

2026-10-01에 공식 제품 문서·기업 발표·공급자 고객 사례를 확인했습니다. 다음 내용은 공개 자료의 운영 형태를 요약한 것이며 회사 내부 구성, 현재 품질·보안 수준 또는 우리 구현의 동등성을 증명하는 자료가 아닙니다. 운영 사례, 제품 제공 기능, 탐색 중인 방향을 구분합니다.

| 기업/제품 | 공식 자료에서 확인한 형태 | 이 팩에 반영한 결정 | 해석의 한계 |
|---|---|---|---|
| 삼성SDS FabriX | 복수 LLM 선택, 기본 클라우드와 하이브리드·온프레미스 제공; 기업 API 계약·보안 게이트웨이·필터·쿼터를 설명 | 모델별 업무/데이터 정책, 로컬/사내/클라우드 경로와 반출 승인, 공통 업무 자산 재사용 | 공급자의 제품 설명; 외부 유출 차단 등의 표현을 독립 보안 검증으로 취급하지 않음 |
| Morgan Stanley | 내부 지식 검색 Assistant와 회의 요약 Debrief를 구축; 전문가 평가·배포 전 테스트·일일 회귀를 설명 | read-only 근거 검색으로 시작, 현업 gold set, 도메인별 평가·반복 개선, 최종 결과 검토 | OpenAI가 게시한 고객 사례; 일반 모델 API에 동일한 보관 조건이 자동 적용된다는 의미 아님 |
| Airbus Skywise | Palantir와 항공 데이터 플랫폼을 구축하고 공급망으로 확장; 분야별 데이터와 전용 애플리케이션을 연결 | 공통 업무 객체·관계 위에 업종팩과 업무별 기능을 축적 | 특정 항공 데이터 플랫폼의 역사적 사례; 모든 기능이 LLM/RAG라는 의미 아님 |
| Siemens × NVIDIA | 제조 현장의 on-premises AI assistant를 RTX/NeMo와 함께 탐색한다고 발표 | 데이터가 현장을 벗어나기 어려운 업무의 로컬 경로, 영상/현장 데이터는 별도 확장 | 공개 표현은 탐색 단계; 전사 운영 완료 사례로 서술하지 않음 |
| Azure API Management AI gateway | 여러 AI 백엔드·에이전트·도구를 보안·관측·거버넌스 정책으로 관리하는 게이트웨이 기능 | OpenAI 호환 HTTPS 게이트웨이 인터페이스와 관리자가 정한 호스트 허용 목록 | 제품 역량 설명이며 실제 고객 배포 증거가 아님; 일부 통합 API는 preview로 명시 |

근거: [삼성SDS FabriX 공식 FAQ](https://www.samsungsds.com/kr/ai-fabrix/fabrix.html), [Morgan Stanley 평가 중심 도입 사례](https://openai.com/index/morgan-stanley/), [Airbus의 Skywise 공급사 확장 발표](https://www.airbus.com/en/newsroom/press-releases/2018-07-airbus-extends-skywise-to-suppliers), [Siemens–NVIDIA 공식 협력 페이지](https://www.siemens.com/en-us/company/artificial-intelligence/siemens-nvidia-partnership/), [Azure AI gateway 공식 기능 문서](https://learn.microsoft.com/en-us/azure/api-management/genai-gateway-capabilities).

Airbus는 2026년 4월에도 Navblue와 Skywise 디지털 서비스를 통합한 Skywise 자회사를 발표했습니다. 이는 과거 플랫폼이 분야 운영 서비스를 축적하며 확장하는 현재의 흐름을 보여줍니다. 통합 발표 자체를 우리 구현의 LLM 성능·보안·ROI 근거로 사용하지 않습니다. [Airbus 2026년 공식 발표](https://www.airbus.com/en/newsroom/press-releases/2026-04-airbus-unveils-skywise-subsidiary-integrating-navblue-and-skywise-digital-services-solutions).

## 회사의 모습에 따른 권장 출발점

| 회사 조건 | 출발 구조 | 먼저 검증할 것 |
|---|---|---|
| 자료의 외부 전송 자체가 금지 | offline 검색 → 폐쇄된 환경의 로컬 모델 | 모델 파일과 라이선스, 장비 접근, 업데이트 경로, 네트워크 차단, 해당 분야 품질 |
| 전용망·전용 클라우드와 공급자 계약이 가능 | 사내/전용 게이트웨이 → 승인된 모델 배포 | 전체 데이터 경로의 리전·보관·운영자 접근·텔레메트리, 사설 endpoint, 인증·쿼터 |
| 공개·내부 자료의 외부 처리를 승인 | 사내 게이트웨이 → frontier 모델 | 분류·DLP·계약·비용·인용과 의미 품질·실패 복구 |
| 여러 부서가 다른 보안 조건을 가짐 | 공통 온톨로지/정책 + 작업별 승인 모델 경로 | 등급별 데이터 분리, ACL 동기화, 캐시/인덱스/로그의 정책, 업무별 평가 |

위 권장은 공개 패턴과 이 팩의 보수적 경계를 토대로 한 설계 판단입니다. 특정 기업이 이 코드와 같은 구성으로 운영한다는 주장이 아닙니다. GPU 서버가 있다고 로컬 모델의 정확성이 보장되거나, 클라우드 게이트웨이가 있다고 학습 제외·무보관·데이터 상주가 자동 보장되지는 않습니다.

## 모델보다 오래 남아야 하는 자산

업무 객체와 식별자, 판단 규칙과 예외, 자료의 출처·효력·권한, 현업 정답 평가셋, 승인/실행 계약, 실패 복구 절차가 회사의 누적 자산입니다. 모델은 이 자산 위에서 교체합니다. 모델마다 같은 평가셋과 보안 조건을 통과해야 하며, 자동 fallback이 다른 데이터 반출 경로를 만들지 않도록 합니다.

온톨로지 설계 근거는 [Palantir Ontology](https://www.palantir.com/docs/foundry/ontology/overview)와 [Ontology-augmented generation](https://www.palantir.com/docs/foundry/ontology/ontology-augmented-generation)입니다. 공통 코어가 여러 업무를 받더라도 분야 규칙·식별자·예외·평가 없이 전문성이 생기지는 않습니다.
