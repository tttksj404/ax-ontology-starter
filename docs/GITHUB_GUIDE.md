# GitHub 게시 범위와 실행 안내

이 저장소는 AX Ontology Starter v0.3.0의 코드, 합성 예제, 업종별 확장·보안·운영 문서, 공개 검증 기록을 제공합니다. 업무 진단부터 현재 원문 RAG, 검토된 LLM Wiki, 사람 승인과 되돌리기가 있는 로컬 상태 변경까지 실행할 수 있습니다.

## 처음 사용하는 순서

1. [README](../README.md)의 설치와 구매·고객지원·인사 데모를 실행합니다.
2. [적용 범위와 인터뷰](ADOPTION.md)로 회사의 업무·책임자·데이터 권한·정책을 정합니다.
3. [회사 적용 가이드](V02_GUIDE.md)에서 신원·데이터 계약·도메인팩·모델 경로를 연결합니다.
4. [v0.3 실행 가이드](V03_GUIDE.md)로 Wiki 초안·독립 검토·게시를 실행합니다.
5. [알려진 권고 8개](V03_RELEASE.md#최종-감사의-비차단-권고-8개)와 회사 gold set을 검토한 뒤 제한 파일럿을 시작합니다.
6. [업그레이드 가이드](UPGRADE_GUIDE.md)로 분야별 검색·운영·커넥터를 강화합니다.

## Git 소스와 원본 전달 ZIP의 관계

[v0.3.0 릴리즈](https://github.com/tttksj404/ax-ontology-starter/releases/tag/v0.3.0)의 ZIP은 2026-10-06 revision-3 최종 전달본입니다. 프로젝트 파일 358개와 항목별 크기·SHA-256을 적은 `DELIVERY_MANIFEST.json` 하나를 담고 있습니다.

| 파일 | 내용 |
|---|---|
| `ax-ontology-starter-v0.3.0.zip` | 실행 코드·예제·문서·공개 증거를 묶은 원본 전달본 |
| `ax-ontology-starter-v0.3.0.zip.sha256` | ZIP 바이트의 SHA-256 |
| `ax-ontology-starter-v0.3.0.delivery.json` | 당시 파일 수·검사 범위·ZIP 대조 결과 |

원본 ZIP의 크기는 **2,363,120 bytes**이고 SHA-256은 다음과 같습니다.

```text
93da82c10c10d9bcd27eef707da4a11ad074d26551d553d945e6f276a6ff2e4e
```

다운로드한 ZIP의 hash는 PowerShell에서 확인할 수 있습니다.

```powershell
Get-FileHash -Algorithm SHA256 .\ax-ontology-starter-v0.3.0.zip
```

GitHub용 README, 이 게시 안내, Git 제외·바이트 보존 설정은 원본 전달본 이후 정리했습니다. 원본 ZIP을 새 문서로 덮어쓰거나 과거 감사 manifest를 다시 작성하지 않습니다. `.gitattributes`는 Git의 줄바꿈 변환으로 고정 소스·증거의 바이트가 달라지는 것을 막습니다.

원본의 검사 대상 149개 파일은 Git 소스와 별도로 바이트를 대조합니다. 원본 Opus 감사 입력은 140개 파일이며, 그 시점의 README도 포함합니다. 지금의 README를 그 과거 정적 감사가 검토했다고 해석하면 안 됩니다. [v0.3 검증 기록](V03_VERIFICATION.md)과 [전달 결과](V03_RELEASE.md)는 원본 고정 입력의 결과입니다.

GitHub가 자동 생성하는 `Source code (zip/tar.gz)`는 게시용 문서·Git 설정이 포함된 Git 소스 아카이브입니다. 위에 이름을 적은 원본 전달 ZIP과 파일 구성·hash가 다르므로 다운로드 시 구분합니다.

## 공개하는 검증과 공개에서 제외하는 자료

공개 검증에는 실행 로그, 검사 소스 manifest, 독립 검토 보고서, 정적 감사의 고정 입력과 공개 판정이 포함됩니다. 과거 NEEDS_FIX와 실패 기록도 각 시점의 결과로 유지합니다. 합성 fixtures와 모델 전송 시험은 회사의 실데이터·모델 품질·ROI를 측정한 결과가 아닙니다.

세션과 작업 상태, runtime DB, 데모 자격증명, 환경 파일·비밀키, 캐시·가상환경·빌드 중간물, 원본 advisor 응답 JSON과 stderr는 게시 대상에서 제외합니다. 공개 판정 JSON은 모델명·입력 hash·범위·판정에 필요한 공개 기록이며 원본 응답과 구분합니다. 게시에는 검증된 ZIP의 파일 목록을 기준으로 한 명시적 경로 목록을 사용합니다.

## 회사 적용과 추가 변경의 검증 경계

실제 ERP·CRM·CMMS·IdP 커넥터, 중요한 결정의 실행 엔진, 벡터·하이브리드 검색, source watcher, 자동 재compile 대기열은 회사 요구에 맞게 추가합니다. 현업 gold set, 권한 회수·만료·삭제, 장애·복구·rollback, 반출·DLP·보존·리전 정책을 확인한 뒤 단계적으로 배포합니다.

코드가 바뀌면 이전 PASS를 그대로 적용하지 않습니다. 변경된 소스 manifest, 관련 실패 반례, 실행·설치 검사, 독립 검토, 필요한 새 감사 기록을 함께 만듭니다. 공개 저장소에 회사 파일럿 데이터나 자격증명을 추가하지 않습니다.
