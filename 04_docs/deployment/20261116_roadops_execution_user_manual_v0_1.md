# RoadOps 실행·사용자 매뉴얼 v0.1 / Execution & User Manual v0.1

작성일 / Date: 2026-11-16
적용 범위 / Scope: S2 실행 소스·Prompt 계약·Tool/API·의존성·환경변수 예시·사용자 절차

## 1. 3분 실행 / Three-minute run

RoadOps는 제주 도로 위험을 순찰 업무로 바꾸고, 제한된 팀·차량·근무시간 안에서 `안전 우선`과 `업무 균형` 두 배분안을 만드는 결정 지원 Agent다. 기본 데모는 외부 LLM과 API 키를 사용하지 않는다.

### POSIX (macOS·Linux)

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./run_demo.sh --as-of '2026-11-16T18:00:00+09:00'
```

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run_demo.ps1 --as-of "2026-11-16T18:00:00+09:00"
```

정상 종료하면 콘솔에 `pass_with_limitations`와 7개 Tool 상태가 표시된다. 이 상태는 실패가 아니라 저장된 데모 입력의 품질 한계를 결과에 표시했다는 뜻이다.

## 2. 실행 환경과 의존성 / Environment and dependencies

| 항목 | 요구사항 | 용도 |
| --- | --- | --- |
| Python | 3.11 이상, 3.15 미만 | Agent·품질검사·최적화 |
| Python packages | `requirements.txt` | 실행·테스트·분석 의존성의 범위 고정 |
| Node.js | `^20.19.0` 또는 `>=22.12.0` | 웹 대시보드 테스트·빌드 |
| Node packages | `package-lock.json` | 웹 의존성 재현 |
| GPU | 필요 없음 | 모든 제출 데모는 CPU로 실행 |
| 네트워크 | 설치 시에만 필요 | 의존성 설치 후 캐시 데모는 오프라인 실행 |

Python 패키지는 호환 범위를 제한했지만 해시로 완전 잠금한 lock은 아니다. Node 패키지는 `package-lock.json`을 `npm ci`로 설치한다.

## 3. 데모 모드와 입력 / Demo modes and inputs

### 기본: `cached_demo`

`demo/cached_inputs_v0_1` 안의 검토된 파생 스냅샷을 사용한다.

- 위험 예보 88행
- 통합 현장 이벤트 22행
- 팀→현장 도로망 경로 108개
- 품질 보고서 3종
- 파일별 SHA-256과 크기를 담은 `manifest.json`

이 데이터는 실시간 도로 현황이 아니다. 시연 결과를 현장 출동 지시로 사용하면 안 된다.

### 사전 준비 입력: `prepared_inputs`

API 수집과 품질검사를 외부에서 끝낸 CSV·JSON을 지정할 수 있다.

```bash
./run_demo.sh \
  --execution-mode prepared_inputs \
  --risk-forecasts path/to/risk_forecasts.csv \
  --integrated-events path/to/integrated_field_events.csv \
  --risk-quality path/to/risk_quality_report.json \
  --event-quality path/to/event_quality_report.json \
  --travel-time-matrix path/to/travel_time_matrix.json \
  --travel-quality path/to/travel_quality_report.json \
  --resources path/to/resource_plan.json \
  --output-dir path/to/output
```

입력 품질이 `fail`이거나 필수 경로가 없으면 Agent는 최적화를 진행하지 않는다.

## 4. Prompt 계약 / Prompt contract

현재 v0.1은 범용 LLM에 자유 문장을 보내는 구조가 아니다. 오프라인 재현성을 위해 제한된 한국어 요청을 파싱하고 검증된 Python Tool로 실행한다.

```text
팀 {team_count}개와 차량 {vehicle_count}대로 {duration_hours}시간 안에
{risk_horizon} 위험 기준 순찰계획을 만들어줘.
안전 우선과 업무 균형을 비교해줘.
```

`risk_horizon`은 `현재`, `1시간 후`, `3시간 후`, `6시간 후`를 지원한다. 실행 계약은 [`config/agent/roadops_agent_contract_v0_1.json`](../../config/agent/roadops_agent_contract_v0_1.json)에 고정했다. 각 결과에는 계약 SHA-256와 기대·관측 Tool 순서가 남는다.

## 5. Agent Tool 흐름 / Agent tool flow

| 순서 | Tool | 입력→출력 | 실패 시 행동 |
| ---: | --- | --- | --- |
| 1 | `request_interpreter` | 자연어 요청→구조화된 제약 | 요청 반려 |
| 2 | `data_quality_gate` | 자원·품질보고서→통과 여부 | 배분 차단 |
| 3 | `risk_task_builder` | 예보·이벤트→링크 단위 업무 | 활성 업무 0건이면 중단 |
| 4 | `travel_time_gate` | 업무·경로행렬→호환성 | 누락 경로가 있으면 중단 |
| 5 | `allocation_optimizer` | 자원·업무·경로→2개 대안 | 해가 없으면 수동 개입 |
| 6 | `plan_validator` | 배분안→중복·근무·경로 재검사 | 위반 대안 반환 금지 |
| 7 | `result_explainer` | 지표·한계→운영자 설명 | 결정적 템플릿으로 한계 표시 |

모든 실행은 `tool_trace.jsonl`에 입력 요약, 출력 요약, 상태, 한계를 남긴다. 결과의 `manual_approval_required` 값은 항상 `true`다.

## 6. API·키 구조 / API and key inventory

캐시 데모는 아래 API를 호출하지 않는다. 라이브 수집은 Agent 실행과 분리하며 `config/data_sources.json`이 단일 설정 원본이다.

| 환경변수 | 소스 | 제출 데모 |
| --- | --- | --- |
| `JEJU_CITS_API_KEY` | C-ITS 도로위험·통제·공사·노면기상 | 불필요 |
| `JEJU_ITS_API_KEY` | ITS 실시간·1시간·일간 교통 | 불필요 |
| `DATA_GO_KR_SERVICE_KEY` | 기상청·한국공항공사·한국해양교통안전공단 | 불필요 |
| `TAAS_API_KEY` | TAAS 세부링크 도로위험지수 | 불필요 |

키가 필요한 개발 환경에서만 `config/.env.example`을 `config/.env`로 복사한다. `config/.env`는 Git 추적 대상이 아니다.

```bash
cp config/.env.example config/.env
```

C-ITS·ITS 운영 URL은 문서상 HTTP다. 키가 평문으로 전송될 수 있어 실시간 호출은 기본 차단되며, 명시적 `--allow-insecure-http`와 운영자 판단이 필요하다.

## 7. 출력 읽기 / Reading outputs

기본 출력 경로는 `02_outputs/data/agent_flow_v0_1` 이다.

| 파일 | 의미 |
| --- | --- |
| `agent_result.json` | 파싱 요청, 현장 업무, 두 배분안, 검증, 최종 설명 |
| `quality_report.json` | 실행 상태, 입력·출력 경로, 실패 검사, Agent 계약 해시 |
| `tool_trace.jsonl` | 7개 Tool의 순서별 감사 기록 |

대표 캐시 데모의 기대값은 업무 9개 모두 배정, 위험가중 커버리지 100%, 제약 위반 0건이다. 도로망 이동시간은 실시간 ETA가 아니라 제한속도 기반 자유흐름 추정치다.

## 8. 웹 지도와 승인 흐름 / Web map and approval flow

### 설치·실행

```bash
cd 08_dashboard/roadops_map_v0_1
npm ci
npm test
npm run build
npm run dev -- --host 127.0.0.1
```

콘솔에 표시된 로컬 URL을 브라우저에서 연다. 정적 빌드는 `dist/index.html`에 생성된다.

### 운영자 순서

1. `+현재·1·3·6시간`을 바꾸며 위험 링크와 근거 충족률을 확인한다.
2. `안전 우선`과 `업무 균형` 대안의 커버리지·이동시간·팀별 업무를 비교한다.
3. 도로 통제·폭우 What-if에서 영향받는 팀과 변경 이유를 확인한다.
4. 자원이나 담당팀을 바꿨다면 제약 검사를 다시 실행한다.
5. 안전확인 3개, 담당자, 승인 사유를 모두 입력한 뒤에만 승인한다.
6. 승인 후 계획 지문과 브라우저 감사 로그를 확인한다.

현재 웹은 자원 수정 후 Python 최적화기와 실시간으로 재계산하지 않는다. 입력이 검증된 계획과 달라지면 `RESOURCE_REPLAN_REQUIRED`로 승인을 차단한다.

## 9. 제출 소스 자체검사 / Submission source validation

### POSIX

```bash
.venv/bin/python 07_scripts/20261116_roadops_validate_submission_source_v0_1.py \
  --strict
```

### Windows PowerShell

```powershell
.\.venv\Scripts\python.exe 07_scripts\20261116_roadops_validate_submission_source_v0_1.py --strict
```

이 검사는 다음을 확인한다.

- 필수 실행 소스·매뉴얼·requirements·웹 lock 파일 존재
- Prompt·7개 Tool·안전장치 계약의 구조
- `config/.env`·생성 산출물·가상환경·`node_modules`의 Git 미추적
- 현재 로컬에 설정된 키 값과 제출 후보 파일의 일치 0건
- 사용자 절대경로 0건과 캐시 데모 해시 무결성
- POSIX 원클릭 실행과 실제 7개 Tool 순서 일치

검사 결과는 `02_outputs/data/submission_source_validation_v0_1/submission_source_validation.json`에 저장되며 Git에 포함하지 않는다.

2026-11-16 관측 호스트에서 필수 13 / 13개가 통과했고, 제출 후보 파일에서 로컬에 설정된 비밀값 일치는 0건이었다. POSIX 실행기는 7개 Tool을 완주했다. 관측 호스트에 PowerShell이 없어 Windows 실행기는 정적 소스만 검사했으며, 이 한계로 판정은 `pass_with_limitations`다.

## 10. 문제 해결 / Troubleshooting

| 증상 | 확인 | 조치 |
| --- | --- | --- |
| `Python ... is required` | Python 미설치 또는 경로 누락 | Python 3.11~3.14 설치 후 가상환경 재생성 |
| `Required input is missing` | 캐시 번들 누락 | `demo/cached_inputs_v0_1/manifest.json`과 6개 파일 확인 |
| `Invalid agent contract` | Prompt·Tool 계약 수정 또는 파손 | 계약 JSON 복원 후 제출 검증 재실행 |
| `data_quality_gate_failed` | 입력 품질보고서 `fail` | 실패 검사를 수정하고 새 스냅샷 생성 |
| `travel_time_gate_failed` | 필요한 팀→작업 경로 누락 | 이동시간 행렬 재생성 |
| `npm ci` 실패 | Node 버전 또는 네트워크 | Node 지원 버전 확인, 프록시·레지스트리 확인 |
| 웹 승인 비활성 | 안전확인·담당자·사유 누락 또는 입력 변경 | 오류 카드 해소, 백엔드 재계획 후 승인 |

## 11. 보안·운영 한계 / Security and operational limits

- 원클릭 데모와 웹 스냅샷은 실시간 데이터가 아니다.
- 위험점수는 사고 확률이 아니라 현장 점검 우선순위다.
- 도로망 이동시간은 실시간 정체·회전제한을 반영하지 않는다.
- 항공·여객선 유입압력은 실응답 의미 검증이 끝나지 않아 점수에 반영하지 않았다.
- 웹 승인·감사 로그는 브라우저 `localStorage`에 저장되며 행정 전자결재가 아니다.
- 최종 실행 전에 반드시 담당자가 도로 통제·날씨·자원 상태를 재확인해야 한다.

## 12. 소스 구성 / Source map

| 구성 | 경로 |
| --- | --- |
| 원클릭 실행 | `run_demo.sh`, `run_demo.ps1` |
| Agent 진입점 | `07_scripts/20261113_roadops_run_agent_flow_v0_1.py` |
| Agent 오케스트레이션 | `05_src/roadops/agent_flow.py` |
| 자원·업무·최적화 | `05_src/roadops/resources.py`, `allocation_baselines.py`, `allocation_optimizer.py` |
| Prompt·Tool·안전장치 계약 | `config/agent/roadops_agent_contract_v0_1.json` |
| 제출 소스 목록 | `config/submission/source_manifest_v0_1.json` |
| API 설정 | `config/data_sources.json`, `config/.env.example` |
| 캐시 데모 | `demo/cached_inputs_v0_1` |
| 웹 지도·승인 UI | `08_dashboard/roadops_map_v0_1` |

이 S2 단계는 실행 소스와 매뉴얼을 검증한다. 최종 ZIP 생성·재해제·다른 경로 실행은 S4에서 별도로 검증한다.
