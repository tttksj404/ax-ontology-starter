# 회사 조건으로 시작하는 AX 도입

도입의 첫 결정은 업종명이 아니라 실제 업무, 데이터, 계약, 통신 조건입니다. `CompanyProfile + BusinessIntake` 진단은 입력을 결정적으로 분류합니다. `REPORTED`는 제출된 자기신고 상태이며 원천 진위, 현장 통제 작동 또는 보안 인증을 증명하지 않습니다. 가장 완전한 결과도 `pilot_review`이며 운영 승인이 아닙니다.

## 한 회사의 적용 단위

| 구성 | 담는 것 | 바뀌는 주기 | 최종 확인자 |
|---|---|---|---|
| 공통 코어 | 계약 binding, 권한 우선 검색, 제안·독립 human 승인·실행, SQLite 감사, 릴리즈 veto | 코드 릴리즈 | 개발·보안·운영 |
| 업종팩 `DomainPack` | 회사 용어, 객체·관계, 문서, 허용 행위, 분류와 접근 정책 | 규정·업무·원천 변경 | 현업·데이터 소유자 |
| 회사 보안 프로필 `CompanyProfile` | 관할, 배치, 최대 민감도, 전송·리전·모델·도구·보존·그룹 정책과 승인 | 정책·계약 변경 | 보안·개인정보·위험 책임자 |
| 증거팩 | 업무 인터뷰, 원천·데이터 계약, gold set, dry run·shadow 결과, 위험·모델 계약 검토, 릴리즈 기록 | 매 평가·승격 | 현업 검토자·운영 책임자 |

공통 코어가 같아도 회사 보안 프로필과 증거팩이 다르면 배치와 자동화 수준은 달라집니다. 업종 표준을 사용하더라도 회사 원천 필드와 판단 규칙을 별도로 승인합니다.

회사 보안 프로필에는 인증 모드(`opaque_only`/`jwt_only`/`both`), 사람과 서비스 주체의 매핑, 모델 반출 등급 하한, 하한 변경 근거도 포함합니다. v0.2의 기본 모델 질의 하한은 `RESTRICTED`이며, 낮추려면 검증된 통신 경로와 회사 분류·반출 정책이 필요합니다.

## 적용하기 좋은 업무와 높은 검토가 필요한 결정

| 분야 | 시작 후보 | 필요한 분야 객체·근거 | 더 높은 검토가 필요한 결정 |
|---|---|---|---|
| 제조·유통 | 구매요청 점검, 정비 문서 검색, 품질 이상 정리 | 자재·설비·작업지시·검사·절차·공급사 | 설비 구동, 안전 판정, 발주·지급 |
| B2B·서비스 | 문의 분류, 담당자 배정 초안, 답변 근거 검색 | 고객·문의·계약·제품·SLA·지식 문서 | 고객 발송, 환불, 계약 변경 |
| 재무·회계 | 증빙 누락, 정산 불일치 후보, 내부 규정 질의 | 거래·증빙·계정·정산·규정·승인 | 자금 이동, 장부 확정, 신용·투자 판단 |
| 인사·교육 | 서류·교육 상태 점검, 사내 규정 안내 | 구성원·서류·교육·정책·필수 요건 | 채용·평가·징계, 급여 변경 |
| 공공·전문 서비스 | 접수 요건, 기록 검색, 보고서 초안 | 신청·사건·기록·요건·담당자·근거 | 권리 부여·박탈, 최종 처분·전문 판단 |
| 의료·연구 지원 | 비임상 문서, 장비 문서·연구 기록 검색 | 문서·장비·실험·승인·버전·절차 | 진단·치료, 임상 안전, 연구 윤리 승인 |

저장소의 구매·고객지원·입사서류 예제는 합성 데이터입니다. 그 밖의 행은 설계 후보이며 현장 적합도나 생산성을 검증한 결과가 아닙니다.

## 네 배치는 실제 데이터와 통신 조건으로 고른다

| 모드 | 선택 조건 | 모델 통신 | 함께 확인할 것 |
|---|---|---|---|
| `offline` | 모델 호출 없이 권한 검색·인용·결정적 규칙으로 충분 | 없음 | 배포물 반입, 로컬 로그·백업, 검색 품질 |
| `private` | 승인된 사내·전용 모델 종단이 있고 데이터가 그 경계 안에 머물러야 함 | 회사가 통제하는 종단 | GPU·모델 해시, 양자화 품질, 패치, 용량, 네트워크·로그 |
| `gateway` | 외부 모델 사용이 허용되고 게이트웨이·공급자 계약이 전송·리전·보존 조건을 충족 | 승인된 HTTPS 게이트웨이 | 인증, host allowlist, DLP, rate limit, 공급자·하위 처리자·로그 계약 |
| `hybrid` | 데이터 분류나 업무 단계에 따라 로컬·외부 경로를 분리해야 함 | 정책이 허용한 경로만 | 분류 오류, 자동 우회 금지, 경로별 평가·감사·장애 처리 |

개인정보, 의료, 금융이라는 이름만으로 무조건 on-premises를 요구하지 않습니다. 반대로 게이트웨이가 있다는 이유만으로 외부 전송을 허용하지도 않습니다. 실제 원문, OCR 결과, 임베딩, 캐시, 프롬프트·응답 로그, 도구 입력까지 분류하고 계약과 관할을 확인합니다.

## 업무 한 건을 끝까지 인터뷰한다

정상 사례뿐 아니라 누락, 예외, 반려, 중복, 긴급 사례를 포함해 한 사건이 들어와 끝날 때까지 따라갑니다. [업무 발굴 프롬프트](../templates/workflow-discovery.md)로 초안을 만들고 현업이 확인한 뒤 계약에 넣습니다.

| 질문 | 계약 위치 | 보류 조건 |
|---|---|---|
| 무엇이 완료이며 누가 책임지는가 | `business`, `objective`, `process_owner` | 책임자·완료 조건 미확인 |
| 단계별 입력·출력·인계는 무엇인가 | `steps`, `inputs`, `outputs`, `depends_on` | 선행 단계·소유자 미확인 |
| 어떤 규칙과 최신 근거로 판단하는가 | `rules`, `evidence_sources`, 문서 version/hash | 출처·버전·담당자 미확인 |
| 예외·재작업·수동 판단은 언제인가 | `exceptions`, 이벤트 로그 | 예외가 평가셋에 없음 |
| 원천·권한·민감도·삭제 책임은 누구인가 | `DataContract`, `access`, `lifecycle` | 계약·ACL·보존 미확인 |
| 돈·권리·안전이 바뀌며 되돌릴 수 있는가 | `risk`, `decision_impact`, `reversible` | 영향·복구 미확인 |
| 값은 관측·문서·진술·미확인 중 무엇인가 | `evidence_status`, `value_status` | 진술을 관측으로 승격 |

단계 의존은 DAG입니다. 반려 루프는 순환 의존으로 만들지 않고 예외와 이벤트 로그의 재방문으로 기록합니다.

## 도입 진단을 읽는 법

`POST /v1/onboard`는 요청된 배치·민감도·전송·리전·모델·도구·그룹을 회사 프로필과 비교합니다. 결과의 의미는 다음과 같습니다.

| 결과 | 의미 | 다음 행동 |
|---|---|---|
| `blocked` | 핵심 정책·근거가 미확인이거나 명시적 충돌·반려가 있음 | 충돌 해결과 근거 수집 전 중단 |
| `on_hold` | 핵심 차단은 없지만 정보·승인·현장 증거가 남음 | 책임자와 승인 범위를 채움 |
| `pilot_review` | 입력 계약상 제한 파일럿을 검토할 수 있음 | 통제된 실데이터 dry run·현업 평가·운영 승인 |

특히 `ProfileEvidence.region_policy`, `model_policy`, `tool_policy`가 `UNKNOWN`이면 각각 `region_policy_evidence_unknown`, `model_policy_evidence_unknown`, `tool_policy_evidence_unknown` 이유를 남기고 `blocked`로 판정합니다. 다른 핵심 정보·근거의 `unknown`도 허용으로 해석하지 않습니다. `REPORTED`는 해당 누락을 자기신고로 채울 수 있지만 진위 확인 단계로 승격하지 않습니다.

응답의 `assurance=self_reported_readiness`, `live_validated=false`, `security_certified=false` 경계는 완전한 입력에서도 유지됩니다.

## 도입 산출물과 비용

업무 하나마다 다음을 남깁니다.

- 업무 책임자, 데이터 소유자, 위험 수용 책임자와 성공·중단 기준
- 회사 보안 프로필과 [위험·관할·데이터 검토서](../templates/risk-data-review.md)
- 서버 등록 `DataContractRegistry`, 원천 버전·해시·ACL·수명주기·대조 정책
- tenant가 `acme`라면 `acme.<점이 없는 접미부>`처럼 tenant prefix를 고정한 managed 문서 ID와 신뢰 가능한 할당자
- managed 문서의 contract ID/version/hash binding, source 관측시각과 수락 version history
- 변경 문서만 담는 delta snapshot 규칙과 누락을 삭제로 해석하지 않는 명시적 retire/tombstone 절차
- 기존 문서 변경 주체의 저장 ACL tenant/group/clearance 범위와 계약의 `READ+AUDIT+MANAGE_KNOWLEDGE` 권한
- 업종팩과 정상·예외·거부·권한·삭제를 포함한 gold set
- [모델·게이트웨이 계약 검토서](../templates/model-contract-review.md)와 모델·온톨로지·도구 릴리즈 기록
- dry run, shadow, 단계 승격, 중단·되돌리기와 백업 복원 기록

비용은 모델 호출·GPU·저장소 외에 현업 검수, 오류 재작업, 데이터 정리, 평가셋 유지, 보안·개인정보 검토, 관측, 장애 대응, 공급자·게이트웨이 운영을 포함합니다. 처리시간 감소를 검수·재작업·운영비가 빠진 실제 절감액으로 표현하지 않습니다.

`knowledge state`는 전체 tenant 재고가 아니라 호출자의 등급·그룹과 감사 목적, 현재 관리 가능한 계약으로 제한된 운영 화면입니다. retire와 tombstone 메타데이터는 변경 직전 ACL snapshot을 계속 적용하며, ACL을 알 수 없는 legacy 메타데이터는 노출하지 않습니다. 전체 재고 대조가 필요하면 별도의 통제된 관리자 보고 절차를 설계합니다.

계약 관리 권한만으로 기존 문서 전체를 바꿀 수 있는 것은 아닙니다. upsert, retire, tombstone, ACL 변경은 저장 ACL snapshot의 tenant, group, clearance도 만족해야 하며 ACL을 알 수 없거나 이 범위를 벗어난 기존 문서는 동일한 404로 거부합니다. 이 쓰기 검사는 문서 ACL의 purpose를 적용하지 않지만, 계약 자체의 `READ`, `AUDIT`, `MANAGE_KNOWLEDGE` 검사는 유지합니다. 따라서 state에서 숨은 모든 문서가 항상 쓰기 불가라고 일반화하지 않고, 숨은 이유와 쓰기 ACL을 따로 검토합니다. 다만 같은 tenant의 upsert는 미사용 ID의 생성 성공과 이미 사용 중인 비가시 ID의 404가 달라 ID 사용 여부를 추론할 수 있습니다. 문서 ID에는 고객명·사건명 같은 민감한 의미를 넣지 않고, 신뢰 가능한 할당자를 두며 계약별 접미부 규칙이나 더 강한 격리가 필요하면 tenant별 DB를 검토합니다.

managed upsert는 조회 전에 문서 ID의 마지막 점 앞부분이 계약 tenant와 정확히 같고, 접미부가 비어 있지 않으며 점을 포함하지 않는지 검사합니다. 위반은 실제 ID 존재 여부와 무관하게 `data_contract_violation` 422입니다. 이 규칙은 managed upsert에 적용되며 bootstrap·읽기 ID와 v0.1 역사 기록을 바꾸지 않습니다. 기존 unqualified managed ID는 자동 rename하지 않고 upsert를 거부합니다. 현재 binding과 저장 ACL 권한이 있는 retire/tombstone 정리는 유지하되, ID와 accepted source-version history를 옮기는 일은 승인된 migration으로 수행합니다. 다중 tenant 운영 전에는 legacy·bootstrap ID의 실제 owner와 prefix를 재고 대조해, 예를 들어 acme 소유 행이 `beta.doc`처럼 보이는 충돌을 통제된 migration으로 해소합니다. 이 규칙을 entity, action, object나 일반 ontology ID 전체의 namespace 보장으로 확대하지 않습니다.

ACL 변경 권한은 단순 메타데이터 편집 권한이 아닙니다. 저장 ACL을 만족하는 계약 관리자는 계약이 허용한 범위에서 groups, purposes, 민감도를 넓히거나 줄일 수 있고, purpose 추가는 이후 본문 읽기 범위를 넓힐 수 있습니다. 회사가 위임 범위와 승인자를 정하고 변경 기록을 검토해야 합니다. 계약을 registry에서 제거하면 그 계약 ID를 통한 API 정리도 할 수 없으므로, 제거 전에 보존을 확인해 retire/tombstone합니다. 이미 제거했다면 같은 tenant/source/contract ID를 통제해 재등록한 뒤 drift tombstone으로 정리합니다. `delete_within_hours`와 원천·백업의 실제 삭제는 회사와 원천 담당자의 별도 책임입니다.

managed 신규 upsert와 ACL 변경의 `access.groups`는 비어 있을 수 없습니다. 모든 그룹의 접근을 회수하려면 빈 ACL로 active orphan을 만들지 말고, 보존 판단에 따라 명시적 retire 또는 tombstone을 선택합니다. 공통 `Access`의 빈 그룹 deny-all 의미는 bootstrap 등 다른 용도에서 유지됩니다. 기존 개발 DB의 managed 빈 그룹·ACL 불명 행은 자동으로 권한을 복원하지 않고 숨김·404 상태로 두며, 담당자가 실제 회사의 보존·삭제 결정을 확인한 통제된 migration으로 정리합니다.

도입 전 확인표는 [v0.2 도입·운영 가이드](V02_GUIDE.md), 분야 심화 절차는 [업그레이드 가이드](UPGRADE_GUIDE.md)에 이어집니다.
