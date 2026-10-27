# C-ITS 스냅샷 생명주기 감사 v0.1 / C-ITS Snapshot Lifecycle Audit v0.1

## 목적 / Purpose

C-ITS 도로위험·통제·작업·노면기상 응답에는 제공자 관측시각이 없다. 이 감사는 각 호출의 수집시각을 기록하고 연속 스냅샷을 비교해 `new`, `unchanged`, `changed`, `disappeared`, `unknown`을 구분한다.

C-ITS event, closure, work, and road-weather responses do not include a provider observation timestamp. This audit records ingestion time and compares consecutive snapshots to distinguish `new`, `unchanged`, `changed`, `disappeared`, and `unknown`.

## 데이터 단위 / Grain

- 스냅샷: 소스 1개와 수집 실행 1회당 1개 JSON
- 활성 상태: 소스의 현재 고유 레코드 키당 1개 상태
- 생명주기 로그: 레코드와 수집 실행당 1개 상태 판정
- 도로위험·통제·작업 키: `ocrr_id + link_id`
- 노면기상 키: `latitude + longitude`

## 상태 규칙 / State rules

| 상태 | 판정 규칙 | 상태 저장 처리 |
| --- | --- | --- |
| `new` | 이전 활성 상태에 키가 없음 | 최초·최종 관측시각 생성 |
| `unchanged` | 키와 레코드 해시가 동일 | 최초 관측 유지, 최종 관측 갱신 |
| `changed` | 키는 같고 레코드 해시가 변경 | 변경시각과 최신 레코드 갱신 |
| `disappeared` | 정상 수집에서 이전 키가 사라짐 | 활성 상태에서 제거 |
| `unknown` | 호출 실패, 중복 키, 키 누락 | 기존 활성 상태를 보존하고 소멸로 처리하지 않음 |

정상 0건은 실패가 아니다. 성공 응답의 `info_cnt=0`과 추출 레코드 0건이 일치하면 정상 빈 스냅샷으로 처리한다. 반대로 호출 실패는 0건으로 변환하지 않고, 이전 활성 레코드를 `unknown`으로 유지한다.

## 실수집 결과 / Live results

2026-10-27 09:32:30 KST의 첫 수집은 네 API 모두 성공했고 품질 실패는 없었다.

| 소스 | 레코드 | 첫 상태 |
| --- | ---: | ---: |
| 도로위험 | 33 | `new` 33 |
| 도로통제 | 0 | 정상 빈 응답 |
| 도로작업 | 1 | `new` 1 |
| 노면기상 | 12 | `new` 12 |
| 합계 | 46 | `new` 46 |

09:32:33 KST의 즉시 재수집에서도 네 API가 모두 성공했다. 레코드 46건은 모두 `unchanged`였고, `changed`·`disappeared`·`unknown`은 없었다. 이 짧은 간격의 검사는 동일 응답에 대한 비교 로직의 결정성을 확인하기 위한 것으로, C-ITS의 실제 갱신주기나 신선도를 증명하지 않는다.

09:37:52 KST의 5분 후 수집은 네 API 모두 성공했고 품질 실패도 없었다. 도로위험은 이전 33건에서 34건으로 바뀌며 `new` 5건, `disappeared` 4건, `unchanged` 29건이 분리됐다. 노면기상은 12건 중 4건이 `changed`, 8건이 `unchanged`였다. 도로작업 1건은 유지됐고 도로통제는 다시 정상 0건이었다.

| 소스 | 5분 후 활성 레코드 | 생명주기 변화 |
| --- | ---: | --- |
| 도로위험 | 34 | `new` 5, `disappeared` 4, `unchanged` 29 |
| 도로통제 | 0 | 정상 빈 응답 |
| 도로작업 | 1 | `unchanged` 1 |
| 노면기상 | 12 | `changed` 4, `unchanged` 8 |
| 합계 | 47 | `new` 5, `changed` 4, `disappeared` 4, `unchanged` 38 |

이 결과는 수집 시각 기준의 상태 변화를 보여주지만, 원천 관측시각이 없으므로 각 변화의 실제 발생 시점을 증명하지는 않는다.

## 품질검사 / Quality checks

- 제공 `info_cnt`와 추출 레코드 수 일치
- 설정된 복합 키의 완전성
- 스냅샷 내부 복합 키 유일성
- 레코드 정규화 후 SHA-256 비교
- 호출 실패 시 활성 상태 보존
- 키 누락·중복 시 소멸 판정 보류
- 인증키와 인증키 포함 URL의 스냅샷·상태·로그 제외

고정 테스트에서는 정상 빈 응답, 변경, 신규, 소멸, 호출 실패, 중복 키, 키 누락을 모두 재현했다. 중복·누락 키가 하나라도 있는 회차에서는 미관측 기존 레코드를 거짓 소멸로 판정하지 않도록 검증했다. 총 자동화 테스트 54개가 통과했다.

## 한계와 다음 단계 / Limitations and next step

수집시각은 RoadOps가 응답을 받은 시각이지 제공자가 이벤트를 관측한 시각이 아니다. 따라서 반복해서 보였다는 이유만으로 현재 유효한 이벤트라고 단정할 수 없다. 충분한 기간의 변화 패턴과 제공기관의 데이터 유지 정책을 함께 확인해야 한다.

다음 단계는 다음과 같다.

1. 여러 시간대의 5분 간격 반복 수집으로 변화율·지속시간 분포 측정
2. `link_id=-1` 노면기상과 미결합 이벤트의 좌표 기반 도로 결합
3. 정확 ID·공간 보조·미결합을 분리한 통합 이벤트 테이블 생성
4. 도로별 위험점수 입력 전 신선도·결합 근거 품질 게이트 적용

## 재현 / Reproduce

```bash
python 07_scripts/20261027_roadops_collect_cits_snapshots_v0_1.py \
  --allow-insecure-http \
  --iterations 12 \
  --interval-seconds 300
```

생성 데이터는 `02_outputs/data/cits_snapshot_monitor_v0_1` 아래의 `snapshots`, `state`, `runs`, `lifecycle_events.jsonl`에 저장된다. API 키와 키가 포함된 요청 URL은 저장하지 않는다.
