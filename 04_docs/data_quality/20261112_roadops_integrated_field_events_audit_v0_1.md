# 통합 현장 이벤트 품질 감사 v0.1 / Integrated Field-Event Quality Audit v0.1

작성일 / Date: 2026-11-12
최신 실행 / Latest run: 2026-11-12 17:58 KST

## 결론 / Decision

17:58 KST에 새로 수집한 C-ITS 25건을 입력으로 삼아 이벤트 1건당 1행인 통합 테이블을 만들었다. 출력도 25건이고 이벤트 ID도 25개로, 제주데이터허브 선형 심각도·교통량·날씨·TAAS 결합 과정에서 행 증가나 중복은 없었다.

결합 등급은 `exact_link_id` 4건, `spatial_fallback` 15건, `excluded` 6건이다. 점수화 대상 19건만 `effective_link_id`를 부여했으며, 배제 6건은 원본 ID와 공간 결합 근거를 보존하되 링크 단위 피처가 결합되지 않도록 차단했다.

제주데이터허브 선행값은 점수화 대상 19건에 모두 결합됐고, 교통량·날씨·TAAS까지 네 피처가 모두 갖쳐진 이벤트는 17건(89.5%)이다. 위험점수 v0.1은 결측을 0으로 대체하지 않고 상·하한으로 표시하며, 제주데이터허브와 TAAS를 하나의 25점 구조위험 구성요소 안에서만 결합한다.

## 데이터 단위와 키 / Grain and keys

- 통합 테이블 단위: 선택된 C-ITS 스냅샷의 원천 레코드 1건당 1행
- 이벤트 키: 소스·수집시각·원천 순번·이벤트 ID·좌표로 만든 결정적 SHA-256 `event_id`
- 도로 키: 점수화 허용 이벤트에만 부여되는 `effective_link_id`
- 제주데이터허브: 2018~2020년 도로 선형별 조건부 사고 심각도
- 교통량: ITS에서 링크별 가장 최신의 유효한 관측 1건
- 날씨: 이벤트 좌표의 기상청 격자에서 기준시각과 가장 가까운 예보 슬롯 1건
- TAAS: 점수화 대상의 고유 링크마다 조회한 구조적 사고위험 선행값

`audit_matched_link_id`는 배제된 이벤트에도 감사 근거로 남을 수 있지만 피처 결합에는 사용하지 않는다.

## 실수집 결합 결과 / Live integration result

| 구분 | 행 기준 | 고유 링크·격자 기준 | 판정 |
| --- | ---: | ---: | --- |
| 제주데이터허브 선형 심각도 | 19/19 (100.0%) | 9/9 링크 (100.0%) | 전부 결합 |
| ITS 교통량 | 17/19 (89.5%) | 7/9 링크 (77.8%) | 2개 링크 결측 |
| 기상청 초단기예보 | 24/24 유효 좌표 (100.0%) | 12/12 격자 (100.0%) | 전부 결합 |
| TAAS 위험지수 | 18/19 (94.7%) | 8/9 링크 (88.9%) | 1개 링크 API 오류 |
| 네 피처 모두 | 17/19 (89.5%) | 7/9 링크 (77.8%) | 결측 게이트 필요 |

배제 6건은 1·2순위 링크 거리 차 부족 5건과 잘못된 좌표 1건이다. 모두 `scoring_eligible=false`, `effective_link_id=null`로 유지한다.

## 결측과 오류 / Missingness and errors

| 링크 | 도로명 | 교통량 | 날씨 | TAAS | 처리 |
| --- | --- | --- | --- | --- | --- |
| `4060438807` | 516로 | `missing_link` | `matched` | `ok` | 교통 근거가 없는 상·하한으로 점수화 |
| `4050438101` | 남조로 | `missing_link` | `matched` | `api_error` | 근거 커버리지 60% 미만으로 `hold` |

TAAS의 `4050438101` 조회는 HTTP 200이었지만 제공기관 결과코드가 `10 INVALID_REQUEST_PARAMETER_ERROR`였다. 전송 성공과 데이터 성공을 분리해 `api_error`로 판정했고 위험값을 0으로 대체하지 않았다.

## 시간 정렬 / Temporal alignment

- 기준 빌드 시각: 17:58:59 KST
- C-ITS 수집시각: 17:58:49 KST, 약 0.2분 전
- ITS 관측시각: 17:55 KST, 약 4.0분 전
- 기상청 선택 예보시각: 18:00 KST, 약 1.0분 후
- 제주데이터허브: 2018~2020년의 조건부 구조 심각도
- TAAS: 실시간 사고가 아닌 구조적 선행 위험값

ITS는 30분을 초과하거나 빌드 시점보다 5분 이상 미래면 점수 근거에서 제외한다. 기상 예보는 유효시각이 기준시각에서 절대값 60분 이내인 경우만 사용한다. C-ITS에는 제공기관 발생시각이 없어 수집시각을 대신 쓰며, 모든 점수에 `cits_source_timestamp_unavailable`을 남긴다.

## 자동화 품질 게이트 / Automated gates

- 입력 이벤트 수와 출력 행 수 일치
- `event_id` 고유성
- `exact_link_id`, `spatial_fallback`, `excluded` 외 등급 차단
- 점수화 대상의 `effective_link_id` 완전성
- 배제 이벤트의 `effective_link_id` null 강제
- 기준망 링크, 제주데이터허브 선행값, 최신 교통량, TAAS 링크의 중복 차단
- 결측을 0으로 임의 대체하지 않고 상태를 별도 보존

이번 실행의 구조적 게이트 실패는 0건이다. 전체 상태는 C-ITS 원천 발생시각 부재를 포함한 `pass_with_limitations`다.

## 품질 판정 / Findings

1. **그레인 보존:** 25개 입력이 25개 출력과 25개 고유 이벤트 ID로 유지됐다.
2. **교통 커버리지:** 행 기준 89.5%지만 고유 링크 기준 77.8%로, 행 비율만 보면 도로 범위의 결측을 과소평가한다.
3. **TAAS 단일 링크 오류:** 9개 링크 중 8개는 정상이고 1개는 제공기관 오류다.
4. **원천 시각 한계:** C-ITS 발생시각이 없어 이미 종료된 이벤트와 새 이벤트를 단일 호출로 구분할 수 없다.
5. **필수 데이터 활용:** ID 1027 원천 51행을 검증하고 대상 9개 링크에 모두 결합했다. 사고 발생률이 아니라 직선 대비 조건부 사망 심각도로만 사용한다.

## 재현 / Reproduce

```bash
python 07_scripts/20261112_roadops_build_jeju_datahub_geometry_prior_v0_1.py --strict

python 07_scripts/20261027_roadops_collect_cits_snapshots_v0_1.py \
  --iterations 1 --allow-insecure-http --strict
python 07_scripts/20261112_roadops_audit_cits_spatial_join_v0_1.py --strict
python 07_scripts/20261112_roadops_build_integrated_events_v0_1.py \
  --refresh-enrichments --allow-insecure-http --strict
```

통합 CSV는 `02_outputs/data/integrated_field_events_v0_1/integrated_field_events.csv`, 품질보고서는 같은 디렉터리의 `quality_report.json`에 저장된다. 보강 캐시와 출력에는 인증키나 인증 URL을 저장하지 않는다.

## 다음 작업 / Next work

1. C-ITS 시정·노면 필드의 단위와 결측 표식을 제공기관에 확인한다.
2. 같은 링크의 복수 이벤트를 현장 작업 단위로 그룹화한다.
3. 위험점수와 가용 인력·차량·이동시간을 연결하되 운영자가 승인하기 전에는 배치를 확정하지 않는다.
