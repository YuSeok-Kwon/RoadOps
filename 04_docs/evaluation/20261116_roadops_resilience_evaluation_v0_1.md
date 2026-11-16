# RoadOps 장애·복구 평가 v0.1 / Resilience Evaluation v0.1

작성일 / Date: 2026-11-16

## 1. 목적 / Objective

실시간 데이터나 계산 단계가 실패했을 때 RoadOps가 정상 결과처럼 표시하지 않고 안전한 상태로 전환되는지 확인한다. 핵심 원칙은 다음 다섯 가지다.

- 자동 출동을 허용하지 않고 모든 결과에 담당자 승인을 유지한다.
- 실패·미수집 값을 `0`으로 대체하지 않는다.
- 캐시를 쓸 때는 캐시 출처·나이·품질 상태와 실시간이 아님을 표시한다.
- 잘못된 링크와 기한이 지난 데이터는 점수·배분에서 제외하고 근거를 보존한다.
- 최적화가 불능해도 하드 제약을 암묵적으로 완화하지 않는다.

## 2. 평가 방법 / Method

본 결과는 실제 운영 장애 통계가 아니라, 검토된 기준 산출물에 6개 장애를 인위적으로 주입한 결과다. 실행 기준시각은 `2026-11-16T12:00:00+09:00`, 캐시 최대 허용 나이는 120분으로 고정했다.

장애 주입에 사용한 기준 산출물은 Agent 결과 `pass_with_limitations`, 수동 승인 필수, 위험점수 25행, 도로 참조 링크 136개, 이동시간 경로 108개, 최적화 대안 2개다.

## 3. 결과 / Results

| 장애 시나리오 | 안전 상태 | 복구 행동 | 핵심 판정 | 결과 |
| --- | --- | --- | --- | --- |
| API 실패 + 30분 캐시 | `degraded` | `cache_replay` | 출처·나이 표시, 실시간 표현 금지 | 통과 |
| API 실패 + 캐시 없음 | `hold` | `await_fresh_data` | 순위·배분 중단 | 통과 |
| 121분 경과 스냅샷 | `hold` | `refresh_or_manual_review` | 위험점수 미생성 | 통과 |
| 참조망에 없는 도로 링크 | `excluded` | `preserve_for_link_review` | 제외 사유·원본 근거 보존 | 통과 |
| 전역 실행 가능한 배분안 없음 | `hold` | `manual_intervention` | 플랜 미생성, 하드 제약 유지 | 통과 |
| 설명 생성기 실패 | `degraded` | `deterministic_explanation_fallback` | 검증된 Tool 결과만 템플릿으로 복사 | 통과 |

총 6개 시나리오의 53개 자동 검사가 모두 통과했다. 평가 결과 지문은 `d151b12bdb696b8558a72b7e6cfa582e0dcaee50e62004f2f2b94519887774a1`이다.

## 4. 설명 실패 안전장치 / Explanation fallback

설명 생성 단계가 실패해도 임의로 문장을 만들지 않는다. 기존 Agent가 검증한 구조화 결과의 대안 ID, 배정·미배정 건수, 위험가중 커버리지, 도로망 이동시간, 제약 위반 건수, 한계만 결정적 템플릿으로 복사한다. Tool 결과가 유효하지 않으면 설명도 생성하지 않고 `hold`로 전환한다.

## 5. 판정과 한계 / Decision and limitations

E2 v0.1은 `pass`다. 상태별 복구 정책과 실패 시 금지해야 할 행동을 코드·자동 테스트·평가 산출물로 고정했다.

다만 이 평가는 저장된 데모 산출물에 실패 조건을 주입한 단위·통합 정책 평가다. 실제 외부 API 지연·부분 응답·장시간 중단, 다중 장애, 서버 재시작 후 복구시간은 측정하지 않았다. 설명 실패도 실제 LLM 서비스 장애가 아니라 결과 생성기 실패를 가정한 시뮬레이션이다. 따라서 운영 SLA나 실제 복구시간으로 해석하면 안 된다.

## 6. 재현 / Reproduction

```bash
.venv/bin/python 07_scripts/20261116_roadops_evaluate_resilience_v0_1.py \
  --evaluated-at '2026-11-16T12:00:00+09:00' \
  --strict
```

생성 결과:

- `02_outputs/data/resilience_evaluation_v0_1/resilience_evaluation.json`
- `02_outputs/data/resilience_evaluation_v0_1/quality_report.json`
