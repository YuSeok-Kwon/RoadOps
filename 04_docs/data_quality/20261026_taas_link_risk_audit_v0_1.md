# TAAS–제주 도로망 표본 결합 감사 / TAAS–Jeju Road Link Coverage Audit

## 결론 / Conclusion

TAAS 세부링크 도로위험지수를 RoadOps의 모든 도로 구간에 적용하는 안은 현재 보류한다. 제주 기준 도로망 37,087개 링크에서 `링크 ID 앞 3자리 × 도로등급`으로 층화한 200개 표본 중 정상 위험 레코드는 136개, 제공기관 요청 거부는 64개였다. 관측 커버리지 68%는 사전에 정한 90% 기준을 통과하지 못했다.

TAAS detailed-link risk should not yet be treated as a mandatory feature for every RoadOps road segment. Of 200 proportionally stratified links sampled from 37,087 Jeju reference links, 136 returned valid risk records and 64 were rejected by the provider. The observed 68% coverage failed the predeclared 90% gate.

## 데이터와 분석 단위 / Dataset and grain

- 기준망: 국토교통부 전국표준 노드링크에서 추출한 제주 링크 37,087개
- TAAS 소스: 세부링크 도로위험지수 REST API
- 분석 단위: 국가표준 링크 1개 × TAAS 조회 1회
- 표본: 링크 ID 앞 3자리와 도로등급 6개 층을 모집단 비율에 가깝게 반영한 200개
- 표본 시드: `20261026`
- TAAS 차량 코드: `01`
- 조회 형상: 기준 링크 WKT의 시작점과 종료점으로 만든 WGS84 `LineString`

링크 ID 앞 3자리는 표본 층화에만 사용하며 행정구역명으로 확정하지 않았다. 최대 표본 비중 차이는 `405|107` 층의 0.93%p였다.

## 수행한 검사 / Checks performed

| 검사 | 관측값 | 기준 | 결과 |
|---|---:|---:|---|
| 표본 실행 완전성 | 200 / 200, 100% | 100% | 통과 |
| 표본 링크 유일성 | 200 / 200, 100% | 100% | 통과 |
| 제공기관 정상 응답률 | 136 / 200, 68% | 95% | 실패 |
| TAAS 레코드 커버리지 | 136 / 200, 68% | 90% | 실패 |
| 정상 응답 스키마 유효율 | 136 / 136, 100% | 99% | 통과 |
| 필수 필드 완전성 | 136 / 136, 100% | 99% | 통과 |

필수 필드는 `index`, `line_string`, `anals_value`, `anals_grd`다. API 키는 결과, 캐시, 로그에 기록하지 않았다.

## 주요 발견 / Findings

### 1. 전체 링크 커버리지 부족 — High severity, high confidence

- 실패 내용: 200개 중 64개가 정상 위험 레코드를 반환하지 않았다.
- 증거: 정상 136개, 요청 거부 64개, 커버리지 68%.
- 영향: TAAS를 필수 위험 피처로 두면 표본의 32%가 점수 계산에서 탈락하거나 잘못된 기본값을 받는다.
- 조치: TAAS를 선택적 구조위험 사전정보로 사용하고 `available / rejected / unavailable` 상태를 별도 피처로 보존한다.

### 2. 요청 거부를 데이터 없음으로 해석할 수 없음 — High severity, high confidence

- 실패 내용: 64건 모두 HTTP 200 내부에서 `10 / INVALID_REQUEST_PARAMETER_ERROR`를 반환했다.
- 증거: 성공 결과만 캐시한 뒤 실패 64건을 재호출했을 때 동일한 64건이 같은 오류를 반복했다. 링크 방향을 바꾼 오류 표본 10건도 같은 코드를 반환했다.
- 영향: 이 값을 위험도 0이나 단순 결측으로 바꾸면 제공기관 거부와 실제 저위험 도로가 섞인다.
- 가능한 원인: 지원 도로망 또는 좌표 제약 불일치가 유력하지만 공식 확인 전에는 원인으로 확정하지 않는다.
- 조치: TAAS 제공기관에 코드 10의 정확한 의미, 지원 좌표 범위, 기준 도로망 버전을 확인한다.

### 3. 반환된 레코드의 스키마는 안정적 — Low severity, high confidence

- 관측: 정상 반환 136건 모두 필수 필드가 채워졌고 한 요청당 한 레코드였다.
- 영향: TAAS가 정상 반환된 구간에서는 구조적 위험 피처로 사용할 수 있다.
- 자동화: 필수 필드 99% 이상, 위험값 숫자형, 제공기관 오류 분리 검사를 회귀 테스트로 유지한다.

### 4. 위험값은 0이 많고 긴 꼬리를 가짐 — Medium modeling risk, high confidence

- 증거: 정상 위험값 136개 중 73개(53.68%)가 0이었다.
- 분포: 중앙값 0.00, 평균 7.80, 75백분위 2.405, 최댓값 186.13.
- 등급: `01` 112개, `02` 3개, `03` 10개, `04` 11개.
- 영향: 단순 평균·최댓값 기반 정규화는 일부 극단값에 끌릴 수 있다.
- 조치: 위험등급을 보존하고 위험값에는 분위수 절단 또는 `log1p` 변환을 비교한다.

## 층별 결과 / Segment results

| 링크 앞 3자리 | 도로등급 | 표본 | 정상 | 커버리지 |
|---|---:|---:|---:|---:|
| 405 | 105 | 3 | 2 | 66.67% |
| 405 | 106 | 21 | 16 | 76.19% |
| 405 | 107 | 85 | 62 | 72.94% |
| 406 | 105 | 2 | 2 | 100.00% |
| 406 | 106 | 19 | 14 | 73.68% |
| 406 | 107 | 70 | 40 | 57.14% |

`406|107`에서 가장 낮은 관측값이 나왔지만 이는 표본 기반이고 링크 앞 3자리의 행정구역 의미도 확정하지 않았으므로 지역적 원인으로 해석하지 않는다. 특히 `405|105`, `406|105`는 표본 수가 매우 작다.

## 시간·추세 한계 / Temporal limitations

이번 감사는 2026-10-26의 단면 검사다. TAAS 위험지수의 기준기간과 갱신주기가 응답에 직접 포함되지 않아 시간 추세, 최신성, 과거 안정성은 평가하지 못했다. 이후 제공기관 메타데이터를 확인하고 동일 표본을 반복 조회해야 한다.

## 권고 / Recommended remediation

1. TAAS 위험값과 함께 `taas_status`, `taas_available`을 저장한다.
2. 거부 또는 미수록 링크에는 위험도 0을 넣지 않고 국가표준 도로 속성·기상·향후 C-ITS/ITS를 사용한 대체 경로를 적용한다.
3. 코드 10의 공식 의미와 지원 도로망 버전을 확인하기 전에는 전체 제주 커버리지 수치로 일반화하지 않는다.
4. 제공기관 확인 후 같은 시드·표본·게이트로 감사를 재실행한다.
5. 다음 단계에서는 동일 200개 링크에 기상청 격자를 결합하고 TAAS 가용 여부를 포함한 위험 피처 테이블을 설계한다.

## 재현 경로 / Reproducibility

- 실행 스크립트: `07_scripts/20261026_roadops_audit_taas_coverage_v0_1.py`
- 분석 노트북: `03_notebooks/20261026_taas_link_risk_audit_v0_1.ipynb`
- 감사 결과: `02_outputs/data/taas_coverage_audit_v0_1/audit_report.json`
- 표본 결과: `02_outputs/data/taas_coverage_audit_v0_1/sample_results.csv`
- 피처 표본: `02_outputs/data/taas_coverage_audit_v0_1/road_risk_features_v0_1.csv`
- 공식 문서: https://opendata.koroad.or.kr/api/selectLinkDataSet.do

`02_outputs` 산출물과 API 캐시는 로컬 생성 데이터로 Git에 포함하지 않는다.
