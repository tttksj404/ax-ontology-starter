# 설계 자료 목록과 적용 경계

기준일은 2026-10-02입니다. 표준 본문, 공식 제품 문서, 법령·감독기관 자료, 원 논문·공식 저장소, 당사자 기업의 공개 사례 페이지를 직접 확인해 설계 판단의 출처와 적용 경계를 나눴습니다. 표준, 제품 문서, 공개 사례, 연구 결과는 증거의 성격이 다릅니다. 링크가 있다고 해서 해당 기술이 이 저장소의 런타임 의존성이 되거나 이 프로젝트의 현장 성과가 입증되는 것은 아닙니다.

이 표의 자료 상태와 런타임의 `SourceStatus`는 다른 분류입니다. 런타임에서 `REPORTED`는 제출자 자기신고이고 원천 진위·현장 통제 작동을 검증하지 않습니다. region/model/tool 정책 근거의 `UNKNOWN`은 도입 진단을 `blocked`로 만듭니다. 아래 공식 자료를 인용해도 그 상태가 자동으로 관측·문서 검증 또는 보안 인증으로 승격되지는 않습니다.

## LLM Wiki와 지속 지식

| 자료 | 종류·상태 | 이 프로젝트에 적용한 원칙 | 실무 검증 경계 |
|---|---|---|---|
| [Karpathy: LLM Wiki 원안](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | 당사자 공개 설계 메모, 2026-04-04 | 원문과 파생 Wiki를 분리하고 수집·질의·정비를 반복한다. 검토된 용어·절차·관계를 지속 저장한다. | enterprise 보안·업무 성과·모든 분야의 RAG 대비 우월성을 입증한 연구가 아니다. |
| [OWASP RAG Security](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html) | 공식 보안 지침 | 검색 전 권한, 원문 provenance, 파생 지식의 접근·오염·갱신 경계를 유지한다. | 현재 모델은 실제 적대적 보안 인증을 받지 않았다. |
| [OWASP LLM08 Vector and Embedding Weaknesses](https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/) | 공식 위험 분류 | 미래 벡터 검색에서도 tenant·ACL·삭제·검색 결과 무결성을 보존한다. | 현재 검색은 벡터/embedding 구현이 아니다. |
| [OWASP Agentic Top 10: ASI06](https://genai.owasp.org/download/52117/?tmstv=1765059207) | 공식 agentic 위험 자료 | 지속 memory와 knowledge 오염을 threat로 취급하고 Wiki를 원문·행위로 자동 승격하지 않는다. | marker 제거·원천 오등록·DB 전체 재작성의 기원을 인증하지 않는다. |
| [OWASP Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) | 공식 보안 지침 | 문서는 데이터로 다루고 도구 실행·반출·게시 결정을 엔진과 사람에 둔다. | 인젝션을 완전히 제거하거나 substring 검사로 의미 정확성을 증명하지 않는다. |

위 자료를 근거로 raw RAG + ontology + reviewed Wiki를 함께 제공하는 것은 이 프로젝트의 설계 판단입니다. 효과의 크기는 회사의 같은 조건 gold set으로 확인하며 원안의 추상 설계를 기업 벤치마크로 표현하지 않습니다. 실제 구현과 업종별 강화는 [LLM Wiki 가이드](LLM_WIKI_GUIDE.md)를 따릅니다.

## 온톨로지·데이터 계약·계보

| 자료 | 종류·상태 | 이 프로젝트에 적용한 원칙 | 실무 검증 경계 |
|---|---|---|---|
| [Palantir: Why create an Ontology?](https://www.palantir.com/docs/foundry/ontology/why-ontology) | 제품 개념 문서 | 데이터·논리·행위·보안을 한 업무 모델에 묶고, 실행 전 시나리오와 권한을 확인한다. | Palantir 제품·SDK·호환성을 구현했다는 뜻이 아니다. |
| [Palantir: Ontology-augmented generation](https://www.palantir.com/docs/foundry/ontology/ontology-augmented-generation) | 제품 방법론 | 검색 방법은 문서·질문 특성에 맞춰 단계적으로 확장하고 검색 실패를 먼저 측정한다. | 이 저장소는 현재 권한 우선 키워드·관계 검색이며 벡터·GraphRAG 품질을 주장하지 않는다. |
| [Palantir: Action consistency and isolation](https://www.palantir.com/docs/foundry/action-types/consistency-guarantees) | 제품 동작 문서 | 쓰기 전 현재 버전·계약·저장 ACL과 충돌을 다시 확인하고 원자적 적용 범위를 명확히 한다. | SQLite 구현은 Foundry의 격리 수준이나 외부 부작용 원자성을 제공하지 않는다. tombstone의 version/hash drift cleanup은 이 프로젝트의 제한된 삭제 정책이다. |
| [Palantir: Object edit schema migrations](https://www.palantir.com/docs/foundry/object-edits/schema-migrations) | 제품 운영 문서 | 깨지는 스키마 변경은 마이그레이션과 복구 계획을 먼저 둔다. | 이 프로젝트의 자동 마이그레이션은 v0.1 단일 SQLite를 v0.2 지식 테이블로 올리는 제한된 경로다. |
| [W3C PROV-O](https://www.w3.org/TR/prov-o/) | W3C Recommendation | 원천, 생성·변경 활동, 책임 주체를 분리해 출처를 표현한다. | 현재 JSON 계약은 PROV-O 직렬화나 RDF 상호운용을 보장하지 않는다. |
| [W3C OWL 2 Overview](https://www.w3.org/TR/owl2-overview/) | W3C Recommendation | 업종 개념·관계의 기계 판독 가능한 의미 모델을 장기 확장 후보로 둔다. | 현재 `DomainPack`은 OWL 추론기나 OWL 적합 구현이 아니다. |
| [W3C SHACL](https://www.w3.org/TR/shacl/) | W3C Recommendation | 그래프 제약과 검증 결과를 분리하는 설계 원칙을 참고한다. | 현재 검증은 Pydantic과 코드 불변식이며 SHACL 엔진을 포함하지 않는다. |
| [ODCS 3.0.0](https://bitol-io.github.io/open-data-contract-standard/v3.0.0/home/) | Linux Foundation 계열 공개 표준 | 생산자·소비자 계약에 소유자, 스키마, 품질, SLA, 서버 정보를 함께 두는 관점을 반영한다. | `DataContractRegistry`는 원천·범위·ACL·수명주기·출처 해시의 최소 부분집합이다. 단일 파일 import는 변경 문서 delta이며 전체 source reconciliation이 아니다. ODCS 호환을 주장하지 않는다. |
| [OpenLineage facets](https://openlineage.io/docs/spec/facets/) | 오픈 사양 문서 | 실행·작업·입력·출력 메타데이터를 나누고 확장 필드의 충돌을 피한다. | 현재 감사 기록은 OpenLineage 이벤트를 발행하지 않는다. 계보 백엔드 도입 시 별도 매핑과 유실 검증이 필요하다. |

## 위험·인증·AI 보안

| 자료 | 종류·상태 | 이 프로젝트에 적용한 원칙 | 실무 검증 경계 |
|---|---|---|---|
| [NIST AI RMF 1.0](https://www.nist.gov/itl/ai-risk-management-framework) | 자발적 위험관리 프레임워크, 개정 진행 중 | 거버넌스·맥락 파악·측정·관리를 릴리즈 전후 반복한다. | 적용 선언만으로 규제 준수나 안전 인증이 되지 않는다. |
| [NIST AI 600-1 GenAI Profile](https://www.nist.gov/itl/ai-risk-management-framework/ai-risk-management-framework-resources) | NIST GenAI 프로필 | 생성형 AI의 근거성, 오용, 개인정보, 공급망 위험을 평가셋과 운영 통제에 연결한다. | 체크리스트는 위협 모델·레드팀·현장 위해성 평가를 대체하지 않는다. |
| [NIST SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final) | NIST 최종 특별간행물 | 네트워크 위치만 신뢰하지 않고 요청마다 주체·자원·정책을 확인한다. | 이 참조 런타임은 완성된 Zero Trust Architecture가 아니다. 기기 신뢰·PDP/PEP·네트워크 통제는 외부 범위다. |
| [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html) | IETF Best Current Practice | OAuth 배포에서는 발급자 혼동, 토큰 탈취·재생, 리다이렉트와 키 회전을 별도 통제로 다룬다. | v0.2는 고정 JWKS 기반 RS256 access token 검증만 제공한다. authorization code, PKCE, refresh token, DPoP/mTLS, 로그인 UI는 없다. |
| [MCP 2026-07-28 release](https://blog.modelcontextprotocol.io/posts/2026-07-28/) | MCP 공식 릴리스 설명 | 발급자 검증, 발급 서버별 자격증명 분리, 최소 도구 권한과 게이트웨이 관측을 향후 도구 연동 검토 항목으로 둔다. | 이 저장소는 MCP 서버·클라이언트를 구현하지 않는다. MCP 릴리스 준수 주장이 아니다. |
| [OWASP LLM Top 10 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) | OWASP 커뮤니티 가이드 | 프롬프트 인젝션, 민감정보 노출, 과도한 권한, 공급망과 출력 처리 위험을 위협 시나리오로 관리한다. | 목록 적용만으로 침투시험이나 보안 보증이 되지 않는다. |
| [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/) | OWASP 커뮤니티 가이드 | 도구·기억·에이전트 간 신뢰와 자율 실행 범위를 최소화한다. | 현재 모델 출력에는 실행 도구가 연결되지 않는다. 향후 도구 추가 시 새 위협 모델이 필요하다. |
| [개인정보위 생성형 AI 개인정보 처리 안내서 발표](https://pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS074&mCode=C020010000&nttId=11410) | 대한민국 감독기관 안내, 2025-08-06 | 목적·데이터 출처·적법 근거·생애주기 안전조치·정보주체 권리와 CPO 거버넌스를 검토한다. | 프로젝트의 기술 통제는 법률 검토, 개인정보 영향평가, 국외이전·위탁 검토를 대신하지 않는다. |
| [인공지능기본법 제33조](https://law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1031810895) | 대한민국 법령, 2026-07-21 시행 | 제공하려는 서비스가 고영향 인공지능인지 사전에 검토하고 필요하면 확인 절차를 밟는다. | 코드가 고영향 여부를 자동 판정하지 않는다. 관할·용도별 법무 판단이 필요하다. |

## 운영·평가·모델 인프라

| 자료 | 종류·상태 | 이 프로젝트에 적용한 원칙 | 실무 검증 경계 |
|---|---|---|---|
| [Azure Foundry RAG evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rag-evaluators) | 제품 평가 문서, 일부 평가기 preview | 검색과 생성의 품질을 분리하고 ground truth가 필요한 지표를 구분한다. | Azure 평가기를 의존성으로 추가하지 않는다. 평가기 자체의 편향과 현업 일치도를 확인해야 한다. |
| [Azure API Management AI gateway](https://learn.microsoft.com/en-us/azure/api-management/genai-gateway-capabilities) | 제품 문서, 일부 기능 preview | 인증, 할당량, 회로 차단, 관측, 모델 백엔드 자격증명을 중앙 통제로 둘 수 있다. | 게이트웨이 사용만으로 반출·리전·보관·하위 처리자 조건이 충족되지 않는다. 현재 구현은 특정 Azure 제품에 연결되지 않는다. |
| [Azure AI Search document deletion](https://learn.microsoft.com/en-us/azure/search/search-how-to-delete-documents) | 제품 운영 문서 | 소스 soft-delete와 인덱스 삭제의 순서, 권한, 삭제 확인을 별도 운영 절차로 둔다. | v0.2 tombstone은 로컬 논리 삭제다. 원천, 검색 서비스, 임베딩, WAL, 백업, 공급자 로그의 물리 삭제 증명이 아니다. |
| [Temporal Activities](https://docs.temporal.io/activities) | 워크플로 제품 문서 | 외부 부작용은 재시도될 수 있으므로 멱등성과 체크포인트를 갖춘 활동으로 설계한다. | Temporal은 의존성이 아니다. 현재 지식 변경은 SQLite 트랜잭션과 요청키로 제한된 재시도 안전성을 제공하며, replay 응답 문서 목록은 현재 권한 투영이라 byte 동일성을 약속하지 않는다. |
| [OpenTelemetry GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) | OpenTelemetry 개발 상태 규약 | 검색·모델 호출의 지연, 토큰, 공급자와 실패를 표준화할 후보로 검토한다. | 속성 이름과 안정성이 바뀔 수 있다. 질문·프롬프트·검색문은 민감정보일 수 있어 기본 원문 로깅을 금지한다. |
| [MLflow GenAI evaluation](https://mlflow.org/docs/latest/genai/eval-monitor/index.html) | 오픈소스 제품 문서 | 버전된 평가 데이터, 사람 피드백, 코드 기반 지표와 모델 심판을 구분한다. | MLflow는 현재 의존성이 아니며 LLM 심판 결과만으로 릴리즈하지 않는다. |
| [vLLM quantization](https://docs.vllm.ai/en/latest/features/quantization/) | 오픈소스 제품 문서 | 로컬 모델 후보는 양자화 방식·하드웨어 호환·품질·처리량을 함께 측정한다. | 양자화가 곧 비용·품질 개선을 보장하지 않는다. 실제 GPU와 모델별 재평가가 필요하다. |
| [Ollama cloud models](https://docs.ollama.com/cloud) | 공식 제품 문서 | Ollama 앱·CLI가 cloud model을 지원하므로 loopback endpoint만으로 로컬 추론을 가정하지 않는다. | cloud 기능 지원 사실은 현재 회사 backend가 원격 실행 중이라는 증거가 아니다. runtime 설정·로그와 네트워크를 직접 확인한다. |
| [Ollama cloud 기능 비활성화](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features) | 공식 제품 운영 문서 | `server.json`의 `disable_ollama_cloud: true` 또는 `OLLAMA_NO_CLOUD=1` 적용 후 서버를 재시작하고 로그의 `Ollama cloud disabled: true`를 확인한다. | 설정과 로그 확인만으로 무반출·회사 보안 인증이 되지 않는다. OS/container outbound deny와 DNS·proxy·tunnel·패킷 검증을 별도로 수행한다. |
| [Google SRE launch checklist](https://sre.google/sre-book/launch-checklist/) | 공개 운영 지침 | 용량, 실패, 백업·복구, 보안 검토, 반복 빌드, canary, 단계 배포와 되돌리기를 출시 조건으로 둔다. | 체크리스트 완료는 이 프로젝트의 출시 검증 결과가 아니다. 실제 서비스 부하와 복구 훈련이 필요하다. |

## 공개 도입 사례와 연구

| 자료 | 종류·상태 | 참고한 패턴 | 해석 제한 |
|---|---|---|---|
| [Morgan Stanley](https://openai.com/index/morgan-stanley/) | 공급자 게시 고객 사례 | 전문가 골드셋, 배포 전 평가, 일일 회귀, 사람이 결과를 검토하는 지식 검색부터 시작한다. | 공개 수치와 보관 조건은 해당 고객·계약의 주장이다. 이 프로젝트 성과나 일반 조건으로 전용하지 않는다. |
| [Klarna](https://openai.com/index/klarna/) | 공급자 게시 고객 사례 | 고객지원처럼 대량 반복 업무도 만족도·재문의·처리시간·비용을 함께 본다. | 기업 자체 보고 수치다. 인력 대체나 이익 개선을 본 프로젝트의 예상치로 사용하지 않는다. |
| [Siemens × Microsoft](https://press.siemens.com/global/en/pressrelease/siemens-and-microsoft-scale-industrial-ai) | 기업 보도자료 | 제조 지식과 현장 도구를 결합할 때 도메인 전문가와 산업 환경 검증이 필요하다. | 보도자료의 이용 기업·사용자 수는 독립 효과 평가가 아니다. 이 저장소는 산업 Copilot이나 PLC 연결을 제공하지 않는다. |
| [Samsung SDS FabriX/Brity Copilot 공개 사례](https://www.samsungsds.com/la/news/real-240903.html) | 기업 보도자료 | 기업 데이터·모델·업무 도구를 통제된 플랫폼으로 묶는 운영 패턴을 참고한다. | 특정 제품의 보안·생산성 주장과 이 참조 구현의 능력을 동일시하지 않는다. |
| [GraphRAG 논문](https://arxiv.org/abs/2404.16130) | 연구 논문 | 전체 말뭉치의 주제 종합 같은 global query는 그래프·커뮤니티 요약 후보가 될 수 있다. | 논문은 특정 데이터·질문군 결과다. 모든 질의에서 일반 RAG보다 우월하다고 쓰지 않는다. |
| [microsoft/graphrag](https://github.com/microsoft/graphrag) | 연구 중심 오픈소스 | 필요할 때 작은 자료로 비용·검색 실패 유형을 비교한 뒤 도입한다. | 저장소가 밝히듯 공식 지원 제품이 아니며 인덱싱 비용과 변경 가능성이 있다. 현재 의존성으로 추가하지 않는다. |
| [HBS/BCG: Jagged Technological Frontier](https://aiinstitute.hbs.edu/navigating-the-jagged-technological-frontier/) | 현장 실험 연구 | AI 효과가 과업별로 들쭉날쭉하므로 전체 직무 평균보다 단계·예외별 평가가 필요하다. | 연구 참가자·과업의 결과를 다른 조직의 생산성 예측으로 옮기지 않는다. |
| [Google Cloud: GenAI KPI](https://cloud.google.com/transform/gen-ai-kpis-measuring-ai-success-deep-dive) | 공급자 실무 가이드 | 모델 품질, 시스템 품질, 채택, 업무 결과, 비용을 나눠 측정한다. | 시간 절감은 검수·재작업·교육·운영비를 반영하기 전에는 실제 비용 절감이 아니다. |

## 업종 어휘의 시작점

| 자료 | 상태 | 사용할 수 있는 범위 | 확인해야 할 것 |
|---|---|---|---|
| [EDM Council FIBO](https://spec.edmcouncil.org/fibo/index.html) | 금융 비즈니스 온톨로지, OWL·OMG 표준화 | 금융 용어·관계의 후보 사전 | 적용 관할, 상품·회계·규제 범위, 사용 릴리즈와 현업 승인 |
| [HL7 FHIR R5](https://hl7.org/fhir/) | HL7 의료 데이터 교환 표준, R5 일부 콘텐츠는 Trial Use | 의료 자원·문서 교환 구조의 후보 | 국가별 프로파일, R5 성숙도, 임상 안전·개인정보·상호운용 시험 |
| [OPC UA Part 1](https://reference.opcfoundation.org/specs/OPC-10000-1) | OPC Foundation 산업 상호운용 표준 | 설비 정보 모델·서비스·보안 개념의 후보 | 장비 프로파일, companion specification, 인증서·네트워크·실시간 제약 |
| [GS1 EPCIS](https://ref.gs1.org/standards/epcis/) | GS1 공급망 가시성 이벤트 표준 | 공급망 사건·대상·위치·시간 모델의 후보 | 적용 버전, CBV, 파트너 호환, 식별자 품질, 이벤트 누락·중복 |

이 자료들은 분야팩 초안의 출발점입니다. 표준의 클래스를 그대로 복사하기 전에 회사 용어, 원천 필드, 실제 판단 규칙, 관할과 버전을 현업·데이터·법무 담당자가 함께 확인해야 합니다.
