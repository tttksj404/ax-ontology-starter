# 위험·관할·데이터 수명주기 검토서

이 문서는 의사결정 기록입니다. 빈칸과 `미확인`은 허용하지만 추정값으로 채우지 않습니다. 한 항목이라도 운영 조건을 바꾸면 검토자를 다시 지정하고 승인 범위를 갱신합니다.

상태를 쓸 때 `REPORTED`는 제출자 자기신고, `UNKNOWN`은 미확인으로 구분합니다. `REPORTED`를 원천 진위 확인·현장 통제 작동·보안 인증으로 바꾸어 적지 않습니다. region/model/tool 정책 근거가 `UNKNOWN`이면 현재 도입 진단은 `blocked`입니다.

## 1. 요청과 책임

- 검토 대상 업무·기능:
- 요청자 / 업무 책임자:
- 데이터 소유자:
- 위험 수용 책임자:
- 보안 / 개인정보 / 법무 검토자:
- 적용 국가·지역·산업 규제:
- 검토일 / 다음 재검토일:

## 2. 결정이 미치는 영향

| 질문 | 답변 | 근거 위치 | 상태 |
|---|---|---|---|
| 결과가 돈, 권리, 안전, 고용, 의료, 신용 또는 법적 지위를 바꾸는가? |  |  | 관측 / 문서 / 진술 / 미확인 |
| 최종 판단자는 누구이며 어떤 화면·기록을 확인하는가? |  |  |  |
| 잘못된 결과를 중단·되돌리거나 보상할 수 있는가? |  |  |  |
| 고영향 인공지능 여부를 누가 검토했는가? |  |  |  |
| 자동 실행 상한과 항상 사람에게 넘길 조건은 무엇인가? |  |  |  |

## 3. 데이터와 관할

| 항목 | 내용 | 증거 / 승인자 |
|---|---|---|
| 개인정보·민감정보·영업비밀 범주 |  |  |
| 수집 목적과 적법 근거 |  |  |
| 원천 시스템과 원천 기록 식별자 |  |  |
| managed 문서 ID namespace·비민감 접미부·신뢰 가능한 할당자 | `<tenant>.<점 없는 접미부>` |  |
| 허용 사용자·그룹·목적 |  |  |
| 처리 지역·저장 지역 |  |  |
| 위탁자·하위 처리자 |  |  |
| 국외 전송 대상·국가·근거·고지 |  |  |
| 보존 기간·기산점·법적 보존 예외 |  |  |
| 삭제 요청·정정·접근권 처리 경로 |  |  |
| 지식 상태 메타데이터를 볼 등급·그룹·감사 목적과 관리 가능 계약 |  |  |
| 인증 모드와 사람·서비스 주체 매핑 | `opaque_only` / `jwt_only` / `both`, `person_id`, 서비스 계정 |  |
| 모델 질의 등급 하한과 반출 정책 | 기본 `RESTRICTED`; 변경 시 검증된 channel·회사 정책 |  |

## 4. 파생물과 로그까지 포함한 수명주기

| 자산 | 생성 위치 | 소유자 | 보존·삭제 규칙 | 삭제 확인 방법 |
|---|---|---|---|---|
| 원문 / 원천 export |  |  |  |  |
| 정규화 delta snapshot |  |  |  |  |
| 검색 인덱스 / 캐시 |  |  |  |  |
| 임베딩 / 벡터 |  |  |  |  |
| OCR·음성 전사·이미지 특징 |  |  |  |  |
| 프롬프트·응답·도구 호출 로그 |  |  |  |  |
| SQLite·WAL·백업 |  |  |  |  |
| 외부 모델·게이트웨이·관측 시스템 |  |  |  |  |

`tombstone`은 이 참조 런타임의 검색·승인에서 문서를 제외하는 논리 상태입니다. 위 표의 물리 매체·백업·WAL·공급자 보존 자료가 지워졌다는 증거로 사용하지 않습니다.

- source snapshot은 변경 문서만 보내는 delta입니다. 같은 문서 ID 중복을 제거하는 생성 규칙과, 변경 문서에 새 source version을 부여하는 책임자를 적습니다.
- delta에서 빠진 문서는 자동 retire/tombstone되지 않으므로 삭제·정정 이벤트의 별도 반입 책임자를 적습니다.
- source별 마지막 수락 `observed_at`, 문서별 accepted source-version history, contract ID/version/hash drift의 점검·복구 절차를 적습니다.
- `observed_at`은 게시자가 제공한 claim입니다. 실제 수집 시각·원천 인증 증거의 위치를 따로 적습니다.
- retire/tombstone 뒤에도 원래 ACL snapshot으로 메타데이터 노출을 제한합니다. ACL을 복원할 수 없는 legacy 행의 관리자 대조·migration 절차를 적습니다.
- 기존 문서 mutation 담당자가 저장 ACL의 tenant/group/clearance와 계약의 `READ+AUDIT+MANAGE_KNOWLEDGE`를 만족하는지 적습니다. 문서 purpose는 쓰기 ACL 검사에서 생략되므로 state 가시성과 쓰기 권한을 같은 것으로 기록하지 않습니다.
- ACL 변경 담당자는 계약 범위 안에서 groups, purposes, 민감도를 확대·축소할 수 있고 purpose 추가가 본문 열람 범위를 넓힐 수 있습니다. 단순 메타데이터 편집 권한으로 위임하지 말고 승인자·대조 기록을 적습니다.
- managed 신규 upsert·ACL 변경의 groups는 비우지 않습니다. 완전 회수 시 retire/tombstone 선택과 보존 승인자를 적고, 비어 있지 않은 다른 그룹 self-revoke와 구분합니다.
- legacy managed 빈 그룹·ACL 불명 행은 자동 권한 복원 없이 숨김+404로 유지합니다. 실제 회사 보존·법적 보존·원천 삭제를 확인할 migration 담당자와 증거를 적습니다.
- 계약 version/hash drift 뒤 계속 쓸 문서는 새 source version upsert로 재등록하고, 삭제할 문서는 같은 tenant/source/contract ID에서 tombstone cleanup을 사용합니다. retire/change_acl의 full binding 요구와 구분합니다.
- 계약을 registry에서 제거하기 전에 문서별 보존을 확인해 retire/tombstone합니다. 이미 제거했다면 같은 tenant/source/contract ID 재등록과 ACL 검사를 거쳐 drift tombstone으로 정리하고, `delete_within_hours`의 원천·파생물·백업별 책임자와 완료 증거를 적습니다.
- 기존 unqualified managed ID는 자동 rename하지 않습니다. upsert 422와 cleanup 경계를 기록하고, 계속 사용할 ID와 accepted source-version history는 백업·승인·충돌 검사·감사 대조가 있는 통제된 migration으로 옮깁니다.
- 다중 tenant 운영 전 legacy·bootstrap 문서의 실제 owner, 저장 tenant와 ID prefix를 재고 대조합니다. 다른 tenant namespace처럼 보이는 기존 ID, trusted admin 파일, 일반 ontology ID를 신규 managed upsert guard가 자동 정리한다고 가정하지 않습니다.
- 신규 성공과 replay 응답의 `documents`는 현재 ACL·exact binding으로 투영되며, 이 투영은 DB에 저장하는 canonical receipt/audit를 수정하지 않습니다. 자기 group을 제거한 ACL 변경 성공도 빈 배열일 수 있습니다. 과거 메타데이터 열람 권한과 원본 receipt 보존 위치를 따로 정합니다.

## 5. 위협과 대응

| 위협 / 실패 | 사전 차단 | 탐지 신호 | 대응·중단 | 복구·대조 |
|---|---|---|---|---|
| 잘못된 원천·위조된 출처 |  |  |  |  |
| 권한 회수 지연·교차 테넌트 노출 |  |  |  |  |
| 같은 tenant의 문서 ID 사용 여부 추론·민감한 ID 의미 노출·ID 선점 |  |  |  |  |
| 서비스 계정 승인·동일인 자기 승인 |  |  |  |  |
| 계약 drift·미바인딩 문서·과거 source version 재사용 |  |  |  |  |
| 계약 관리자 권한을 기존 문서 전체 쓰기 권한으로 오인 |  |  |  |  |
| ACL 변경 권한으로 group·purpose·민감도 범위를 부당하게 확대 |  |  |  |  |
| registry 계약을 문서 정리보다 먼저 제거해 API 삭제 경로 상실 |  |  |  |  |
| 빈 그룹 active 문서 생성으로 정상 삭제 경로 상실 |  |  |  |  |
| replay 응답 투영 감소를 영수증·감사 유실로 오인 |  |  |  |  |
| delta snapshot 중복·순서 역전·누락을 삭제로 오인 |  |  |  |  |
| 제한된 knowledge state를 전체 tenant 재고로 오인 |  |  |  |  |
| 프롬프트 인젝션·문서 내 지시 |  |  |  |  |
| 민감정보 모델 반출·로그 유출 |  |  |  |  |
| 오래된 근거로 승인·실행 |  |  |  |  |
| 중복 요청·부분 실패·재시작 |  |  |  |  |
| 삭제·정정 미전파 |  |  |  |  |
| 모델·도구·공급자 변경 |  |  |  |  |

## 6. 결정

- 결정: 보류 / 제한된 파일럿 검토 / 거부
- 허용 범위와 기간:
- 금지된 데이터·행위:
- 남은 미확인 항목:
- 재검토를 촉발하는 사건:
- 승인자와 승인 시각:

자가 보고와 문서 확인은 현장 통제 검증이나 보안 인증이 아닙니다. `CompanyProfile` 진단 결과도 제한된 파일럿 검토의 입력일 뿐 운영 승인으로 사용하지 않습니다.

