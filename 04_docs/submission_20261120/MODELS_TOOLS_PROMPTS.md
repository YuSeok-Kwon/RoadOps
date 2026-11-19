# Agent 구성·Prompt·모델·Tool/API

## 현재 구현과 개발자 역할

권유석이 데이터 수집·정제, Agent Tool, 웹 운영 화면, 경로·시간 계산, 검증 및 결과 문서를 구현했습니다. 목표는 제주 데이터를 근거로 점검 대상·항목·방문 계획을 제안하고, 상황이 바뀌었을 때 필요한 시간과 제약을 담당자가 확인하게 하는 것입니다.

현재 실행에는 학습한 ML 모델, 다운로드한 모델 가중치, 외부 LLM API가 없습니다. Python의 제한 문법 요청 해석·품질 검사·제약 배분과 JavaScript의 점수·방향성 도로망 경로 계산을 사용합니다. 웹의 ‘AI 자동선택’은 이 자동화 도구의 UI 명칭입니다. GPT-5.4 mini API를 이용한 자연어 요청 해석·설명 보조는 기획서의 **검토 계획**이며, 현재 검증 결과에 포함되지 않습니다. 모델 파일이나 LLM 인증키는 제출물에 없습니다.

## Prompt와 단계별 계약

원문: `config/agent/roadops_agent_contract_v0_1.json`. 범용 자유 대화가 아닌 아래 제한 요청 형식을 지원합니다.

> 팀 {team_count}개와 차량 {vehicle_count}대로 {duration_hours}시간 안에 {risk_horizon} 위험 기준 순찰계획을 만들어줘. 안전 우선과 업무 균형을 비교해줘.

시점은 현재·1시간 후·3시간 후·6시간 후입니다. 실제 자원 파일과 수가 다르면 오류로 차단합니다.

| 순서 | Tool ID | 동작·주요 구현 |
|---|---|---|
| 1 | `request_interpreter` | 한국어 요청을 팀·차량·시간·시점·대안으로 구조화 — `agent_flow.parse_agent_request` |
| 2 | `data_quality_gate` | 자원·결측·품질 보고서 검사 — `agent_flow._quality_gate` |
| 3 | `risk_task_builder` | 동일 도로 이벤트를 현장 작업으로 구성 — `allocation_baselines.build_field_tasks` |
| 4 | `travel_time_gate` | 도로망·이동시간·작업 ID 호환 검사 — `agent_flow._travel_matrix_errors` |
| 5 | `allocation_optimizer` | 인력·차량·시간·필수 조건 내 안전/균형 대안 계산 — `allocation_optimizer.build_constraint_allocation` |
| 6 | `plan_validator` | 중복·시간·경로·필수 제약 재검증 — `agent_flow._validate_plans` |
| 7 | `result_explainer` | 지표·누락·한계·승인 필요성 설명 — `agent_flow._explain` |

Python 코드 경로는 `05_src/roadops`입니다. 웹 구현은 `08_dashboard/roadops_map_v0_1/src/content/dashboard`의 우선순위·점검 근거·작업계획·통제 재계산 모듈과 Worker를 사용합니다. 웹과 CLI는 데이터 시점·사용자 흐름이 다르며, 하나의 실행 결과로 합쳐 제시하지 않습니다.

## 자동 판단과 담당자 판단

자동화 범위: 자료 품질 확인, 점수 산정, 점검 항목 제안, 방문 순서·시간 계산, 통제 구간 제외, 완료 기록 보존, 중복·시간·조건 재검증, 결과·근거 표시.

담당자 범위: 실제 노면·통행 가능성 확인, 출동 인원·시간·필수 방문 설정, 계획 검토·결정, 시간 연장·지원 여부 판단. 프로그램이 실제 출동 명령이나 기관 결재를 자동 집행하지 않습니다. 시간 초과 비교안은 `previewOnly`, `review_required`로 표시하고 확정을 차단합니다.

## API·라이브러리

수집 API의 상세 URL·환경변수·결합 키는 `config/data_sources.json`에 있습니다. 지도 배경은 OpenStreetMap 타일, 경로 그래프는 국토교통부 표준노드링크입니다. 설치 의존성은 루트 `requirements.txt`, 제출용 최소 목록 `requirements-runtime.txt`, 앱 `package.json`/`package-lock.json`에 있습니다. 실제 검증 환경의 버전은 `evidence/python-environment.txt`, `evidence/validation.json`을 참조합니다.

Python은 httpx(수집), pyshp·pyproj(공간 처리), pytest(검증)를 사용합니다. 웹은 React·Vite, 지도·배분 계산용 자체 JavaScript 모듈과 Web Worker를 사용합니다. 현재 계산은 CPU 중심이며 CUDA·GPU 모델 적재·LLM 네트워크 호출이 없습니다.
