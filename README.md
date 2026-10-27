# 제주 RoadOps / Jeju RoadOps

제주 도로의 과거·실시간 위험정보와 기상예보를 결합해 공무원의 현장 순찰 인력과 차량 배치를 지원하고, 상황 변화 시 계획을 다시 조정하는 설명 가능한 AI Agent 프로젝트입니다.

Jeju RoadOps is an explainable AI agent that combines historical and real-time road risk data with weather forecasts to support public officials in allocating patrol teams and vehicles and replanning when conditions change.

## 현재 단계 / Current phase

국토교통부 전국표준 노드링크에서 추출한 제주 기준 도로망의 구조적 품질을 검증했습니다. 다음은 제주 C-ITS·ITS 실시간 응답과의 링크 ID 호환성과 정확 조인율을 검증합니다.

The structural quality of a Jeju baseline network extracted from the MOLIT national standard node-link release is now validated. The next step is to measure link-version compatibility and exact-join coverage against live Jeju C-ITS/ITS responses.

## 디렉토리 / Directories

```text
01_raw_data/       원본 데이터, 읽기 전용 / immutable raw data
02_outputs/        가공 데이터와 시각화 / processed data and figures
03_notebooks/      탐색·검증 노트북 / exploration and validation notebooks
04_docs/           데이터·설계 문서 / data and design documentation
05_src/            재사용 가능한 Python 코드 / reusable Python code
07_scripts/        실행 스크립트 / executable scripts
config/            비밀정보를 제외한 설정 / non-secret configuration
tests/             자동화 테스트 / automated tests
999_Temporary/     임시 작업 파일 / temporary files
```

## 환경 설정 / Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

API 키가 필요하면 [`config/.env.example`](./config/.env.example)을 복사해 사용합니다. 실제 키는 Git에 포함하지 않습니다.

Copy [`config/.env.example`](./config/.env.example) when API keys are needed. Real keys must not be committed.

## 첫 데이터 스파이크 / First data spike

```bash
# 자동화 테스트 / automated tests
python -m pytest

# 공개 문서 접근성만 점검 / documentation-only probe
python 07_scripts/20261026_roadops_data_feasibility_v0_1.py

# 키가 설정된 소스만 운영 API 점검 / probe live APIs only when keys exist
python 07_scripts/20261026_roadops_data_feasibility_v0_1.py --live

# 실제 데이터가 아닌 fixture로 결합 규칙 확인 / deterministic fixture join
python 07_scripts/20261026_roadops_join_fixture_v0_1.py

# 도로망 CSV/JSON 품질 게이트 / road-network data-quality gates
python 07_scripts/20261026_roadops_profile_road_network_v0_1.py \
  --links 01_raw_data/links.csv \
  --nodes 01_raw_data/nodes.csv \
  --output 02_outputs/data/road_network_quality.json

# 국가표준 노드링크에서 제주 추출 / extract Jeju from the national node-link archive
python 07_scripts/20261026_roadops_extract_jeju_nodelink_v0_1.py \
  --archive 01_raw_data/external/molit_nodelink_20261014/NODELINKDATA_20261014.zip

# 저장된 ITS 응답을 기준망과 검증 / validate a saved ITS response
python 07_scripts/20261026_roadops_validate_live_link_compatibility_v0_1.py \
  --source-id jeju_its_realtime_traffic \
  --reference-links 02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv \
  --input path/to/jeju_its_response.json \
  --output 02_outputs/data/jeju_its_link_compatibility.json

# TAAS와 제주 기준 도로망의 층화 표본 결합 감사 / stratified TAAS coverage audit
python 07_scripts/20261026_roadops_audit_taas_coverage_v0_1.py \
  --sample-size 200 \
  --request-delay 0.1

# TAAS 감사 분석 노트북 생성 / build the TAAS audit notebook
python 07_scripts/20261026_roadops_build_taas_audit_notebook_v0_1.py
jupyter nbconvert --execute --to notebook --inplace \
  03_notebooks/20261026_taas_link_risk_audit_v0_1.ipynb

# 제주 C-ITS·ITS 인증키·실시간성 감사 / audit Jeju API keys and timeliness
python 07_scripts/20261027_roadops_audit_jeju_live_api_v0_1.py \
  --allow-insecure-http

# C-ITS 스냅샷 1회 수집 / collect one C-ITS snapshot
python 07_scripts/20261027_roadops_collect_cits_snapshots_v0_1.py \
  --allow-insecure-http

# 5분 간격 연속 수집 / collect every five minutes
python 07_scripts/20261027_roadops_collect_cits_snapshots_v0_1.py \
  --allow-insecure-http \
  --iterations 12 \
  --interval-seconds 300
```

C-ITS·ITS 문서의 운영 주소는 HTTP이므로 인증키가 평문으로 전송될 수 있습니다. 실시간 호출은 기본 차단되며, 기존 JSON 응답을 입력하는 방식은 키 없이 검증할 수 있습니다.

The documented C-ITS/ITS operational URLs use HTTP and may transmit API keys in plaintext. Live calls are blocked by default; saved JSON responses can be validated without a key.

## 문서 / Documentation

- [프로젝트 정의 / Project brief](./PROJECT_BRIEF.md)
- [콘텐츠 가이드 / Content guide](./CONTENT_GUIDE.md)
- [데이터 실현 가능성 점검 / Data feasibility spike](./04_docs/data_feasibility/20261026_roadops_data_feasibility_v0_1.md)
- [TAAS 링크 위험지수 품질 감사 / TAAS link-risk quality audit](./04_docs/data_quality/20261026_taas_link_risk_audit_v0_1.md)
- [TAAS 감사 노트북 / TAAS audit notebook](./03_notebooks/20261026_taas_link_risk_audit_v0_1.ipynb)
- [제주 API 인증키·실시간성 감사 / Jeju API key and timeliness audit](./04_docs/data_quality/20261027_roadops_jeju_live_api_key_freshness_audit_v0_1.md)
- [제주 API 감사 노트북 / Jeju API audit notebook](./03_notebooks/20261027_jeju_live_api_key_freshness_audit_v0_1.ipynb)
- [C-ITS 스냅샷 생명주기 감사 / C-ITS snapshot lifecycle audit](./04_docs/data_quality/20261027_roadops_cits_snapshot_lifecycle_audit_v0_1.md)
- [C-ITS 스냅샷 감사 노트북 / C-ITS snapshot audit notebook](./03_notebooks/20261027_cits_snapshot_lifecycle_audit_v0_1.ipynb)
- [실제 제주 도로망 품질 검증 / Real Jeju road-network quality validation](./04_docs/data_feasibility/20261026_roadops_real_road_network_quality_v0_2.md)
- [실시간 링크 호환성 검증 / Live-link compatibility validation](./04_docs/data_feasibility/20261026_roadops_live_link_compatibility_v0_3.md)
- [Velog 1부 초안 / Velog Part 1 draft](./04_docs/content/20261026_roadops_part_1_velog_draft_v0_1.md)
- [LinkedIn 첫 기록 초안 / LinkedIn first update draft](./04_docs/content/20261026_roadops_part_1_linkedin_draft_v0_1.md)
- [Velog 2부 초안 / Velog Part 2 draft](./04_docs/content/20261027_roadops_part_2_velog_draft_v0_1.md)
- [LinkedIn 두 번째 기록 초안 / LinkedIn second update draft](./04_docs/content/20261027_roadops_part_2_linkedin_draft_v0_1.md)

## 파일 이름 / File naming

분석 문서와 노트북은 `YYYYMMDD_roadops_주제_v버전` 형식을 사용합니다. `final`, `최종` 같은 이름은 사용하지 않습니다.

Analysis documents and notebooks use the `YYYYMMDD_roadops_topic_vVersion` convention. Names such as `final` are avoided.
