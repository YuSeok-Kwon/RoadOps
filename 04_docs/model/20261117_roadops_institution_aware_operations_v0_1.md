# RoadOps 기관·관할 기반 운영 모델 v0.1 / Institution-aware Operations v0.1

작성일 / Date: 2026-11-17

## 결론 / Decision

RoadOps의 자원·업무·최적화 모델에 관리기관, 도로 관할, 출동 승인권자, 경찰·소방 인계를 실제 제약과 출력 필드로 추가했다. 이 정보는 설명용 라벨이 아니다. 관리기관 또는 관할 권한이 맞지 않는 현장반은 배정 후보에서 제외되고, 승인 대기와 기관 인계 상태는 계획 결과와 감사 로그에 보존된다.

The resource, task, and optimizer models now carry managing agency, road jurisdiction, dispatch approver, and police/fire handoff data. Agency and jurisdiction mismatches make an assignment infeasible rather than merely adding a warning.

## 데이터 구조 / Data structure

### 자원 시나리오

- `governance.agencies`: 도·행정시·경찰·소방 등 기관 사전
- `governance.approvers`: 활성 출동 승인권자와 소속기관
- `governance.handoff_channels`: 경찰·소방 인계 채널과 가용상태
- `governance.defaults`: 기본 관리기관·관할·승인권자·인계 수준
- `teams[].managing_agency_id`: 현장반 소속 관리기관
- `teams[].support_agency_ids`: 협약에 따라 지원 가능한 다른 기관
- `teams[].authorized_road_jurisdictions`: 현장반이 작업 가능한 도로 관할

### 현장 업무

- `managing_agency_id`
- `road_jurisdiction`
- `jurisdiction_basis`
- `dispatch_approval_required`
- `dispatch_approver_id`
- `dispatch_approval_status`
- `response_mode`
- `handoff_actions[]`

인계 수준은 `none`, `notify`, `coordinate`, `transfer` 네 단계다. `transfer`는 도로 현장반 배정에서 제외하고 별도 `handoff_queue`로 분리한다. `coordinate`는 현장반 업무와 경찰·소방 공조가 동시에 필요한 공동 대응으로 유지한다.

## 안전 규칙 / Guardrails

1. 관리기관이 다르고 지원기관으로 등록되지 않은 현장반은 배정하지 않는다.
2. 현장반의 허용 관할에 포함되지 않은 도로 업무는 배정하지 않는다.
3. 존재하지 않거나 비활성인 승인권자·인계 채널은 입력 검증에서 차단한다.
4. 출동 승인 상태는 기본적으로 `pending`이며 자동 승인하지 않는다.
5. 경찰·소방 완전 이관 업무를 도로 현장반의 위험 커버리지로 계산하지 않는다.
6. 기존 기관 필드가 없는 입력은 호환을 위해 `legacy_unscoped`로 처리하되 경고를 남긴다.

## 데모 범위와 한계 / Demo scope and limits

현재 데모의 관할값 `demo_provincial_road_management_area`는 공식 도로대장 판정이 아니라 운영자 입력 가정이다. `jurisdiction_basis=operator_demo_assumption_not_official_road_register`로 이를 명시한다. 실제 적용 전에는 도로관리청·행정시 관할 원장과 조직별 승인 규정을 연결해야 한다.

데모 실행에서는 9개 업무가 모두 승인 대기 상태로 생성되고, 그중 1개 업무에 경찰 공조가 붙는다. 두 최적화 대안 모두 기관·관할 위반 0건으로 검증된다.

## 검증 / Validation

~~~bash
.venv/bin/pytest
./run_demo.sh
~~~

- 전체 테스트: 178개 통과
- 데모: 7개 Agent 도구 완료
- 배정업무: 9개
- 출동 승인 대기: 9개
- 경찰·소방 인계 액션: 1개
- 제약 위반: 0개
