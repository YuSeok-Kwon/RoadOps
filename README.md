# 제주 RoadOps / Jeju RoadOps

제주 도로의 과거·실시간 위험정보와 기상예보를 결합해 공무원의 현장 순찰 인력과 차량 배치를 지원하고, 상황 변화 시 계획을 다시 조정하는 설명 가능한 AI Agent 프로젝트입니다.

Jeju RoadOps is an explainable AI agent that combines historical and real-time road risk data with weather forecasts to support public officials in allocating patrol teams and vehicles and replanning when conditions change.

## 현재 단계 / Current phase

제주 C-ITS 현장 이벤트와 설명 가능한 0·1·3·6시간 운영 우선순위, 팀·차량 자원 모델, 도로망 이동시간, 제약 기반 배분을 연결했습니다. 자연어 요청 한 문장으로 최초 계획을 만들고, 통제·폭우 What-if에서는 완료·고정·비영향 업무를 보존한 채 영향팀만 부분 재계획합니다. 현재·예측 위험과 팀 경로를 보여주는 제주 도로 지도, 자원 편집·안전확인·승인·감사로그를 갖춘 웹 MVP를 구현했습니다. 또한 API·신선도·링크·최적화·설명 장애 6개 시나리오에서 자동 출동을 차단하고 캐시 재생·보류·제외·수동 개입으로 안전 전환하는 복구 정책을 검증했습니다.

The project now creates an initial plan from one natural-language request and partially replans only affected teams under road-closure and heavy-rain what-if scenarios. The web MVP connects the current/forecast Jeju road map to editable resources, safety checks, operator approval, and an audit log. Its fail-safe policy was also verified across six injected API, freshness, link, optimization, and explanation failures: automatic dispatch stays blocked while the workflow degrades to cache replay, hold, exclusion, or manual intervention.

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
demo/              API 키 없는 오프라인 시연 입력 / key-free offline demo inputs
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

## 오프라인 캐시 데모 / Offline cached demo

API 키 없이 검토된 저장 입력으로 Agent를 실행합니다. 이 결과는 실시간 현황이 아닙니다.

Run the Agent from reviewed frozen inputs without API keys. The result is not live road status.

```bash
.venv/bin/python 07_scripts/20261113_roadops_run_agent_flow_v0_1.py \
  --as-of '2026-11-16T18:00:00+09:00' \
  --strict
```

OS별 원클릭 진입점도 제공합니다. 추가 인자는 Python 실행기에 그대로 전달됩니다.

OS-specific one-command entry points are also provided. Additional arguments are forwarded to the Python runner.

```bash
# macOS / Linux
./run_demo.sh --as-of '2026-11-16T18:00:00+09:00'
```

```powershell
# Windows PowerShell
.\run_demo.ps1 --as-of "2026-11-16T18:00:00+09:00"
```

센터 환경 사전점검은 Python·Node 의존성 설치 후 다음처럼 실행합니다.

Run the center-environment preflight after installing the Python and Node dependencies.

```bash
.venv/bin/python 07_scripts/20261116_roadops_validate_center_environment_v0_1.py \
  --strict
```

제출 소스·Prompt/Tool 계약·비밀값 미포함·원클릭 실행을 한 번에 검증할 수 있습니다.

Validate the submission source, Prompt/Tool contract, secret exclusion, and one-command entry point together.

```bash
.venv/bin/python 07_scripts/20261116_roadops_validate_submission_source_v0_1.py \
  --strict
```

19개 원천부터 Agent와 지도 출력까지의 데이터 계보와 592개 필드·JSON leaf path를 검증합니다.

Validate the lineage from 19 sources to the Agent and map outputs, covering 592 fields and JSON leaf paths.

```bash
.venv/bin/python 07_scripts/20261116_roadops_validate_data_lineage_v0_1.py \
  --strict
```

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

# 최신 C-ITS 스냅샷 좌표 기반 도로 결합 감사 / audit spatial road matching
python 07_scripts/20261112_roadops_audit_cits_spatial_join_v0_1.py

# 제주데이터허브 도로 선형 심각도 선행값 / build Jeju Data Hub geometry priors
# 데이터 ID 1027의 CSV를 아래 경로에 저장 / save dataset 1027 CSV at:
# 01_raw_data/external/jeju_datahub_1027/제주도로선형별교통사고현황.csv
python 07_scripts/20261112_roadops_build_jeju_datahub_geometry_prior_v0_1.py \
  --strict

# 통합 현장 이벤트 테이블 생성 / build the integrated field-event table
# 최초 수집 또는 새로고침 시에만 HTTP 명시 허용 / allow HTTP explicitly only when refreshing
python 07_scripts/20261112_roadops_build_integrated_events_v0_1.py \
  --refresh-enrichments \
  --allow-insecure-http \
  --strict

# 설명 가능한 위험점수 / build explainable risk scores
python 07_scripts/20261112_roadops_build_risk_scores_v0_1.py --strict

# 0·1·3·6시간 운영 우선순위 시나리오 / build horizon priority scenarios
python 07_scripts/20261112_roadops_build_weather_timeline_v0_1.py --strict
python 07_scripts/20261112_roadops_build_risk_forecasts_v0_1.py --strict

# 팀·차량 자원 검증과 위험순·최근접 기준선 / resource validation and baselines
python 07_scripts/20261112_roadops_build_allocation_baselines_v0_1.py --strict

# 실제 도로망 이동시간 행렬과 캐시 / road-network travel-time matrix and cache
python 07_scripts/20261113_roadops_build_travel_time_matrix_v0_1.py --strict

# 안전 우선·업무 균형 제약 최적화 / safety-first and balanced optimization
python 07_scripts/20261113_roadops_optimize_allocation_v0_1.py --strict

# 저장된 보강 데이터로 네트워크 호출 없이 재생성 / rebuild from cached enrichments
python 07_scripts/20261112_roadops_build_integrated_events_v0_1.py --strict
```

C-ITS·ITS 문서의 운영 주소는 HTTP이므로 인증키가 평문으로 전송될 수 있습니다. 실시간 호출은 기본 차단되며, 기존 JSON 응답을 입력하는 방식은 키 없이 검증할 수 있습니다.

The documented C-ITS/ITS operational URLs use HTTP and may transmit API keys in plaintext. Live calls are blocked by default; saved JSON responses can be validated without a key.

## 문서 / Documentation

- [프로젝트 정의 / Project brief](./PROJECT_BRIEF.md)
- [콘텐츠 가이드 / Content guide](./CONTENT_GUIDE.md)
- [제주 행정·도로관리 체계와 현장 대응 절차 조사 / Jeju road administration and field-response research](./04_docs/research/20261117_jeju_road_administration_field_response_v0_1.md)
- [기관·관할 기반 운영 모델 v0.1 / Institution-aware operations v0.1](./04_docs/model/20261117_roadops_institution_aware_operations_v0_1.md)
- [데이터 실현 가능성 점검 / Data feasibility spike](./04_docs/data_feasibility/20261026_roadops_data_feasibility_v0_1.md)
- [TAAS 링크 위험지수 품질 감사 / TAAS link-risk quality audit](./04_docs/data_quality/20261026_taas_link_risk_audit_v0_1.md)
- [TAAS 감사 노트북 / TAAS audit notebook](./03_notebooks/20261026_taas_link_risk_audit_v0_1.ipynb)
- [제주 API 인증키·실시간성 감사 / Jeju API key and timeliness audit](./04_docs/data_quality/20261027_roadops_jeju_live_api_key_freshness_audit_v0_1.md)
- [제주 API 감사 노트북 / Jeju API audit notebook](./03_notebooks/20261027_jeju_live_api_key_freshness_audit_v0_1.ipynb)
- [C-ITS 스냅샷 생명주기 감사 / C-ITS snapshot lifecycle audit](./04_docs/data_quality/20261027_roadops_cits_snapshot_lifecycle_audit_v0_1.md)
- [C-ITS 스냅샷 감사 노트북 / C-ITS snapshot audit notebook](./03_notebooks/20261027_cits_snapshot_lifecycle_audit_v0_1.ipynb)
- [C-ITS 공간 결합 품질 감사 / C-ITS spatial-join quality audit](./04_docs/data_quality/20261112_roadops_cits_spatial_join_audit_v0_1.md)
- [제주데이터허브 선형 심각도 감사 / Jeju Data Hub geometry severity audit](./04_docs/data_quality/20261112_roadops_jeju_datahub_geometry_prior_audit_v0_1.md)
- [통합 현장 이벤트 품질 감사 / Integrated field-event quality audit](./04_docs/data_quality/20261112_roadops_integrated_field_events_audit_v0_1.md)
- [설명 가능한 위험점수 v0.1 / Explainable risk score v0.1](./04_docs/model/20261112_roadops_explainable_risk_score_v0_1.md)
- [0·1·3·6시간 운영 우선순위 v0.1 / Horizon priority scenarios v0.1](./04_docs/model/20261112_roadops_risk_forecast_v0_1.md)
- [자원 입력과 기준선 배분 v0.1 / Resource inputs and allocation baselines v0.1](./04_docs/model/20261112_roadops_allocation_baselines_v0_1.md)
- [도로망 이동시간 행렬 v0.1 / Road-network travel-time matrix v0.1](./04_docs/model/20261113_roadops_travel_time_matrix_v0_1.md)
- [제약 기반 자원 배분 v0.1 / Constraint-based allocation v0.1](./04_docs/model/20261113_roadops_constraint_allocation_v0_1.md)
- [자원 배분 정량 평가 v0.1 / Allocation evaluation v0.1](./04_docs/evaluation/20261113_roadops_allocation_evaluation_v0_1.md)
- [Agent 도구 흐름 v0.1 / Agent tool flow v0.1](./04_docs/agent/20261113_roadops_agent_flow_v0_1.md)
- [부분 재계획 v0.1 / Partial replanning v0.1](./04_docs/agent/20261113_roadops_partial_replanning_v0_1.md)
- [장애·복구 평가 v0.1 / Resilience evaluation v0.1](./04_docs/evaluation/20261116_roadops_resilience_evaluation_v0_1.md)
- [센터 실행환경 검증 v0.1 / Center environment validation v0.1](./04_docs/deployment/20261116_roadops_center_environment_validation_v0_1.md)
- [실행·사용자 매뉴얼 v0.1 / Execution and user manual v0.1](./04_docs/deployment/20261116_roadops_execution_user_manual_v0_1.md)
- [데이터 활용·필드 계보 명세 v0.1 / Data usage and field lineage v0.1](./04_docs/deployment/20261116_roadops_data_usage_lineage_v0_1.md)
- [평가 연계 작업표 / Evaluation-aligned work plan](./04_docs/planning/20261112_roadops_evaluation_workplan_v0_1.md)
- [실제 제주 도로망 품질 검증 / Real Jeju road-network quality validation](./04_docs/data_feasibility/20261026_roadops_real_road_network_quality_v0_2.md)
- [실시간 링크 호환성 검증 / Live-link compatibility validation](./04_docs/data_feasibility/20261026_roadops_live_link_compatibility_v0_3.md)
- [Velog 1부 초안 / Velog Part 1 draft](./04_docs/content/20261026_roadops_part_1_velog_draft_v0_1.md)
- [LinkedIn 1·2부 통합 초안 / Combined LinkedIn Parts 1 and 2](./04_docs/content/20261112_roadops_linkedin_combined_draft_v0_1.txt)
- [Velog 2부 초안 / Velog Part 2 draft](./04_docs/content/20261027_roadops_part_2_velog_draft_v0_1.md)
- [Velog 3부 초안 / Velog Part 3 draft](./04_docs/content/20261112_roadops_part_3_velog_draft_v0_1.md)
- [LinkedIn 3부 초안 / LinkedIn Part 3 draft](./04_docs/content/20261113_roadops_part_3_linkedin_draft_v0_1.txt)
- [Velog 4부 초안 / Velog Part 4 draft](./04_docs/content/20261113_roadops_part_4_velog_draft_v0_1.md)
- [LinkedIn 4부 초안 / LinkedIn Part 4 draft](./04_docs/content/20261113_roadops_part_4_linkedin_draft_v0_1.txt)
- [Velog 5부 초안 / Velog Part 5 draft](./04_docs/content/20261113_roadops_part_5_velog_draft_v0_1.md)
- [Velog 6부 초안 / Velog Part 6 draft](./04_docs/content/20261116_roadops_part_6_velog_draft_v0_1.md)
- [LinkedIn 5부 초안 / LinkedIn Part 5 draft](./04_docs/content/20261116_roadops_part_5_linkedin_draft_v0_1.txt)
- [Velog 7부 초안 / Velog Part 7 draft](./04_docs/content/20261117_roadops_part_7_velog_draft_v0_1.md)
- [LinkedIn 6부 초안 / LinkedIn Part 6 draft](./04_docs/content/20261117_roadops_part_6_linkedin_draft_v0_1.txt)
- [Velog 8부 마지막 기록 초안 / Velog Part 8 closing draft](./04_docs/content/20261120_roadops_part_8_velog_draft_v0_1.md)
- [LinkedIn 7부 마지막 기록 초안 / LinkedIn Part 7 closing draft](./04_docs/content/20261120_roadops_part_7_linkedin_draft_v0_1.txt)

## 공모전 제출 패키지 / Competition delivery

[최종 제출 매뉴얼 / Submission guide](./04_docs/submission_20261120/README.md)에 필수 제출물별 위치, 저장 자료 웹 실행, 독립 경로 검증, 데이터 이용조건과 센터 적용 한계를 정리했습니다. 패키징 도구는 `07_scripts/20261120_roadops_package_submission.py`입니다. 제출 ZIP과 15페이지 PDF는 로컬 `02_outputs/submission_20261120/`에 보관하며, 인증키·개발 가상환경·설치된 패키지는 포함하지 않습니다.

The delivery contains a 15-page proposal, two frozen browser demos, source, manuals, data lineage and verification evidence. It preserves original input timestamps and explicitly labels saved-data playback.

## 파일 이름 / File naming

분석 문서와 노트북은 `YYYYMMDD_roadops_주제_v버전` 형식을 사용합니다. `final`, `최종` 같은 이름은 사용하지 않습니다.

Analysis documents and notebooks use the `YYYYMMDD_roadops_topic_vVersion` convention. Names such as `final` are avoided.
