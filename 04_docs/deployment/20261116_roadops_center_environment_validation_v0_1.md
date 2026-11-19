# RoadOps 센터 실행환경 검증 v0.1 / Center Environment Validation v0.1

작성일 / Date: 2026-11-16

## 1. 목적과 판정 / Objective and decision

공모전 센터 제공 환경으로 안내된 `Intel Core i7-8700 / RAM 32GB / GTX 1060 3GB`에서 RoadOps가 대형 로컬 LLM·CUDA·실시간 API에 의존하지 않고 재현 가능한지 점검한다.

현재 판정은 `pass_with_limitations`다.

- 필수 환경·무결성·스모크 검사 15 / 15 통과
- API 키가 필요 없는 167KB 캐시 데모 번들 추가
- Agent 7단계, Python 160개 테스트, 웹 정책 6개 테스트, 웹 생산 빌드 통과
- GPU 필수 의존성 0개, 실행 코드의 사용자 절대경로 0건
- 현재 호스트의 스모크 합산 1.833초, 자식 프로세스 최대 RSS 430.766MB

다만 실제 센터 PC가 아닌 `macOS arm64 / 10 logical CPU / RAM 24GB / NVIDIA GPU 없음`에서 실행했다. 센터 운영체제도 아직 확인되지 않았다. 따라서 실제 센터 장비 통과나 성능 SLA로 해석하면 안 된다.

## 2. 타겟 프로필 / Target profile

| 항목 | 센터 목표 | RoadOps 정책 |
| --- | ---: | --- |
| CPU | i7-8700, 6코어·12스레드 | CPU 기반 결정적 위험·최적화 계산 |
| RAM | 32GB | 관측 최대 RSS 약 434MB, 다만 호스트·프로세스 차이 있음 |
| GPU | GTX 1060 3GB | 사용하지 않음, CUDA 필수 아님 |
| Python | 3.11 이상, 3.15 미만 | 현재 3.14.3에서 검증 |
| Node.js | `^20.19.0` 또는 `>=22.12.0` | Vite 8 엔진 요구범위 |
| 네트워크 | 설치 시 필요 | 의존성 설치 후 캐시 데모는 오프라인 실행 |

타겟 설정은 [`config/execution_profiles/competition_center_v0_1.json`](../../config/execution_profiles/competition_center_v0_1.json)에 고정했다.

## 3. 데이터 수집 및 적재 / Data collection and ingestion

### 캐시 데모 모드

깨끗한 Git 체크아웃에는 `.gitignore`로 제외된 `02_outputs/data` 산출물이 없다. 기존 Agent 기본 명령은 이 경로를 요구해 새 환경에서 즉시 실패했다.

이 문제를 해결하기 위해 검토된 파생 산출물만 [`demo/cached_inputs_v0_1`](../../demo/cached_inputs_v0_1)에 묶었다.

| 입력 | 규모 |
| --- | ---: |
| 0·1·3·6시간 위험 예보 | 88행, 75,262 bytes |
| 통합 현장 이벤트 | 22행, 16,012 bytes |
| 이동시간 행렬 | 108개 경로, 형상 제외 후 57,105 bytes |
| 품질 보고서 3종 | 18,199 bytes |
| 매니페스트 | SHA-256·크기·한계, 1,819 bytes |

총 크기는 166,578 bytes다. 원본 API 응답과 인증키는 포함하지 않았다. 도로 형상도 제외했으므로 이 번들로 지도를 재생성할 수는 없다. 웹 지도는 별도로 컴파일된 `src/data.json`을 사용한다.

이 번들은 실시간 현황이 아니라 `frozen_reviewed_derived_demo_not_live_data`다. 제출 전에 상위 데이터의 파생 산출물 재배포 조건을 최종 검토해야 한다.

### 라이브·사전 준비 입력 모드

라이브 API 수집은 데모 실행의 필수 조건이 아니다. 새 데이터를 사용할 때는 다음 두 단계를 분리한다.

1. API 키와 네트워크가 있는 환경에서 수집·정제·품질검사를 실행한다.
2. 센터에서는 검증된 CSV·JSON 경로를 `--risk-forecasts`, `--integrated-events`, `--travel-time-matrix` 등으로 명시한다.

## 4. 전처리·피처·모델 흐름 / Preprocessing, features, and modeling

```text
저장 위험예보·현장이벤트·이동시간
  → 매니페스트 SHA-256 무결성 검증
  → 요청 해석
  → 데이터 품질 게이트
  → 동일 링크 위험을 현장 작업으로 통합
  → 108개 도로망 이동시간 쌍 검사
  → 제약 기반 안전 우선·균형 운영 계획
  → 제약 독립 재검증
  → 지표·한계·수동 승인 필요 여부 설명
```

위험점수·도로망 경로·최적화는 모두 Python 규칙으로 실행한다. `torch`, `tensorflow`, `transformers`, `cupy`, `cuda-python`은 `requirements.txt`에 없다. GTX 1060 3GB는 실행에 사용하지 않는다.

## 5. 새 환경 실행 절차 / Clean-environment runbook

### POSIX 쉫n셀

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

cd 08_dashboard/roadops_map_v0_1
npm ci
cd ../..

.venv/bin/python 07_scripts/20261116_roadops_validate_center_environment_v0_1.py \
  --strict
```

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Set-Location 08_dashboard\roadops_map_v0_1
npm ci
Set-Location ..\..

.\.venv\Scripts\python.exe 07_scripts\20261116_roadops_validate_center_environment_v0_1.py --strict
```

### Agent 캐시 데모만 실행

```bash
.venv/bin/python 07_scripts/20261113_roadops_run_agent_flow_v0_1.py \
  --as-of '2026-11-16T18:00:00+09:00' \
  --strict
```

기본 입력이 이제 `demo/cached_inputs_v0_1`을 가리키므로 `config/.env`가 없어도 실행된다. 출력은 `02_outputs/data/agent_flow_v0_1`에 생성된다.

## 6. 실행 결과 / Observed results

관측 호스트: `macOS 27 arm64`, Python `3.14.3`, Node `22.16.0`, npm `10.9.2`, 10 logical CPU, RAM 24GB, NVIDIA GPU 없음.
아래 시간과 메모리는 2026-11-16 기준 실행 1회의 관측값이며 반복 실행마다 달라질 수 있다.

| 스모크 항목 | 결과 | 관측 시간 |
| --- | --- | ---: |
| 캐시 Agent 7단계 | `pass_with_limitations`, 대안 2개 | 0.782초 |
| Python 전체 160개 테스트 | 통과 | 0.315초 |
| 웹 승인 정책 6개 테스트 | 통과 | 0.133초 |
| 웹 생산 빌드 | 통과, `dist/index.html` 3,836,936 bytes | 0.603초 |
| 합산 | 4개 실행 모두 통과 | 1.833초 |

자식 프로세스 최대 RSS 430.766MB는 Python·Node 스모크 전체 중 가장 큰 자식 프로세스 기준이다. 각 단계별 메모리나 센터 장비의 최대치로 해석하면 안 된다.

Agent 캐시 데모는 기존 검증 결과를 유지했다.

- 현장 작업 9개 전부 배정
- 안전 우선: 도로망 이동 90.167분, 최대 팀 총소요 91.197분
- 균형 운영: 도로망 이동 99.999분, 최대 팀 총소요 91.197분
- 위험가중 커버리지 100%, 제약 위반 0건
- `manual_approval_required=true`

## 7. 재현성 게이트 / Reproducibility gates

| 게이트 | 판정 |
| --- | --- |
| 캐시 번들 6개 파일의 SHA-256·크기 | 통과 |
| Python 의존성 9종 설치 | 통과 |
| GPU·대형 LLM 필수 패키지 | 0개 |
| 사용자 절대경로 | 0건 |
| API 키 없는 캐시 Agent | 통과 |
| Python 전체 테스트 | 통과 |
| Node 버전·잠금파일·웹 테스트·빌드 | 통과 |
| 실제 센터 하드웨어 실행 | 미수행 |

환경 검증 JSON은 `02_outputs/data/center_environment_validation_v0_1/environment_validation.json`에 생성된다. 이 경로는 실행 산출물이므로 Git에 포함하지 않는다.

## 8. 한계와 센터 첫 실행 체크리스트 / Limitations and first-run checklist

### 현재 한계

- 실제 센터 PC에서는 아직 실행하지 않았다.
- 센터 OS와 Python·Node 사전 설치 여부가 확인되지 않았다.
- `npm audit`에서 현재 잠금파일에 moderate 1건, high 3건이 보고됐다. 정적 오프라인 결과물에 Vite 개발 서버를 포함하지는 않지만, 제출 전 보호된 런타임 호환성을 유지하며 잠금파일을 갱신·재검증해야 한다.
- 캐시 데모에 포함된 파생 데이터의 제출물 재배포 조건을 최종 확인해야 한다.
- 라이브 API 신선도·장애 복구는 별도 E2 장애 주입으로 평가했으며 실서버 SLA가 아니다.

### 실제 센터 PC 첫 실행

1. OS, Python, Node, npm 버전을 기록한다.
2. `npm ci`와 `pip install -r requirements.txt`를 완료한다.
3. 환경 검증 스크립트를 `--strict`로 실행한다.
4. `target_hardware_execution_observed` 필드를 실제 센터 검증 버전에서 갱신한다.
5. Agent 결과의 9개 작업·두 대안·제약 위반 0건을 대조한다.
6. 웹 `dist/index.html`을 열고 지도·승인·감사 로그 상호작용을 확인한다.

## 9. 재생성 / Reproduction

```bash
.venv/bin/python 07_scripts/20261116_roadops_prepare_cached_demo_v0_1.py
.venv/bin/python 07_scripts/20261116_roadops_validate_center_environment_v0_1.py \
  --strict
```

캐시 번들을 다시 만들 때는 검토된 `02_outputs` 산출물이 필요하다. 새 번들을 커밋하기 전에 행 수·품질상태·파일 해시를 다시 검토한다.
