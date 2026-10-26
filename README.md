# 제주 RoadOps / Jeju RoadOps

제주 도로의 과거·실시간 위험정보와 기상예보를 결합해 공무원의 현장 순찰 인력과 차량 배치를 지원하고, 상황 변화 시 계획을 다시 조정하는 설명 가능한 AI Agent 프로젝트입니다.

Jeju RoadOps is an explainable AI agent that combines historical and real-time road risk data with weather forecasts to support public officials in allocating patrol teams and vehicles and replanning when conditions change.

## 현재 단계 / Current phase

제주 도로 데이터, 제주 C-ITS, 기상청 단기예보, TAAS의 접근성과 스키마를 확인하고 공간 결합 가능성을 검증하는 데이터 스파이크를 진행합니다.

The current data spike validates access, schemas, and spatial join feasibility for Jeju road data, Jeju C-ITS, KMA forecasts, and TAAS.

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
```

## 문서 / Documentation

- [프로젝트 정의 / Project brief](./PROJECT_BRIEF.md)
- [콘텐츠 가이드 / Content guide](./CONTENT_GUIDE.md)
- [데이터 실현 가능성 점검 / Data feasibility spike](./04_docs/data_feasibility/20261026_roadops_data_feasibility_v0_1.md)
- [Velog 1부 초안 / Velog Part 1 draft](./04_docs/content/20261026_roadops_part_1_velog_draft_v0_1.md)
- [LinkedIn 첫 기록 초안 / LinkedIn first update draft](./04_docs/content/20261026_roadops_part_1_linkedin_draft_v0_1.md)

## 파일 이름 / File naming

분석 문서와 노트북은 `YYYYMMDD_roadops_주제_v버전` 형식을 사용합니다. `final`, `최종` 같은 이름은 사용하지 않습니다.

Analysis documents and notebooks use the `YYYYMMDD_roadops_topic_vVersion` convention. Names such as `final` are avoided.
