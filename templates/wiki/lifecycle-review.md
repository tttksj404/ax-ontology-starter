# Wiki 수명주기 전파 검토서

knowledge mutation이 Wiki draft·page에 미친 실제 상태와 잔존물을 대조합니다. 원천 사건이 성공했다는 사실만으로 backup·download export까지 지워졌다고 판단하지 않습니다.

## 1. 사건

- tenant / document ID / source ID:
- 사건: upsert / retire / source ACL 변경 / scope object ACL·민감도·삭제 / tombstone / contract drift / raw→derived role 변경 / server floor 상향 / 무결성 실패
- 이전·새 source version / document·content·ACL hash / contract binding:
- knowledge transaction ID·시각 / actor:
- 보존·법적 보존 조건:

## 2. 예상 상태

| 사건 | draft | page head | page version JSON | link | 일반 읽기 |
|---|---|---|---|---|---|
| upsert·retire·ACL 변경 | 의존 draft만 `stale` | current revision이 의존할 때만 `stale` | 유지 | 유지 | 영향 current page만 404·index/query 제외 |
| tombstone | 모든 의존 draft `scrubbed`, `data=NULL` | current revision이 의존할 때만 `scrubbed` | 의존 revision만 `data=NULL` | 의존 revision link만 제거 | 영향 current head는 404, 독립 clean current revision은 유지 |
| transaction rollback | 이전 상태 | 이전 상태 | 이전 상태 | 이전 상태 | 기존 page 유지 |
| raw→derived role 변경 | DB draft 유지 | row 유지 | 유지 | 유지 | 다음 current pack/read에서 숨김; 승인된 raw 원천으로 재compile 필요 |
| scope object ACL·민감도·삭제 또는 floor 상향 | 영향 draft/page 재사용 차단 | 자격 있는 manager만 마지막 revision으로 복구 | 유지 | 유지 | 권한 없는 caller에게 미존재와 같은 404 |

hook 밖에서 원천이나 scope 객체가 바뀌어도 read는 live binding·ACL 불일치 page를 숨겨야 합니다. lint는 저장 snapshot과 현재 접근을 모두 가진 HUMAN knowledge manager에게 `source_changed` 또는 `recompile_required`와 revision·state·reason을 반환합니다. actor가 볼 수 없는 head, scrubbed head와 role 재분류로 current pack에서 사라진 원천의 상세 원인은 노출하지 않습니다.

## 3. 전파·잔존 검사

| 검사 | 기대 결과 | 실제 결과 | 증거 | 판정 |
|---|---|---|---|---|
| draft 조회가 stale/scrubbed payload를 노출하지 않는다 | 404 |  |  |  |
| page·index·query가 영향 page를 노출하지 않는다 | 제외 |  |  |  |
| 숨은 page title·link·backlink·개수 신호가 없다 | 비노출 |  |  |  |
| tombstone 뒤 모든 의존 draft·page revision JSON과 해당 link가 제거됐다 | 제거 |  |  |  |
| 과거 revision만 의존한 변경이 독립 current head를 stale로 만들지 않았다 | published 유지 |  |  |  |
| 과거 revision만 의존한 tombstone이 clean current revision을 scrub하지 않았다 | current 사용 가능 |  |  |  |
| audit chain과 Wiki audit event가 transaction 결과와 맞는다 | 일치 |  |  |  |
| 실패한 knowledge batch의 invalidation도 rollback됐다 | 기존 page 유지 |  |  |  |
| 새 compile이 현재 revision·새 request key·현재 원천을 쓴다 | 재검토 |  |  |  |
| proposer/reviewer replay가 현재 effective person·clearance·floor를 다시 검사한다 | 재사용 차단 또는 동일 결과 |  |  |  |
| role 재분류 뒤 current pack에서 원천이 빠지고 영향 page가 숨겨진다 | 제외·재compile |  |  |  |
| 권한 없는 existing/stale/scrubbed head 요청과 미존재 ID가 같은 404다 | 비노출 |  |  |  |
| 권한 있는 manager의 lint가 `source_changed` / `object_changed` / `head_stale` / `classification_floor`와 revision·state를 반환한다 | 복구 표면 |  |  |  |

## 4. 물리 잔존물

| 매체 | 삭제·보존 책임자 | 상태 | 완료 증거·기한 |
|---|---|---|---|
| SQLite page / WAL |  |  |  |
| filesystem snapshot / backup |  |  |  |
| 내려받은 Wiki export |  |  |  |
| 외부 저장소·gateway·model provider |  |  |  |
| 로그·관측 시스템 |  |  |  |
| page ID·request key·version ID·source dependency·최소 audit metadata |  |  |  |

runtime scrub은 live Wiki table JSON의 제거입니다. 위 매체의 물리 삭제 증거가 아닙니다.

## 5. 결정

- 완료 / 부분 완료 / 격리 유지 / rollback:
- 새 draft·review가 필요한 page:
- page ID가 scrubbed라 새 ID가 필요한가:
- superseded revision publish 재시도가 409 `wiki_publish_replay_superseded`로 닫혔는가:
- server floor 상향으로 새 request key·현재 revision 재compile이 필요한가:
- 남은 잔존물·owner·기한:
- legal hold 대상·승인자·근거·종료 조건 / 일반 삭제 SLA 예외:
- proposer/reviewer person ID의 보존·접근·정정·삭제 처리:
- 승인자 / 완료 시각 / 다음 대조일:

권한 밖 노출, tombstone 원천 재사용, 파생층 누락 중 하나라도 있으면 품질 점수와 관계없이 승격을 중단합니다.
