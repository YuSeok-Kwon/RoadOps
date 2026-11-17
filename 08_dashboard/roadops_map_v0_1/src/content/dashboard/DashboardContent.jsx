import React, { useEffect, useMemo, useState } from "react";

import {
  DataComponent,
  Dropdown,
  useDataApp,
  useDashboardTabs,
} from "../../data-app-public.jsx";
import { WorkflowPanel } from "./WorkflowPanel.jsx";
import "./dashboard.css";

const HORIZONS = [0, 1, 3, 6];
const TEAM_COLORS = {
  "team-east": "#2e3192",
  "team-north": "#1468b3",
  "team-west": "#6aa52d",
};
const RISK_COLORS = {
  critical: "#b42318",
  high: "#e5484d",
  moderate: "#f59e0b",
  low: "#2f80ed",
  minimal: "#6b7280",
};
const RISK_LABELS = {
  critical: "심각",
  high: "높음",
  moderate: "보통",
  low: "낮음",
  minimal: "최소",
};
const PLAN_LABELS = {
  safety_first: "안전 우선",
  balanced_operations: "균형 운영",
};
const SCENARIO_LABELS = {
  none: "기본 계획",
  "demo-road-closure-v0.1": "도로 통제 What-if",
  "demo-heavy-rain-v0.1": "폭우 What-if",
};
const AUTHORITY_STATUS_LABELS = {
  official_provincial_road_scope: "도 관할 근거 확인",
  admin_city_delegation_review_required: "행정시 위임 범위 확인 필요",
  operator_default: "관할 확인 필요",
};
const HANDOFF_STATUS_LABELS = {
  not_requested: "미요청",
  pending: "협조 요청 대기",
  accepted: "인계 접수",
  completed: "인계 완료",
};
const INTEGRATION_LABELS = {
  exact_link_id: "도로구간 번호로 정확히 연결",
  spatial_fallback: "가까운 도로 위치를 기준으로 연결",
  excluded: "분석 대상에서 제외",
};
const DRIVER_LABELS = {
  "event:active_road_event": "현재 도로 위험상황",
  "structural:taas": "과거 교통사고 위험",
  "traffic:speed_to_limit_ratio": "통행속도 저하",
  "weather_road:kma_wind_speed": "강풍 위험",
  "weather_road:cits_visibility": "시야 확보 상태",
  "weather_road:cits_friction": "노면 미끄럼 위험",
};
const QUALITY_LABELS = {
  cits_source_timestamp_unavailable: "도로 위험정보의 발생시각을 확인해야 합니다.",
  "component:traffic:missing_or_stale": "실시간 교통정보가 없거나 오래되었습니다.",
  "integration:spatial_fallback": "정확한 도로번호 대신 가까운 도로 위치로 연결했습니다.",
  "traffic:missing_link": "해당 구간의 교통정보 연결 지점을 찾지 못했습니다.",
  "traffic:missing_or_stale_at_scoring": "점수 계산 시 최신 교통정보를 사용하지 못했습니다.",
  "assumption:cits_visibility_unit_meters": "가시거리 단위를 미터로 가정했습니다.",
  "scenario:event_persistence_without_end_time": "종료 시각이 없는 위험정보를 계속 유효한 것으로 보았습니다.",
  "hold:insufficient_evidence_coverage": "사용할 수 있는 근거가 부족해 현장 확인 전에 추가 검토가 필요합니다.",
};

function geometry(value) {
  if (Array.isArray(value)) return value;
  try {
    const parsed = JSON.parse(value || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function number(value, digits = 1) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: digits }).format(Number(value));
}

function percentage(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Math.round(Number(value) * 100)}%`;
}

function dateTime(value) {
  if (!value) return "확인 불가";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function parseDriver(value) {
  const text = String(value || "");
  const splitAt = text.lastIndexOf(":");
  const key = splitAt > -1 ? text.slice(0, splitAt) : text;
  const contribution = splitAt > -1 ? Number(text.slice(splitAt + 1)) : null;
  return {
    raw: text,
    label: DRIVER_LABELS[key] || "기타 확인 요소",
    contribution: Number.isFinite(contribution) ? contribution : null,
  };
}

function qualityMessage(flag) {
  return QUALITY_LABELS[flag] || "일부 데이터의 최신성 또는 연결 상태를 추가로 확인해야 합니다.";
}

function pathFor(parts, project) {
  return parts.map((part) => part.map(([longitude, latitude], index) => {
    const [x, y] = project(longitude, latitude);
    return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ")).join(" ");
}

function useProjection(backgroundRows, overlayRows) {
  return useMemo(() => {
    const points = [];
    [...backgroundRows, ...overlayRows].forEach((row) => {
      geometry(row.geometry_json).forEach((part) => part.forEach((point) => points.push(point)));
    });
    const longitudes = points.map(([longitude]) => longitude);
    const latitudes = points.map(([, latitude]) => latitude);
    const minLongitude = Math.min(...longitudes, 126.08);
    const maxLongitude = Math.max(...longitudes, 126.98);
    const minLatitude = Math.min(...latitudes, 33.1);
    const maxLatitude = Math.max(...latitudes, 33.58);
    const width = 1000;
    const height = 590;
    const padding = 38;
    const xScale = (width - padding * 2) / Math.max(0.001, maxLongitude - minLongitude);
    const yScale = (height - padding * 2) / Math.max(0.001, maxLatitude - minLatitude);
    const scale = Math.min(xScale, yScale);
    const projectedWidth = (maxLongitude - minLongitude) * scale;
    const projectedHeight = (maxLatitude - minLatitude) * scale;
    const xOffset = (width - projectedWidth) / 2;
    const yOffset = (height - projectedHeight) / 2;
    return {
      width,
      height,
      project: (longitude, latitude) => [
        xOffset + (longitude - minLongitude) * scale,
        height - yOffset - (latitude - minLatitude) * scale,
      ],
    };
  }, [backgroundRows, overlayRows]);
}

function Metric({ label, value, note, tone = "neutral" }) {
  return <div className="roadops-metric" data-tone={tone}>
    <span>{label}</span>
    <strong>{value}</strong>
    <small>{note}</small>
  </div>;
}

function MapLegend({ showScenario }) {
  return <div className="roadops-map-legend" aria-label="지도 범례">
    <div className="legend-group">
      <span className="legend-title">도로 위험도</span>
      <span><i data-risk="high" />먼저 확인</span>
      <span><i data-risk="moderate" />주의 확인</span>
      <span><i data-risk="low" />일반 확인</span>
    </div>
    <div className="legend-group">
      <span className="legend-title">현장 표시</span>
      <span><i className="legend-line" />순찰팀 이동</span>
      <span><i className="legend-point" />점검 위치</span>
      <span><i className="legend-uncertain" />데이터 확인 필요</span>
      {showScenario && <span><i className="legend-before" />변경 전</span>}
      {showScenario && <span><i className="legend-after" />변경 후</span>}
    </div>
  </div>;
}

function RoadMap({
  backgroundRows,
  riskRows,
  taskRows,
  teamRows,
  routeRows,
  replanRows,
  impactRows,
  selectedRisk,
  onSelectRisk,
  scenarioId,
}) {
  const overlayRows = [...riskRows, ...routeRows, ...replanRows, ...impactRows];
  const { width, height, project } = useProjection(backgroundRows, overlayRows);
  const scenarioActive = scenarioId !== "none";
  const affectedTeams = new Set(replanRows.map((row) => row.team_id));

  return <div className="roadops-map-wrap">
    {selectedRisk && <div className="map-focus-panel" data-risk={selectedRisk.risk_level}>
      <span>선택 구간</span>
      <strong>{selectedRisk.road_name}</strong>
      <div>
        <b>{number(selectedRisk.priority_score)}</b>
        <small>{RISK_LABELS[selectedRisk.risk_level] || "위험 미분류"} 단계</small>
      </div>
    </div>}
    <svg className="roadops-map" viewBox={`0 0 ${width} ${height}`} role="img"
      aria-label="제주 위험 링크, 순찰팀 경로, 재계획 전후 비교 지도">
      <defs>
        <filter id="selected-glow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      <g className="map-grid" aria-hidden="true">
        {[160, 320, 480, 640, 800].map((x) => <line key={`x-${x}`} x1={x} x2={x} y1="20" y2={height - 20} />)}
        {[120, 240, 360, 480].map((y) => <line key={`y-${y}`} x1="20" x2={width - 20} y1={y} y2={y} />)}
      </g>

      <g className="map-background" data-reviewed-rows="road_background">
        {backgroundRows.map((row) => <path key={row.road_name}
          d={pathFor(geometry(row.geometry_json), project)} />)}
      </g>

      {scenarioActive && <g className="scenario-impact" data-reviewed-rows="scenario_impacts">
        {impactRows.map((row) => <path key={`${row.scenario_id}-${row.link_id}`}
          className={row.scenario_type === "road_closure" ? "impact-closure" : "impact-rain"}
          d={pathFor(geometry(row.geometry_json), project)} />)}
      </g>}

      <g className="plan-routes" data-reviewed-rows="plan_routes">
        {routeRows.filter((row) => !scenarioActive || !affectedTeams.has(row.team_id)).map((row) => <path
          key={`${row.alternative_id}-${row.team_id}-${row.sequence}`}
          d={pathFor(geometry(row.geometry_json), project)}
          style={{ "--team-color": TEAM_COLORS[row.team_id] || "#475569" }} />)}
      </g>

      {scenarioActive && <g className="replan-routes" data-reviewed-rows="replan_routes">
        {replanRows.map((row) => <path
          key={`${row.scenario_id}-${row.plan_stage}-${row.team_id}-${row.sequence}`}
          className={`replan-${row.plan_stage}`}
          d={pathFor(geometry(row.geometry_json), project)}
          style={{ "--team-color": TEAM_COLORS[row.team_id] || "#475569" }} />)}
      </g>}

      <g className="risk-links" data-reviewed-rows="risk_links">
        {riskRows.map((row) => {
          const selected = selectedRisk?.link_id === row.link_id;
          return <path key={`${row.horizon_hours}-${row.link_id}`}
            className={selected ? "risk-link selected" : "risk-link"}
            d={pathFor(geometry(row.geometry_json), project)}
            role="button" tabIndex={0}
            aria-label={`${row.road_name} 링크 ${row.link_id}, 위험점수 ${row.priority_score ?? "없음"}`}
            onClick={() => onSelectRisk(row)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") onSelectRisk(row);
            }}
            style={{
              "--risk-color": RISK_COLORS[row.risk_level] || RISK_COLORS.minimal,
              "--risk-width": `${Math.max(4, Math.min(10, 3 + (Number(row.priority_score) || 0) / 10))}px`,
              "--risk-opacity": String(Math.max(.48, Number(row.evidence_coverage_ratio) || .48)),
              filter: selected ? "url(#selected-glow)" : undefined,
              strokeDasharray: Number(row.uncertainty_width) > 0 ? "8 5" : undefined,
            }} />;
        })}
      </g>

      <g className="task-points" data-reviewed-rows="field_tasks">
        {taskRows.map((row) => {
          const [x, y] = project(row.longitude, row.latitude);
          return <circle key={row.task_id} cx={x} cy={y} r={row.mandatory ? 7 : 5}
            data-excluded={row.excluded || undefined} data-mandatory={row.mandatory || undefined}>
            <title>{`${row.road_name} · ${row.task_id}`}</title>
          </circle>;
        })}
      </g>

      <g className="team-points" data-reviewed-rows="teams">
        {teamRows.map((row) => {
          const [x, y] = project(row.start_longitude, row.start_latitude);
          return <g key={row.team_id} transform={`translate(${x} ${y})`}>
            <circle r="11" data-available={row.available === false ? "false" : "true"}
              style={{ fill: TEAM_COLORS[row.team_id] || "#475569" }}>
              <title>{`${row.team_name} · ${row.available === false ? "비가용" : "가용"}`}</title>
            </circle>
            <text y="4">{row.team_name?.slice(0, 1) || "팀"}</text>
          </g>;
        })}
      </g>
    </svg>
    <div className="map-place-label map-place-label--jeju">제주시</div>
    <div className="map-place-label map-place-label--seogwipo">서귀포시</div>
    <MapLegend showScenario={scenarioActive} />
  </div>;
}

function RiskDetail({ row, sourceRows, horizon }) {
  if (!row) return <div className="empty-detail">표시할 위험 링크가 없습니다.</div>;
  const drivers = String(row.risk_drivers || "").split(" | ").filter(Boolean).map(parseDriver);
  const qualityFlags = String(row.quality_flags || "").split("|")
    .map((flag) => flag.trim()).filter((flag) => flag && flag !== "none");
  const strongestDriver = [...drivers].sort((left, right) => Number(right.contribution || 0) - Number(left.contribution || 0))[0];
  return <DataComponent variant="plain" id="risk-detail" queryId="risk_links" kind="custom"
    title={`${row.road_name} 위험 요약`}
    description="왜 이 구간을 먼저 확인해야 하는지 쉬운 말로 설명합니다."
    sourceRows={sourceRows} displayRows={[row]}
    scopeFilters={[{ field: "horizon_hours", label: "예측 시점", value: horizon }, { field: "link_id", label: "링크", value: row.link_id }]}
    className="risk-detail-card">
    <div className="risk-score-block">
      <div><span>현장 확인 우선순위</span><strong>{number(row.priority_score)}</strong></div>
      <span className="risk-band">예상 범위 {number(row.score_lower_bound)}–{number(row.score_upper_bound)}</span>
    </div>
    <div className="risk-detail-grid">
      <div><span>위험 단계</span><b data-risk-level={row.risk_level}>{RISK_LABELS[row.risk_level] || "미분류"}</b></div>
      <div><span>사용 가능한 근거 반영률</span><b>{percentage(row.evidence_coverage_ratio)}</b></div>
      <div><span>도로 연결 상태</span><b>{INTEGRATION_LABELS[row.integration_class] || "확인 필요"}</b></div>
      <div><span>예상 시각</span><b>{dateTime(row.target_at)}</b></div>
    </div>
    <div className="risk-explanation">
      <span>왜 먼저 확인해야 하나요?</span>
      <strong>{strongestDriver ? `${strongestDriver.label}이 우선순위 점수에 가장 크게 반영됐습니다.` : "점수를 설명할 충분한 근거가 없어 추가 확인이 필요합니다."}</strong>
    </div>
    <div className="driver-list">
      <span>점수에 반영된 항목</span>
      {drivers.length ? <ul>{drivers.map((driver) => <li key={driver.raw}><strong>{driver.label}</strong><span>{driver.contribution != null ? `${number(driver.contribution)}점 반영` : "반영 정도 확인 필요"}</span></li>)}</ul> : <p>사용 가능한 근거가 없습니다.</p>}
    </div>
    {qualityFlags.length > 0 && <div className="quality-note">
      <span>확인할 데이터 한계</span>
      <ul>{qualityFlags.map((flag) => <li key={flag}>{qualityMessage(flag)}</li>)}</ul>
    </div>}
    <details className="technical-details">
      <summary>상세 기술정보</summary>
      <code>도로 연결: {row.integration_class || "none"}</code>
      <code>점수 근거: {row.risk_drivers || "none"}</code>
      <code>품질 코드: {row.quality_flags || "none"}</code>
    </details>
  </DataComponent>;
}

function AuthorityDetail({ task, authority, taskRows, authorityRows }) {
  const row = task || authority;
  if (!row) return <div className="empty-detail">선택한 링크의 관할 자료가 없습니다.</div>;
  const handoffs = task?.handoff_statuses || ["police", "fire"].map((type) => ({
    handoff_type: type,
    status: "not_requested",
    target_agency_name: authority?.[`${type}_agency_name`],
    contact_method: authority?.[`${type}_contact_method`],
    automation_status: authority?.[`${type}_automation_status`],
  }));
  const sourceRowsByQuery = {
    field_tasks: taskRows,
    governance_authorities: authorityRows,
  };
  const displayRows = [authority, task].filter(Boolean);
  return <DataComponent variant="plain" id="authority-detail" queryId="governance_authorities"
    queryIds={["governance_authorities", "field_tasks"]} kind="custom"
    title="관할·승인·인계"
    description="공식 도로분류·행정경계·사무위임 근거와 현장 인계 상태를 구분합니다."
    sourceRows={authorityRows} displayRows={displayRows} sourceRowsByQuery={sourceRowsByQuery}
    scopeFilters={[{ field: "link_id", label: "링크", value: row.link_id }]}
    className="authority-detail-card">
    <div className="authority-status-head" data-review={row.authority_status === "admin_city_delegation_review_required" || undefined}>
      <span>{AUTHORITY_STATUS_LABELS[row.authority_status] || "관할 상태 확인"}</span>
      <strong>{row.road_class || "도로"} {row.road_number ? `${row.road_number}호` : ""} · {row.road_name}</strong>
    </div>
    <dl className="authority-grid">
      <div><dt>담당기관</dt><dd>{row.managing_agency_name || "확인 필요"}</dd></div>
      <div><dt>행정시 구역</dt><dd>{[row.administrative_city, row.administrative_unit].filter(Boolean).join(" ") || "확인 필요"}</dd></div>
      <div><dt>도로 관할</dt><dd>{row.road_class && row.road_number ? `${row.road_class} ${row.road_number}호` : "확인 필요"}</dd></div>
      <div><dt>승인권자</dt><dd>{row.dispatch_approver_role || "운영기관 확인 필요"}</dd></div>
    </dl>
    <p className="authority-basis">{row.jurisdiction_basis}</p>
    <div className="handoff-list">
      {handoffs.map((handoff) => <div key={handoff.handoff_type}>
        <span>{handoff.handoff_type === "police" ? "경찰" : "소방"}</span>
        <strong>{HANDOFF_STATUS_LABELS[handoff.status] || handoff.status}</strong>
        <small>{handoff.target_agency_name || "연계 기관 확인 필요"}</small>
      </div>)}
    </div>
    {row.dispatch_approver_verification_status === "operator_configuration_required"
      && <p className="authority-warning">승인권자 직무는 정했지만 실명·당직자는 운영기관에서 지정해야 합니다.</p>}
  </DataComponent>;
}

function TaskQueue({ rows, selectedLinkId, onSelect }) {
  const sorted = [...rows].filter((row) => !row.excluded)
    .sort((left, right) => Number(right.priority_score) - Number(left.priority_score));
  return <DataComponent variant="plain" id="task-queue" queryId="field_tasks" kind="table"
    title="먼저 확인할 도로" description="점수가 높은 순서입니다. 도로를 누르면 이유와 담당기관을 확인할 수 있습니다."
    sourceRows={rows} displayRows={sorted} className="task-queue-card">
    <div className="task-queue-list">
      <div className="task-queue-head" aria-hidden="true">
        <span>순위</span><span>도로·담당</span><span>상태</span><span>점수</span>
      </div>
      {sorted.slice(0, 6).map((row, index) => <button type="button" key={row.task_id}
        className={selectedLinkId === row.link_id ? "selected" : ""} onClick={() => onSelect(row.link_id)}>
        <span className="task-rank">{String(index + 1).padStart(2, "0")}</span>
        <span className="task-copy"><strong>{row.road_name}</strong><small>{row.administrative_city || "구역 미확인"} · {row.managing_agency_name || row.link_id}</small></span>
        <span className="task-risk-tag" data-risk={row.risk_level}>{RISK_LABELS[row.risk_level] || "확인"}</span>
        <span className="task-score">{number(row.priority_score)}</span>
      </button>)}
    </div>
  </DataComponent>;
}

function PlanComparison({ rows, selectedPlan, onSelect }) {
  return <DataComponent variant="plain" id="plan-comparison" queryId="plan_metrics" kind="table"
    title="배분안 비교" description="안전을 우선할지, 팀별 업무를 고르게 나눌지 비교합니다."
    sourceRows={rows} displayRows={rows} className="plan-comparison-card">
    <div className="plan-comparison-table">
      <div className="plan-table-head"><span>대안</span><span>이동</span><span>최대 업무</span><span>편차</span></div>
      {rows.map((row) => <button type="button" key={row.alternative_id}
        className={selectedPlan === row.alternative_id ? "selected" : ""}
        onClick={() => onSelect(row.alternative_id)}>
        <strong>{PLAN_LABELS[row.alternative_id] || row.alternative_id}</strong>
        <span>{number(row.network_total_travel_minutes)}분</span>
        <span>{number(row.maximum_team_elapsed_minutes)}분</span>
        <span>{number(row.elapsed_minutes_variance)}</span>
      </button>)}
    </div>
  </DataComponent>;
}

function ReplanSummary({ rows, scenarioId }) {
  const row = rows.find((item) => item.scenario_id === scenarioId);
  if (!row) return <div className="replan-empty">
    <strong>기본 계획 표시 중</strong>
    <span>통제 또는 폭우 시나리오를 선택하면 변경 전·후 경로와 이유를 비교합니다.</span>
  </div>;
  return <DataComponent variant="plain" id="replan-summary" queryId="scenario_summary" kind="custom"
    title="부분 재계획 설명" description="영향팀만 다시 계산하고 완료·고정·비영향 업무는 보존한 결과입니다."
    sourceRows={rows} displayRows={[row]}
    scopeFilters={[{ field: "scenario_id", label: "시나리오", value: scenarioId }]}
    className="replan-summary-card">
    <div className="replan-summary-head">
      <span className="approval-badge">책임자 확인 필요</span>
      <strong>{row.summary}</strong>
    </div>
    <p>{row.change_reasons}</p>
    <div className="replan-deltas">
      <span><b>{row.affected_team_count}</b> 영향팀</span>
      <span><b>{Number(row.travel_minutes_delta) >= 0 ? "+" : ""}{number(row.travel_minutes_delta, 3)}</b> 이동분</span>
      <span><b>{number(row.violation_count_delta, 0)}</b> 제약 위반 증감</span>
    </div>
  </DataComponent>;
}

export function DashboardContent() {
  useDashboardTabs([{ id: "dashboard", label: "현장 운영 지도" }]);
  const { queries, snapshot, appTitle, setAppTitle } = useDataApp();
  const [horizonIndex, setHorizonIndex] = useState(0);
  const [selectedPlan, setSelectedPlan] = useState("safety_first");
  const [scenarioId, setScenarioId] = useState("none");
  const [selectedRiskId, setSelectedRiskId] = useState(/** @type {any} */ (null));
  const [workflowState, setWorkflowState] = useState(/** @type {any} */ (null));
  const [inspectorTab, setInspectorTab] = useState("priorities");
  const [mapGuideOpen, setMapGuideOpen] = useState(false);
  const [colorMode, setColorMode] = useState(() => {
    if (typeof localStorage === "undefined") return "dark";
    return localStorage.getItem("roadops-color-mode") === "light" ? "light" : "dark";
  });
  const horizon = HORIZONS[horizonIndex] ?? 0;

  useEffect(() => {
    if (appTitle !== snapshot.title) setAppTitle(snapshot.title);
  }, [appTitle, setAppTitle, snapshot.title]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.roadopsColorMode = colorMode;
    localStorage.setItem("roadops-color-mode", colorMode);
    return () => { delete root.dataset.roadopsColorMode; };
  }, [colorMode]);

  const rows = (queryId) => queries[queryId]?.rows ?? [];
  const metadata = /** @type {any} */ (rows("map_metadata")[0] ?? {});
  const allRiskRows = rows("risk_links");
  const riskRows = allRiskRows.filter((row) => Number(row.horizon_hours) === horizon && row.has_geometry);
  const selectedRisk = riskRows.find((row) => row.link_id === selectedRiskId)
    ?? [...riskRows].sort((left, right) => Number(right.priority_score) - Number(left.priority_score))[0]
    ?? null;
  const planMetrics = rows("plan_metrics");
  const selectedMetrics = planMetrics.find((row) => row.alternative_id === selectedPlan) ?? {};
  const workflowTasks = new Map((workflowState?.tasks ?? []).map((task) => [task.taskId, task]));
  const workflowResources = new Map((workflowState?.resources ?? []).map((resource) => [resource.teamId, resource]));
  const effectiveTaskRows = rows("field_tasks").map((row) => {
    const decision = workflowTasks.get(String(row.task_id));
    return decision ? {
      ...row,
      excluded: decision.excluded,
      fixed_team_id: decision.fixed ? decision.assignedTeamId : null,
      assigned_team_id: decision.assignedTeamId,
    } : row;
  });
  const effectiveTeamRows = rows("teams").map((row) => ({
    ...row,
    available: workflowResources.get(String(row.team_id))?.available ?? true,
  }));
  const selectedTask = effectiveTaskRows.find((row) => row.link_id === selectedRisk?.link_id) ?? null;
  const selectedAuthority = rows("governance_authorities")
    .find((row) => row.link_id === selectedRisk?.link_id) ?? null;
  const allRouteRows = rows("plan_routes");
  const routeRows = effectiveTaskRows.flatMap((task) => {
    const decision = workflowTasks.get(String(task.task_id));
    if (decision?.excluded) return [];
    const assignedTeamId = decision?.assignedTeamId
      ?? allRouteRows.find((row) => row.alternative_id === selectedPlan && row.task_id === task.task_id)?.team_id;
    if (!assignedTeamId) return [];
    const candidate = allRouteRows.find((row) => row.alternative_id === selectedPlan
      && row.task_id === task.task_id && row.team_id === assignedTeamId)
      ?? allRouteRows.find((row) => row.task_id === task.task_id && row.team_id === assignedTeamId);
    return candidate ? [{ ...candidate, alternative_id: selectedPlan }] : [];
  });
  const replanRows = rows("replan_routes").filter((row) => row.scenario_id === scenarioId);
  const impactRows = rows("scenario_impacts").filter((row) => row.scenario_id === scenarioId);
  const highRiskCount = riskRows.filter((row) => ["high", "critical"].includes(row.risk_level)).length;
  const scenarioChoices = ["none", ...rows("scenario_summary").map((row) => row.scenario_id)];
  const mapQueryIds = ["risk_links", "road_background", "field_tasks", "governance_authorities", "teams", "plan_routes", "replan_routes", "scenario_impacts"];
  const sourceRowsByQuery = Object.fromEntries(mapQueryIds.map((queryId) => [queryId, rows(queryId)]));

  const selectTask = (linkId) => {
    const match = riskRows.find((row) => row.link_id === linkId);
    if (match) {
      setSelectedRiskId(match.link_id);
      setInspectorTab("segment");
    }
  };

  const selectRisk = (row) => {
    setSelectedRiskId(row.link_id);
    setInspectorTab("segment");
  };

  return <article className="roadops-page" data-dashboard-layout="viewport" data-color-mode={colorMode}>
    <section className="roadops-toolbar" aria-label="지도 제어">
      <div className="toolbar-title">
        <div><span className="eyebrow">ROADOPS / JEJU</span><strong>도로 현장 운영 상황판</strong></div>
        <div className="data-status-group">
          <span className="roadops-freshness-badge stored">저장된 데이터 · 기준 {dateTime(metadata.latest_risk_target_at)}</span>
          <small>현재 자동 갱신 안 함</small>
        </div>
      </div>
      <div className="toolbar-controls">
        <div className="horizon-control">
          <span>예측 시점</span>
          <div className="horizon-buttons" role="group" aria-label="예측 시간 선택">
            {HORIZONS.map((hours, index) => <button type="button" key={hours}
              aria-pressed={horizonIndex === index} onClick={() => setHorizonIndex(index)}>
              {hours === 0 ? "현재" : `${hours}시간 후`}
            </button>)}
          </div>
        </div>
        <div className="toolbar-filter">
          <span>배분 대안</span>
          <Dropdown label="배분 대안" value={selectedPlan}
            choices={planMetrics.map((row) => row.alternative_id)} choiceLabels={PLAN_LABELS}
            onChange={setSelectedPlan} />
        </div>
        <div className="toolbar-filter toolbar-filter-wide">
          <span>재계획 시나리오</span>
          <Dropdown label="재계획 시나리오" value={scenarioId}
            choices={scenarioChoices} choiceLabels={SCENARIO_LABELS} onChange={setScenarioId} />
        </div>
        <div className="theme-control">
          <span>화면 테마</span>
          <div className="theme-buttons" role="group" aria-label="화면 테마 선택">
            <button type="button" aria-pressed={colorMode === "dark"}
              onClick={() => setColorMode("dark")}>다크</button>
            <button type="button" aria-pressed={colorMode === "light"}
              onClick={() => setColorMode("light")}>화이트</button>
          </div>
        </div>
      </div>
    </section>

    <section className="roadops-kpis">
      <DataComponent variant="plain" id="allocation-kpis" queryId="plan_metrics" kind="metrics"
        title="운영 요약" description="선택한 예측 시점과 배분 대안의 핵심 운영 지표입니다."
        showHeading={false} showActions={false} sourceRows={planMetrics} displayRows={[selectedMetrics]}
        scopeFilters={[{ field: "alternative_id", label: "배분 대안", value: selectedPlan }]}>
        <div className="roadops-metric-grid">
          <Metric label="점검 대상" value={riskRows.length} note={horizon === 0 ? "현재 확인 후보" : `${horizon}시간 후 확인 후보`} />
          <Metric label="먼저 확인" value={highRiskCount} note="위험 단계가 높은 도로" tone={highRiskCount ? "warning" : "neutral"} />
          <Metric label="배분 완료" value={`${selectedMetrics.assigned_task_count ?? "—"}/${selectedMetrics.candidate_task_count ?? "—"}`} note="제외 조건 통과 업무" tone="positive" />
          <Metric label="제약 위반" value={number(selectedMetrics.constraint_violation_count, 0)} note={scenarioId === "none" ? "기본 배분안" : "가정 상황 · 책임자 확인 필요"} tone="positive" />
        </div>
      </DataComponent>
    </section>

    <div className="roadops-workspace">
      <section className="roadops-map-column">
        <DataComponent variant="plain" id="roadops-map" queryId="risk_links" queryIds={mapQueryIds}
          kind="custom" title="어디를 먼저 확인해야 하나요?"
          description="제주 전체 도로망이 아닙니다. 국토교통부 국가표준링크 중 주요 간선도로 11개를 배경으로 사용하고, 위험점수·출동업무·배분·재계획에 필요한 링크를 강조합니다."
          sourceRows={allRiskRows} displayRows={riskRows} sourceRowsByQuery={sourceRowsByQuery}
          scopeFilters={[
            { field: "horizon_hours", label: "예측 시점", value: String(horizon) },
            { field: "alternative_id", label: "배분 대안", value: selectedPlan },
            { field: "scenario_id", label: "재계획 시나리오", value: scenarioId },
          ]} className="roadops-map-card">
          <button type="button" className="map-guide-toggle" aria-expanded={mapGuideOpen}
            onClick={() => setMapGuideOpen((open) => !open)}>
            <span>지도 읽는 방법</span><small>주요 간선도로 11개 기준 · {mapGuideOpen ? "접기" : "펼치기"}</small>
          </button>
          {mapGuideOpen && <div className="map-reading-guide" aria-label="지도 표시 설명">
            <p>제주 전체 도로망이 아니라 운영 데모에 사용하는 주요 간선도로와 현장 대상만 표시합니다.</p>
            <span><i data-guide="risk" /><b>위험 도로선</b> 빨강 먼저 · 주황 주의 · 파랑 일반</span>
            <span><i data-guide="route" /><b>팀 경로선</b> 보라 동부 · 파랑 북부 · 초록 서부</span>
            <span><i data-guide="point" /><b>흰 원</b> 현장 점검 위치</span>
          </div>}
          <RoadMap backgroundRows={rows("road_background")} riskRows={riskRows}
            taskRows={effectiveTaskRows} teamRows={effectiveTeamRows} routeRows={routeRows}
            replanRows={replanRows} impactRows={impactRows} selectedRisk={selectedRisk}
            onSelectRisk={selectRisk} scenarioId={scenarioId} />
        </DataComponent>
        <ReplanSummary rows={rows("scenario_summary")} scenarioId={scenarioId} />
      </section>

      <aside className="roadops-inspector">
        <div className="inspector-tabs" role="tablist" aria-label="현장 운영 정보">
          {[{ id: "priorities", label: "우선순위 목록" }, { id: "segment", label: "선택 구간" }, { id: "plan", label: "출동계획" }].map((tab) =>
            <button type="button" role="tab" key={tab.id} aria-selected={inspectorTab === tab.id}
              onClick={() => setInspectorTab(tab.id)}>{tab.label}</button>)}
        </div>
        <div className="inspector-tab-content" role="tabpanel">
          {inspectorTab === "priorities" && <TaskQueue rows={effectiveTaskRows}
            selectedLinkId={selectedRisk?.link_id} onSelect={selectTask} />}
          {inspectorTab === "segment" && <>
            <RiskDetail row={selectedRisk} sourceRows={allRiskRows} horizon={horizon} />
            <AuthorityDetail task={selectedTask} authority={selectedAuthority}
              taskRows={rows("field_tasks")} authorityRows={rows("governance_authorities")} />
          </>}
          {inspectorTab === "plan" && <>
            <PlanComparison rows={planMetrics} selectedPlan={selectedPlan} onSelect={setSelectedPlan} />
            <WorkflowPanel teams={rows("teams")} tasks={rows("field_tasks")}
              governanceRows={rows("governance_authorities")}
              routes={rows("plan_routes")} planMetrics={planMetrics} metadata={metadata}
              selectedPlan={selectedPlan} scenarioId={scenarioId} onStateChange={setWorkflowState} />
          </>}
        </div>
      </aside>
    </div>

    <footer className="roadops-disclaimer">
      운영 우선순위 시나리오이며 사고확률이 아닙니다. 모든 배분·재계획 결과는 현장 지시 전 책임자의 확인과 확정이 필요합니다.
    </footer>
  </article>;
}
