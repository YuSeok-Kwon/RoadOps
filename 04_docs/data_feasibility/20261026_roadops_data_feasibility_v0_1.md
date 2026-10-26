# RoadOps 데이터 실현 가능성 점검 v0.1 / Data Feasibility Spike v0.1

작성일 / Date: 2026-10-26

## 결론 / Decision

RoadOps 주제는 다음 단계로 진행한다. 공식 명세상 제주 도로 구간·노드·일별 및 시간대별 교통량과 C-ITS 도로위험·통제·작업·노면기상, ITS 실시간 교통정보가 모두 `link_id`를 제공한다. 따라서 1차 결합은 좌표 추정이 아니라 표준 링크 ID의 정확 조인으로 설계할 수 있다.

Proceed with RoadOps. The official specifications expose `link_id` across Jeju road links, nodes, daily/hourly traffic, C-ITS hazards, closures, works, road weather, and ITS live traffic. The primary integration can therefore use an exact standard-link join instead of an inferred coordinate match.

단, 이 결론은 **스키마 수준의 실현 가능성**이다. 현재 API 키와 센터 원본 행 데이터가 없어 실제 최신 응답, 링크 ID 유효율, 정확 조인 커버리지는 아직 검증하지 않았다.

This is a **schema-level feasibility result**, not an empirical coverage result. API keys and row-level center exports are not yet available, so current responses, valid-ID rates, and exact-join coverage remain unverified.

## 확인한 결합 경로 / Verified join paths

| 데이터 / Data | 기준 키·공간 단위 / Key or spatial unit | RoadOps에서의 역할 / Role |
|---|---|---|
| 제주 도로 구간 | `link_id`, `start_node_id`, `end_node_id` | 도로 네트워크 기준 테이블 |
| 제주 도로 노드 | `node_id`, WGS84 위·경도 | 링크 시작·종료점과 최소 형상 복원 |
| 제주 일별·시간대별 교통량 | `link_id`, 날짜·시간, 평균속도·통행시간 | 평시 기준선과 혼잡 변화 |
| 제주 C-ITS 위험·통제·공사·노면기상 | `link_id`, WGS84 위·경도 | 실시간 위험 신호와 운영 제약 |
| 제주 ITS 실시간 교통 | `link_id` | 속도·교통량·점유율·통행시간 |
| 기상청 초단기예보 | 5 km `nx`, `ny` 격자 | 가까운 미래의 기상 위험 |
| TAAS 세부링크 위험지수 | WGS84 `LineString` | 구조적 도로 위험 사전정보 |

제주빅데이터센터의 도로 구간·노드 명세는 시작·종료 노드 좌표로 최소 선분을 만들 수 있게 한다. 이는 `link_id`가 누락되거나 불일치할 때만 사용하는 공간 보조 매칭과 위치 품질 검사에 활용한다. 기상청 격자는 링크 중점의 WGS84 좌표를 공식 5 km 격자로 변환하고, TAAS에는 링크 선분을 `LineString(경도 위도,경도 위도)`로 전달한다.

## 구현한 안전장치 / Implemented safeguards

- 링크·노드 ID는 정확히 10자리 숫자인 경우에만 허용하며 임의로 0을 채우지 않는다.
- 이벤트는 `link_id` 정확 조인을 먼저 수행한다.
- 정확 조인이 실패했을 때만 거리 임계값이 표시된 공간 보조 매칭을 사용한다.
- 임계값 밖의 이벤트는 가까운 링크에 강제로 붙이지 않고 `unmatched`로 남긴다.
- 정확·공간·미결합·유효하지 않은 이벤트 수와 개별 매칭 방법을 모두 감사 로그로 반환한다.
- API 키는 환경변수로만 읽고 출력 결과에 포함하지 않는다.

## 접근성 점검 / Access status

| 소스 / Source | 문서·명세 / Documentation | 운영 응답 / Live response | 현재 판단 / Assessment |
|---|---|---|---|
| 제주빅데이터센터 | 명세 XLSX 다운로드 확인 | 원본 행 미확보 | 스키마 확인, 실제 커버리지 미확인 |
| 제주 C-ITS·ITS | 공개 신청 절차와 응답 필드 확인 | 키 없음 | 키 발급 후 검증 필요 |
| 기상청 초단기예보 | JSON/XML API와 5 km 격자 확인 | 키 없음 | 링크→격자 변환 구현, 응답 검증 필요 |
| TAAS 세부링크 위험지수 | WGS84 선분 입력·위험등급 출력 확인 | 키 없음 | 호출량·응답률·공간 일치 검증 필요 |

## 발견한 위험 / Risks found

1. 제주 C-ITS·ITS 문서의 운영 URL은 평문 HTTP다. 현재 환경에서도 HTTPS 연결은 확인되지 않았으므로, 쿼리 문자열의 키가 노출될 수 있다. 운영 적용 전 제공기관에 HTTPS 지원 여부를 확인하고, 백엔드 프록시·제한된 키·키 순환 정책을 사용해야 한다.
2. 센터 명세의 필드 존재가 실제 행의 완전성이나 최신성을 보장하지 않는다.
3. 기상청 5 km 격자는 개별 도로 링크보다 거칠다. 도로별 미세기상으로 해석하지 않고 지역 단위 외생 변수로 사용한다.
4. TAAS 호출은 링크 형상을 기준으로 하므로 전체 도로망을 매번 조회하면 비효율적일 수 있다. 캐시와 배치 전략이 필요하다.
5. 샘플 스크립트의 매칭률은 알고리즘 확인용 fixture 결과이며 실제 제주 성능 수치가 아니다.

## 다음 검증의 합격 기준 / Proposed acceptance gates

아래 값은 달성 결과가 아니라 다음 실데이터 검증의 사전 기준이다.

- 원본 `link_id` 10자리 형식 유효율 99% 이상
- 유효한 C-ITS·ITS 이벤트의 정확 `link_id` 조인율 95% 이상
- 공간 보조 매칭 포함 결합률 99% 이상, 단 보조 매칭 비율은 별도 공개
- 정확 조인된 이벤트 좌표와 링크 선분 거리의 95백분위 100 m 이하
- 실패·결측·지연 응답을 추천 점수 0점으로 숨기지 않고 상태로 분리

기준 미달 시 점수 모델 구현을 중단하고 링크 버전 불일치, 좌표계, 갱신시각, 폐쇄 링크 여부부터 조사한다.

## 다음 작업 / Next work

1. 제주 C-ITS·ITS, 공공데이터포털, TAAS 키를 발급받아 읽기 전용 live probe를 실행한다.
2. 제주빅데이터센터에서 도로 구간·노드·시간대별 교통량 샘플을 내려받는다.
3. 실제 `link_id` 유효율과 정확 조인 커버리지를 계산하고 좌표 거리로 교차검증한다.
4. 합격 기준을 통과한 뒤 위험 점수와 현장 자원 재배치 정책을 설계한다.

## 공식 출처 / Official sources

- 제주빅데이터센터 데이터 명세: https://jejudatahub.net/center/data
- 제주 C-ITS·ITS Open API: https://jejuits.go.kr/open_api/open_apiView.do
- 공공데이터포털 제주 C-ITS: https://www.data.go.kr/data/15079829/openapi.do
- 기상청 단기예보 조회서비스: https://www.data.go.kr/data/15084084/openapi.do
- TAAS 세부링크 도로위험지수: https://opendata.koroad.or.kr/api/selectLinkDataSet.do
