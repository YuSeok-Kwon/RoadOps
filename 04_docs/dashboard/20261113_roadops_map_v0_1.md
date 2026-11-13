# RoadOps 제주 현장 운영 지도 v0.1

## 목적

위험점수, 순찰팀 자원 배분, 통제·폭우 What-if 부분 재계획 결과를 실제 제주 표준링크 좌표 위에서 한 번에 비교한다.

## 화면 구성

- `+0·1·3·6시간` 위험 링크 전환
- `안전 우선·균형 운영` 배분 대안 비교
- 도로 통제·폭우 What-if의 변경 전·후 경로 비교
- 링크 클릭 시 우선순위 점수, 상·하한, 근거 충족률, 점수 구성요소, 품질 플래그 표시
- 팀 출발점, 현장 점검 후보, 배분 경로를 실제 WGS84 링크 형상으로 표시
- 위험 커버리지, 배분 완료 수, 네트워크 이동시간, 제약 위반 수 표시
- 데이터 신선도와 공항·항만 유입압력 미연결 상태 표시

## 데이터 계약

| 지도 계층 | 입력 | 의미 |
| --- | --- | --- |
| 도로 배경 | 국토교통부 제주 표준링크 | 주요 도로의 실제 좌표 기반 배경 |
| 위험 링크 | `risk_forecasts_v0_1` | 사고확률이 아닌 운영 우선순위 시나리오 |
| 팀·업무 | 자원 입력·현장 업무 후보 | 데모 자원 시나리오와 점검 후보 |
| 배분 경로 | `optimized_allocation_v0_1` | 제한속도 기반 자유흐름 네트워크 경로 |
| 재계획 | `partial_replanning_v0_1` | 관측 사실이 아닌 통제·폭우 What-if |

결측값은 0으로 치환하지 않는다. 예측 근거가 부족한 링크는 점수와 구간을 `—`로 표시한다. 공항·항만 유입압력은 실응답을 확보하기 전까지 `데이터 미연결`로 표시하고 점수에 넣지 않는다.

## 재현

```bash
./.venv/bin/python 07_scripts/20261113_roadops_build_map_snapshot_v0_1.py --build-status complete

/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
  /Users/yu_seok/.codex/plugins/cache/openai-curated-remote/data-analytics/1.1.0-exp-homepage/scripts/data-app.mjs \
  build --project-dir "$(pwd)/08_dashboard/roadops_map_v0_1" --separate-data
```

## 검증 결과

- 지도 스냅샷 품질 상태: `pass`
- 위험 링크 지도 행: 44개
- 배분 경로 행: 18개
- 재계획 전·후 경로 행: 18개
- 누락된 필수 링크 형상: 0개
- 형상이 없는 배분·재계획 경로: 0개
- 데스크톱·좁은 화면 렌더링 및 `+6시간`, 도로 통제 What-if, 점검 대기열 연동 확인

## 한계

- 현재 화면은 자동 갱신되는 실시간 서비스가 아니라 저장소 스냅샷이다.
- 이동시간은 실시간 정체를 반영한 ETA가 아니다.
- 통제·폭우는 기능 검증용 What-if이며 실제 발생 사실로 해석하면 안 된다.
- 배분과 재계획은 담당자 승인 전 현장 지시로 사용할 수 없다.
