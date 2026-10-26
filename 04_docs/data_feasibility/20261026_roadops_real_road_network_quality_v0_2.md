# RoadOps 실제 제주 도로망 품질 검증 v0.2 / Real Jeju Road-Network Quality Validation v0.2

작성일 / Date: 2026-10-26
원본 버전 / Source release: 2026-10-14

> 후속 검증 / Follow-up: [실시간 링크 호환성 검증 v0.3](./20261026_roadops_live_link_compatibility_v0_3.md)에서 실시간 응답 품질 게이트와 전송 보안 정책을 구현했다. The follow-up implements live-response quality gates and the transport-security policy.

## 결론 / Decision

국토교통부 전국표준 노드링크에서 추출한 **노드 27,656개와 링크 37,087개**는 RoadOps의 1차 기준 도로망으로 사용한다. ID, 중복, 좌표, 노드 참조, 링크 형상, 차로 수, 제한속도, 연결성을 포함한 14개 게이트를 모두 통과했다.

Use the **27,656 nodes and 37,087 links** extracted from the MOLIT national standard node-link release as RoadOps's first baseline network. The data passed all 14 gates covering IDs, duplication, coordinates, node references, link geometry, lane counts, speed limits, and connectivity.

이 통과는 **도로망 자체의 구조적 사용 가능성**만 의미한다. C-ITS 위험정보나 실시간 교통정보가 이 버전의 `link_id`와 얼마나 정확히 결합되는지는 API 키를 확보한 뒤 별도로 검증해야 한다.

This pass establishes the **structural usability of the road network only**. It does not establish exact-join coverage against C-ITS hazards or live traffic. That requires live API credentials and a separate version-compatibility test.

## 데이터와 재현 정보 / Data and reproducibility

| 항목 / Item | 값 / Value |
|---|---|
| 공식 출처 / Official source | 국토교통부 전국표준 노드링크 / MOLIT national standard node-link |
| 원본 / Archive | `NODELINKDATA_20261014.zip`, 271,402,628 bytes |
| 원본 SHA-256 | `ccddb655a96a4544cf71fbd91715aa4b2d0a617f92aa1b89a0cfc062118b70f3` |
| 전국 레코드 / National source rows | 노드 1,184,340개, 링크 1,564,022개 |
| 제주 추출 / Jeju subset | 노드 27,656개, 링크 37,087개 |
| 좌표 변환 / CRS conversion | `ITRF2000_Central_Belt_60` → `EPSG:4326` |
| 선택 규칙 / Selection rule | 광의의 제주 경계 내 노드, 양단 노드가 모두 선택된 링크 / nodes in broad Jeju bounds and links with both endpoints selected |
| 검증 단위 / Grain | 노드는 `node_id`당 1행, 링크는 `link_id`당 1행 |

원본 ZIP은 변경하지 않고 Git 추적 제외 영역에 보관했다. ZIP 무결성과 SHA-256을 확인한 뒤, 압축 내 `.prj`에서 좌표계를 읽어 WGS84로 변환했다.

The raw ZIP remains immutable in a Git-ignored area. Its archive integrity and SHA-256 were verified before reading the `.prj` definition and transforming the geometry to WGS84.

## 품질 결과 / Quality results

| 검사 / Check | 결과 / Result | 기준 / Gate | 판정 / Decision |
|---|---:|---:|---|
| 유효한 고유 노드 ID / Valid unique node IDs | 27,656 / 27,656 (100%) | 99% / 100% | 통과 / Pass |
| WGS84 좌표 / Valid node coordinates | 27,656 / 27,656 (100%) | 99% | 통과 / Pass |
| 유효한 고유 링크 ID / Valid unique link IDs | 37,087 / 37,087 (100%) | 99% / 100% | 통과 / Pass |
| 노드 참조 무결성 / Endpoint references resolved | 74,174 / 74,174 (100%) | 100% | 통과 / Pass |
| 소스 링크 형상 / Valid source WKT | 37,087 / 37,087 (100%) | 99% | 통과 / Pass |
| 차로 수 / Valid lane counts | 37,087 / 37,087 (100%) | 95% | 통과 / Pass |
| 제한속도 / Valid speed limits | 37,087 / 37,087 (100%) | 95% | 통과 / Pass |
| 설명 가능한 도로명 / Descriptive road names | 36,534 / 37,087 (98.51%) | 95% | 통과 / Pass |
| 자기 순환 링크 / Self-loop-free links | 37,087 / 37,087 (100%) | 100% | 통과 / Pass |
| 최대 연결요소 / Largest connected component | 27,656 / 27,656 (100%) | 95% | 통과 / Pass |

구조적 오류로 분류된 행은 없었다. 다만 도로명이 `-`로 표시된 링크가 553개(1.49%) 있어, 사용자 설명에서는 링크 ID나 주변 지명을 함께 표시해야 한다. 차로 수는 1~5, 제한속도는 10~80 km/h 범위였다. 고립 노드는 없었고 전체가 하나의 무방향 연결요소를 이뤄다.

No row was classified as a structural error. However, 553 links (1.49%) use `-` as the road name, so user-facing explanations must fall back to the link ID or a nearby place name. Lane counts range from 1 to 5 and speed limits from 10 to 80 km/h. There are no isolated nodes, and the entire extracted network forms one undirected connected component.

## 해석할 때의 주의점 / Interpretation limits

1. **추출 규칙이 만든 100%가 있다.** 제주 경계 내의 유효한 좌표를 가진 노드를 먼저 선택했고 양단 노드가 모두 선택된 링크만 남겼다. 따라서 좌표 유효율과 노드 참조율 100%를 전국 원본의 독립적 품질 지표로 해석하면 안 된다.
2. **행정구역 전체 커버리지는 아직 검증하지 않았다.** 추출된 위도 범위는 33.1987~33.5645로 제주 본섬 중심이다. 추자도 등 부속 도서의 순찰 대상 포함 여부는 행정구역 경계와 별도로 비교해야 한다.
3. **연결되어 있다고 통행 가능한 것은 아니다.** 이번 검사는 무방향 연결성이다. 일방통행, 회전 제한, 차량 종류, 임시 통제를 반영한 실제 라우팅 가능성은 다음 단계에서 검증한다.
4. **동적 데이터와의 버전 호환성은 미확인이다.** C-ITS나 실시간 교통 API가 다른 버전의 링크 ID를 사용하면 정확 조인율이 낮아질 수 있다.

1. **Some 100% results are construction-induced.** Nodes were selected by valid coordinates within a broad Jeju boundary, and links were retained only when both endpoints were selected. Coordinate validity and referential integrity therefore do not independently characterize the national source.
2. **Administrative-area coverage is not yet established.** The extracted latitude range, 33.1987 to 33.5645, centers on Jeju's main island. Coverage of outlying islands such as Chuja must be compared with an administrative boundary.
3. **Graph connectivity does not prove drivability.** This test is undirected. One-way restrictions, turn restrictions, vehicle types, and temporary closures still need routing validation.
4. **Version compatibility with dynamic data is unknown.** C-ITS or live-traffic APIs may use a different link version, reducing exact-join coverage.

## 접근성 발견 / Access finding

제주빅데이터센터의 원본 행 데이터는 일반 공개 다운로드가 아니다. 이용 안내에 따르면 로그인, 분석실 예약, 연구 정보 등록, 센터 내 분석, 반출 신청과 재식별 위험 검토가 필요하다. 따라서 이번 단계에서는 즉시 재현 가능한 공공 기준망으로 전국표준 노드링크를 사용했다.

The Jeju Big Data Center's row-level data is not a direct public download. Its guide requires login, an analysis-room reservation, research details, in-center analysis, and an export request with a re-identification-risk review. The national standard node-link archive was therefore used as the immediately reproducible public baseline.

## 다음 검증 / Next validation

1. 제주 C-ITS·ITS API 키를 발급받아 실제 응답의 `link_id` 유효율과 기준망 정확 조인율을 측정한다.
2. 조인 실패를 링크 버전 불일치, 폐지 링크, 형식 오류, 좌표 불일치로 분류한다.
3. 일방통행과 회전정보를 반영한 방향 그래프로 실제 경로 생성 가능성을 검증한다.
4. 행정구역 경계와 비교해 본섬·부속도서 커버리지를 수치화한다.
5. 위 검증을 통과한 뒤에만 위험점수와 순찰자원 배분 모델을 연결한다.

1. Obtain Jeju C-ITS/ITS credentials and measure live `link_id` validity and exact-join coverage against this baseline.
2. Classify join failures into version mismatch, retired links, format errors, and spatial disagreement.
3. Validate routability with a directed graph that includes one-way and turn restrictions.
4. Quantify main-island and outlying-island coverage against an administrative boundary.
5. Connect the risk score and patrol-resource allocation model only after these checks pass.

## 재현 명령 / Reproduction commands

```bash
python 07_scripts/20261026_roadops_extract_jeju_nodelink_v0_1.py \
  --archive 01_raw_data/external/molit_nodelink_20261014/NODELINKDATA_20261014.zip

python 07_scripts/20261026_roadops_profile_road_network_v0_1.py \
  --links 02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv \
  --nodes 02_outputs/interim/molit_nodelink_jeju_20261014/jeju_nodes.csv \
  --output 02_outputs/data/20261026_roadops_real_road_network_quality_v0_2.json
```

## 공식 출처 / Official sources

- [국토교통부 전국표준 노드링크 데이터](https://www.data.go.kr/data/15025526/fileData.do)
- [국가교통정보센터 노드링크 다운로드](https://www.its.go.kr/nodelink/nodelinkRef)
- [제주빅데이터센터 이용 안내](https://jejudatahub.net/about/center-use)
- [제주특별자치도 실시간 교통정보 API](https://www.data.go.kr/data/15093660/openapi.do)
