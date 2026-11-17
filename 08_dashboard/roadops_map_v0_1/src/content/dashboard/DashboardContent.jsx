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
  "demo-road-closure-v0.1": "도로 통제 가정",
  "demo-heavy-rain-v0.1": "폭우 가정",
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
const EVENT_LABELS = {
  road_weather: "노면기상",
  road_event: "도로 돌발상황",
  road_closure: "도로 통제",
  road_work: "도로 작업",
  traffic_accident: "교통사고",
};
const PRIORITY_LABELS = {
  first: "먼저",
  caution: "주의",
  normal: "일반",
};
const PRIORITY_COLORS = {
  first: "#e5484d",
  caution: "#f59e0b",
  normal: "#2f80ed",
};
const LINK_LOCATION_LABELS = {
  "4050418600": "서귀포시 남원읍 신례리 · 516로 인근",
  "4060024900": "서귀포시 예래동 · 1100로 산간 구간",
  "4050396600": "제주시 애월읍 봉성리 · 평화로 인근",
  "4050484600": "제주시 애월읍 광령리 · 평화로 인근",
  "4050484700": "제주시 애월읍 광령리 · 평화로 인근",
  "4050429802": "제주시 애월읍 소길리 · 평화로 인근",
  "4050456800": "제주시 애월읍 유수암리 · 평화로 인근",
  "4060438807": "서귀포시 남원읍 하례리 · 서성로 인근",
  "4050005521": "제주시 아라동 아라일동 · 중앙로 인근",
  "4060456800": "서귀포시 안덕면 동광리 · 광평교차로 인근",
};

function suggestedPriorityLevel(row) {
  if (["critical", "high"].includes(row?.risk_level)) return "first";
  if (row?.risk_level === "moderate") return "caution";
  return "normal";
}

function effectivePriorityLevel(row) {
  return row?.manual_priority_level || row?.effective_priority_level || suggestedPriorityLevel(row);
}

function priorityOrderValue(row) {
  const level = effectivePriorityLevel(row);
  const group = level === "first" ? 3 : level === "caution" ? 2 : 1;
  return group * 1000 + (Number(row?.priority_score) || 0);
}

function locationLabel(row) {
  return LINK_LOCATION_LABELS[String(row?.link_id)]
    || [row?.administrative_city, row?.administrative_unit, row?.road_name].filter(Boolean).join(" ")
    || "위치 확인 필요";
}

function HomeIcon({ className = "" }) {
  return <svg className={className} viewBox="0 0 20 20" aria-hidden="true">
    <path d="M2.5 9.1 10 2.8l7.5 6.3v8.1h-5v-5H7.6v5H2.5Z" />
  </svg>;
}

function InfoTip({ label, children }) {
  return <span className="info-tip-wrap">
    <button type="button" className="info-tip" aria-label={`${label} 설명`}>i</button>
    <span className="info-tip-popover" role="tooltip">{children}</span>
  </span>;
}

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

function priorityReasons(row) {
  const eventTypes = Array.isArray(row.event_types)
    ? row.event_types
    : String(row.event_types || "").split(/[|,]/).map((value) => value.trim()).filter(Boolean);
  const reasons = [];
  if (["critical", "high"].includes(row.risk_level)) {
    reasons.push(`위험 단계가 '${RISK_LABELS[row.risk_level]}'입니다.`);
  }
  if (Number(row.event_count) > 0) {
    const labels = eventTypes.map((value) => EVENT_LABELS[value] || "현장 위험정보").join("·");
    reasons.push(`${labels} ${number(row.event_count, 0)}건이 반영됐습니다.`);
  }
  if (row.mandatory) reasons.push("반드시 확인해야 하는 필수 점검 구간입니다.");
  reasons.push(`현장 확인 우선순위 ${number(row.priority_score)}점입니다.`);
  return reasons.slice(0, 3);
}

function routeKey(row) {
  return row ? `${row.alternative_id}:${row.team_id}:${row.task_id}:${row.sequence}` : null;
}

function pathFor(parts, project) {
  return parts.map((part) => part.map(([longitude, latitude], index) => {
    const [x, y] = project(longitude, latitude);
    return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ")).join(" ");
}

function mercatorCoordinate(longitude, latitude) {
  const limitedLatitude = Math.min(85.051129, Math.max(-85.051129, Number(latitude)));
  const latitudeRadians = limitedLatitude * Math.PI / 180;
  return [
    (Number(longitude) + 180) / 360,
    .5 - Math.log((1 + Math.sin(latitudeRadians)) / (1 - Math.sin(latitudeRadians))) / (4 * Math.PI),
  ];
}

function useProjection(backgroundRows, overlayRows) {
  return useMemo(() => {
    const points = [];
    [...backgroundRows, ...overlayRows].forEach((row) => {
      geometry(row.geometry_json).forEach((part) => part.forEach((point) => points.push(point)));
    });
    const mercatorPoints = points.map(([longitude, latitude]) => mercatorCoordinate(longitude, latitude));
    mercatorPoints.push(mercatorCoordinate(126.08, 33.58), mercatorCoordinate(126.98, 33.1));
    const minMercatorX = Math.min(...mercatorPoints.map(([x]) => x));
    const maxMercatorX = Math.max(...mercatorPoints.map(([x]) => x));
    const minMercatorY = Math.min(...mercatorPoints.map(([, y]) => y));
    const maxMercatorY = Math.max(...mercatorPoints.map(([, y]) => y));
    const width = 1000;
    const height = 590;
    const padding = 38;
    const xScale = (width - padding * 2) / Math.max(0.000001, maxMercatorX - minMercatorX);
    const yScale = (height - padding * 2) / Math.max(0.000001, maxMercatorY - minMercatorY);
    const scale = Math.min(xScale, yScale);
    const projectedWidth = (maxMercatorX - minMercatorX) * scale;
    const projectedHeight = (maxMercatorY - minMercatorY) * scale;
    const xOffset = (width - projectedWidth) / 2;
    const yOffset = (height - projectedHeight) / 2;
    const projectMercator = (x, y) => [
      xOffset + (x - minMercatorX) * scale,
      yOffset + (y - minMercatorY) * scale,
    ];
    return {
      width,
      height,
      project: (longitude, latitude) => projectMercator(...mercatorCoordinate(longitude, latitude)),
      projectMercator,
      mapToMercator: (x, y) => [
        minMercatorX + (x - xOffset) / scale,
        minMercatorY + (y - yOffset) / scale,
      ],
    };
  }, [backgroundRows, overlayRows]);
}

function BasemapTiles({ width, height, zoom, centerX, centerY, projectMercator, mapToMercator }) {
  const viewWidth = width / zoom;
  const viewHeight = height / zoom;
  const viewX = centerX - viewWidth / 2;
  const viewY = centerY - viewHeight / 2;
  const [minX, minY] = mapToMercator(viewX, viewY);
  const [maxX, maxY] = mapToMercator(viewX + viewWidth, viewY + viewHeight);
  const tileZoom = Math.min(13, 10 + Math.ceil(Math.log2(zoom)));
  const tileCount = 2 ** tileZoom;
  const startX = Math.max(0, Math.floor(Math.min(minX, maxX) * tileCount));
  const endX = Math.min(tileCount - 1, Math.floor(Math.max(minX, maxX) * tileCount));
  const startY = Math.max(0, Math.floor(Math.min(minY, maxY) * tileCount));
  const endY = Math.min(tileCount - 1, Math.floor(Math.max(minY, maxY) * tileCount));
  const tiles = [];
  for (let tileX = startX; tileX <= endX; tileX += 1) {
    for (let tileY = startY; tileY <= endY; tileY += 1) {
      const [x, y] = projectMercator(tileX / tileCount, tileY / tileCount);
      const [right, bottom] = projectMercator((tileX + 1) / tileCount, (tileY + 1) / tileCount);
      tiles.push(<image key={`${tileZoom}-${tileX}-${tileY}`}
        href={`https://tile.openstreetmap.org/${tileZoom}/${tileX}/${tileY}.png`}
        x={x} y={y} width={right - x} height={bottom - y} preserveAspectRatio="none" />);
    }
  }
  return <g className="basemap-tiles" aria-hidden="true">{tiles}</g>;
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
      <span className="legend-title">점검 우선순위</span>
      <span><i data-priority="first">먼저</i>가장 먼저 확인</span>
      <span><i data-priority="caution">주의</i>주의해서 확인</span>
      <span><i data-priority="normal">일반</i>일반 순서</span>
    </div>
    <div className="legend-group">
      <span className="legend-title">순찰 코스</span>
      <span><i className="legend-line" />팀 색 점선·이동</span>
      <span><i className="legend-start"><HomeIcon /></i>공개자료 기반 출발 거점</span>
      <span><i className="legend-point">1</i>팀 색 테두리·점검 순서</span>
      {showScenario && <span><i className="legend-before" />변경 전</span>}
      {showScenario && <span><i className="legend-after" />변경 후</span>}
    </div>
  </div>;
}

function RouteDetail({ route, routeRows, taskRows, teamRows, onClose }) {
  if (!route) return null;
  const team = teamRows.find((row) => row.team_id === route.team_id);
  const course = routeRows.filter((row) => row.team_id === route.team_id)
    .sort((left, right) => Number(left.sequence) - Number(right.sequence));
  const routeIndex = course.findIndex((row) => routeKey(row) === routeKey(route));
  const previous = routeIndex > 0 ? course[routeIndex - 1] : null;
  const task = taskRows.find((row) => row.task_id === route.task_id);
  return <aside className="map-route-detail" aria-label="선택한 순찰 경로 상세">
    <div className="route-detail-head">
      <div><span>선택한 이동 경로</span><strong>{team?.team_name || route.team_id} · {route.sequence}번째</strong></div>
      <button type="button" onClick={onClose} aria-label="경로 상세 닫기">닫기</button>
    </div>
    <dl className="route-detail-grid">
      <div><dt>출발</dt><dd>{previous ? previous.road_name : team?.start_location_name || "공개자료 기반 출발 거점"}</dd></div>
      <div><dt>도착·점검</dt><dd>{locationLabel(task || route)}</dd></div>
      <div><dt>이동 예상</dt><dd>{number(route.travel_minutes)}분</dd></div>
      <div><dt>현장 점검</dt><dd>{number(route.service_minutes, 0)}분</dd></div>
      <div><dt>누적 예상</dt><dd>{number(route.cumulative_minutes)}분</dd></div>
      <div><dt>도착지 위험</dt><dd>{RISK_LABELS[task?.risk_level] || "확인"} · {number(task?.priority_score)}점</dd></div>
    </dl>
    <div className="route-course-list">
      <span>전체 순찰 코스</span>
      <ol>
        <li><b className="course-home"><HomeIcon /></b>{team?.start_location_name || team?.team_name || "출발 거점"}</li>
        {course.map((item, index) => {
          const itemTask = taskRows.find((row) => row.task_id === item.task_id);
          return <li key={routeKey(item)} data-current={routeKey(item) === routeKey(route) || undefined}>
            <b style={{ "--team-color": TEAM_COLORS[item.team_id] || "#475569" }}>{index + 1}</b>
            <span><strong>{locationLabel(itemTask || item)}</strong><small>{item.road_name}</small></span>
            <small>{number(item.travel_minutes)}분 이동</small>
          </li>;
        })}
      </ol>
    </div>
  </aside>;
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
  selectedRoute,
  onSelectRisk,
  onSelectTask,
  onSelectRoute,
  onCloseRoute,
  scenarioId,
}) {
  const overlayRows = [...riskRows, ...routeRows, ...replanRows, ...impactRows];
  const { width, height, project, projectMercator, mapToMercator } = useProjection(backgroundRows, overlayRows);
  const [mapView, setMapView] = useState({ zoom: 1, centerX: width / 2, centerY: height / 2 });
  const scenarioActive = scenarioId !== "none";
  const affectedTeams = new Set(replanRows.map((row) => row.team_id));
  const taskByLink = new Map(taskRows.map((row) => [String(row.link_id), row]));
  const sequenceByTask = new Map(routeRows.map((row) => [String(row.task_id), Number(row.sequence)]));
  const teamByTask = new Map(routeRows.map((row) => [String(row.task_id), row.team_id]));

  const viewWidth = width / mapView.zoom;
  const viewHeight = height / mapView.zoom;
  const markerScale = 1 / mapView.zoom;
  const viewBox = `${mapView.centerX - viewWidth / 2} ${mapView.centerY - viewHeight / 2} ${viewWidth} ${viewHeight}`;
  const changeZoom = (factor) => {
    setMapView((current) => {
      const zoom = Math.min(5, Math.max(1, current.zoom * factor));
      const nextWidth = width / zoom;
      const nextHeight = height / zoom;
      return {
        zoom,
        centerX: Math.min(width - nextWidth / 2, Math.max(nextWidth / 2, current.centerX)),
        centerY: Math.min(height - nextHeight / 2, Math.max(nextHeight / 2, current.centerY)),
      };
    });
  };
  const resetZoom = () => setMapView({ zoom: 1, centerX: width / 2, centerY: height / 2 });
  const handleWheel = (event) => {
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    const pointerX = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    const pointerY = Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height));
    const zoomFactor = event.deltaY < 0 ? 1.14 : 1 / 1.14;
    setMapView((current) => {
      const zoom = Math.min(5, Math.max(1, current.zoom * zoomFactor));
      const currentWidth = width / current.zoom;
      const currentHeight = height / current.zoom;
      const worldX = current.centerX - currentWidth / 2 + pointerX * currentWidth;
      const worldY = current.centerY - currentHeight / 2 + pointerY * currentHeight;
      const nextWidth = width / zoom;
      const nextHeight = height / zoom;
      const nextCenterX = worldX + (0.5 - pointerX) * nextWidth;
      const nextCenterY = worldY + (0.5 - pointerY) * nextHeight;
      return {
        zoom,
        centerX: Math.min(width - nextWidth / 2, Math.max(nextWidth / 2, nextCenterX)),
        centerY: Math.min(height - nextHeight / 2, Math.max(nextHeight / 2, nextCenterY)),
      };
    });
  };

  return <div className="roadops-map-wrap" data-route-open={selectedRoute ? "true" : undefined}>
    {selectedRisk && <div className="map-focus-panel" data-risk={selectedRisk.risk_level}>
      <span>선택 구간</span>
      <strong>{locationLabel(taskByLink.get(String(selectedRisk.link_id)) || selectedRisk)}</strong>
      <div>
        <b>{number(selectedRisk.priority_score)}</b>
        <small>{RISK_LABELS[selectedRisk.risk_level] || "위험 미분류"} 단계</small>
      </div>
    </div>}
    <div className="map-zoom-controls" role="group" aria-label="지도 확대 축소">
      <button type="button" onClick={() => changeZoom(1 / 1.35)} aria-label="지도 축소"
        disabled={mapView.zoom <= 1}>−</button>
      <span aria-live="polite">{Math.round(mapView.zoom * 100)}%</span>
      <button type="button" onClick={() => changeZoom(1.35)} aria-label="지도 확대"
        disabled={mapView.zoom >= 5}>+</button>
      <button type="button" className="map-zoom-reset" onClick={resetZoom} disabled={mapView.zoom === 1}>전체</button>
    </div>
    <svg className="roadops-map" viewBox={viewBox} role="img" onWheel={handleWheel}
      aria-label="제주 위험 링크, 순찰팀 경로, 재계획 전후 비교 지도. 지도 위에서 마우스 휠로 확대하거나 축소할 수 있습니다.">
      <defs>
        <filter id="selected-glow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      <BasemapTiles width={width} height={height} zoom={mapView.zoom}
        centerX={mapView.centerX} centerY={mapView.centerY}
        projectMercator={projectMercator} mapToMercator={mapToMercator} />

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
              "--risk-opacity": String(Math.max(.48, Number(row.evidence_coverage_ratio) || .48)),
              filter: selected ? "url(#selected-glow)" : undefined,
            }} />;
        })}
      </g>

      <g className="plan-routes" data-reviewed-rows="plan_routes">
        {routeRows.filter((row) => !scenarioActive || !affectedTeams.has(row.team_id)).map((row) => {
          const selected = routeKey(selectedRoute) === routeKey(row);
          const path = pathFor(geometry(row.geometry_json), project);
          const select = () => onSelectRoute(row);
          return <g key={routeKey(row)} className={selected ? "route-segment selected" : "route-segment"}>
            <path className="route-hit-target" d={path} role="button" tabIndex={0}
              aria-label={`${teamRows.find((team) => team.team_id === row.team_id)?.team_name || row.team_id}, ${row.road_name}까지 ${number(row.travel_minutes)}분`}
              onClick={select} onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") select();
              }} />
            <path className="route-line" d={path} aria-hidden="true"
              style={{ "--team-color": TEAM_COLORS[row.team_id] || "#475569" }} />
          </g>;
        })}
      </g>

      {scenarioActive && <g className="replan-routes" data-reviewed-rows="replan_routes">
        {replanRows.map((row) => <path
          key={`${row.scenario_id}-${row.plan_stage}-${row.team_id}-${row.sequence}`}
          className={`replan-${row.plan_stage}`}
          d={pathFor(geometry(row.geometry_json), project)}
          style={{ "--team-color": TEAM_COLORS[row.team_id] || "#475569" }} />)}
      </g>}

      <g className="task-points" data-reviewed-rows="field_tasks">
        {taskRows.map((row) => {
          const [x, y] = project(row.longitude, row.latitude);
          const sequence = sequenceByTask.get(String(row.task_id));
          const teamId = teamByTask.get(String(row.task_id));
          const priorityLevel = effectivePriorityLevel(row);
          const selected = selectedRisk?.link_id === row.link_id;
          const select = () => onSelectTask(row.link_id);
          return <g key={row.task_id} className={selected ? "task-point selected" : "task-point"}
            transform={`translate(${x} ${y})`} role="button" tabIndex={0}
            aria-label={`${locationLabel(row)}, ${sequence ? `${sequence}번째 점검` : "배분 전"}`}
            onClick={select} onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") select();
            }} style={{ "--task-color": TEAM_COLORS[teamId] || "#475569" }}>
            <g transform={`scale(${markerScale})`}>
              <circle r={row.mandatory ? 9 : 8}
                data-excluded={row.excluded || undefined} data-mandatory={row.mandatory || undefined}>
                <title>{`${locationLabel(row)} · ${row.road_name}`}</title>
              </circle>
              <text y="3.5">{sequence || "?"}</text>
              <g className="priority-marker" data-priority={priorityLevel}
                data-manual={row.manual_priority_level ? "true" : undefined}
                transform="translate(13 -15)"
                style={{ "--priority-color": PRIORITY_COLORS[priorityLevel] || PRIORITY_COLORS.normal }}>
                <rect x="-2" y="-7" width={priorityLevel === "first" ? 26 : 24} height="13" rx="4" />
                <text x={priorityLevel === "first" ? 11 : 10} y="2">{PRIORITY_LABELS[priorityLevel]}</text>
                <title>{row.manual_priority_level
                  ? `담당자가 ${PRIORITY_LABELS[priorityLevel]} 순서로 조정했습니다.`
                  : `위험점수에 따른 ${PRIORITY_LABELS[priorityLevel]} 확인 구간입니다.`}</title>
              </g>
            </g>
          </g>;
        })}
      </g>

      <g className="team-points" data-reviewed-rows="teams">
        {teamRows.map((row) => {
          const [x, y] = project(row.start_longitude, row.start_latitude);
          return <g key={row.team_id} transform={`translate(${x} ${y})`}>
            <g transform={`scale(${markerScale})`}>
              <circle r="12" data-available={row.available === false ? "false" : "true"}
                style={{ fill: TEAM_COLORS[row.team_id] || "#475569" }}>
                <title>{`${row.team_name} · ${row.start_location_name || "출발 거점"} · ${row.available === false ? "비가용" : "가용"}`}</title>
              </circle>
              <path className="team-home-icon" d="M-7 -1 0 -7l7 6v8H2V2h-4v5h-5Z" />
              <text className="team-start-name" x="16" y="4">{row.team_name?.replace(" 순찰팀", "") || "순찰팀"}</text>
            </g>
          </g>;
        })}
      </g>
    </svg>
    <RouteDetail route={selectedRoute} routeRows={routeRows} taskRows={taskRows}
      teamRows={teamRows} onClose={onCloseRoute} />
    <a className="map-attribution" href="https://www.openstreetmap.org/copyright"
      target="_blank" rel="noopener">© OpenStreetMap contributors</a>
    <MapLegend showScenario={scenarioActive} />
  </div>;
}

function RiskDetail({ row, task, sourceRows, horizon }) {
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
      <span className="risk-band" data-risk-level={row.risk_level}>{RISK_LABELS[row.risk_level] || "미분류"} 단계</span>
    </div>
    <div className="risk-action-summary">
      <span>지금 할 일</span>
      <strong>{row.road_name} 현장 상태를 먼저 확인하세요.</strong>
      <p>{strongestDriver ? `우선순위에 가장 크게 반영된 항목은 ${strongestDriver.label}입니다.` : "점수를 설명할 근거가 부족해 추가 확인이 필요합니다."}</p>
    </div>
    <div className="risk-detail-grid">
      <div><span>위험 단계</span><b data-risk-level={row.risk_level}>{RISK_LABELS[row.risk_level] || "미분류"}</b></div>
      <div><span>예상 시각</span><b>{dateTime(row.target_at)}</b></div>
      <div><span>현장 위험정보</span><b>{Number(row.event_count) > 0 ? `${number(row.event_count, 0)}건 반영` : "추가 확인"}</b></div>
      <div><span>담당기관</span><b>{task?.managing_agency_name || "관할 확인 필요"}</b></div>
    </div>
    <div className="driver-list">
      <span>점수에 반영된 항목</span>
      {drivers.length ? <ul>{drivers.map((driver) => <li key={driver.raw}><strong>{driver.label}</strong><span>{driver.contribution != null ? `${number(driver.contribution)}점 반영` : "반영 정도 확인 필요"}</span></li>)}</ul> : <p>사용 가능한 근거가 없습니다.</p>}
    </div>
    <details className="confidence-details">
      <summary>데이터 신뢰도·연결 상태</summary>
      <div className="confidence-grid">
        <div><span>근거 반영률</span><b>{percentage(row.evidence_coverage_ratio)}</b></div>
        <div><span>도로 연결</span><b>{INTEGRATION_LABELS[row.integration_class] || "확인 필요"}</b></div>
        <div><span>예상 점수 범위</span><b>{number(row.score_lower_bound)}–{number(row.score_upper_bound)}</b></div>
      </div>
      {qualityFlags.length > 0 && <div className="quality-note">
        <span>확인할 데이터 한계</span>
        <ul>{qualityFlags.map((flag) => <li key={flag}>{qualityMessage(flag)}</li>)}</ul>
      </div>}
    </details>
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
    .sort((left, right) => priorityOrderValue(right) - priorityOrderValue(left));
  return <DataComponent variant="plain" id="task-queue" queryId="field_tasks" kind="table"
    title="먼저 확인할 도로" description="AI 제안 순서이며, 출동계획의 ‘도로·우선순위’ 단계에서 담당자가 이유를 남기고 조정할 수 있습니다."
    sourceRows={rows} displayRows={sorted} className="task-queue-card">
    <div className="task-queue-list">
      <div className="task-queue-head" aria-hidden="true">
        <span>순위</span><span>도로·담당</span><span>상태</span><span>점수</span>
      </div>
      {sorted.slice(0, 6).map((row, index) => <button type="button" key={row.task_id}
        className={selectedLinkId === row.link_id ? "selected" : ""} onClick={() => onSelect(row.link_id)}>
        <span className="task-rank">{String(index + 1).padStart(2, "0")}</span>
        <span className="task-copy"><strong>{locationLabel(row)}</strong><small>{row.road_name} · {row.managing_agency_name || "담당기관 확인 필요"}</small></span>
        <span className="task-risk-tag" data-priority={effectivePriorityLevel(row)}>
          {row.manual_priority_level ? "담당자 · " : ""}{PRIORITY_LABELS[effectivePriorityLevel(row)]}
        </span>
        <span className="task-score">{number(row.priority_score)}</span>
        <span className="task-hover-reason" role="tooltip">
          <strong>왜 먼저 확인하나요?</strong>
          {priorityReasons(row).map((reason) => <span key={reason}>{reason}</span>)}
        </span>
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
  const scenarioName = row.scenario_type === "road_closure" ? "도로 통제" : "폭우";
  const summary = `${scenarioName}로 영향을 받은 ${number(row.affected_team_count, 0)}개 팀의 남은 일정만 다시 계산했습니다.`;
  const reason = row.scenario_type === "road_closure"
    ? "통제 구간을 지나는 팀의 남은 일정에서 해당 구간을 제외하고 우회 경로를 찾았습니다. 다른 팀의 일정은 그대로 유지했습니다."
    : "폭우가 예상되는 도로는 위험도를 높이고 점검·이동시간을 여유 있게 잡았습니다. 해당 도로를 맡은 팀의 남은 일정만 다시 계산했으며, 다른 팀의 일정은 유지했습니다.";
  return <DataComponent variant="plain" id="replan-summary" queryId="scenario_summary" kind="custom"
    title="부분 재계획 설명" description="영향팀만 다시 계산하고 완료·고정·비영향 업무는 보존한 결과입니다."
    sourceRows={rows} displayRows={[row]}
    scopeFilters={[{ field: "scenario_id", label: "시나리오", value: scenarioId }]}
    className="replan-summary-card">
    <div className="replan-summary-head">
      <span className="approval-badge">책임자 확인 필요</span>
      <strong>{summary}</strong>
    </div>
    <p>{reason}</p>
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
  const [selectedRouteKey, setSelectedRouteKey] = useState(/** @type {any} */ (null));
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

  useEffect(() => {
    setSelectedRouteKey(null);
  }, [selectedPlan, horizon, scenarioId]);

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
      manual_priority_level: decision.manualPriorityLevel,
      manual_priority_reason: decision.priorityReason,
      effective_priority_level: decision.manualPriorityLevel || decision.suggestedPriorityLevel,
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
  const selectedRoute = routeRows.find((row) => routeKey(row) === selectedRouteKey) ?? null;
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

  const selectRoute = (row) => {
    setSelectedRouteKey(routeKey(row));
    setSelectedRiskId(row.link_id);
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
          <span className="toolbar-label">배분 대안
            <InfoTip label="배분 대안">
              <b>안전 우선</b>은 위험도가 높은 도로를 더 빨리 확인합니다.<br />
              <b>균형 운영</b>은 안전 기준을 지키면서 팀별 업무시간 차이를 줄입니다.
            </InfoTip>
          </span>
          <Dropdown label="배분 대안" value={selectedPlan}
            choices={planMetrics.map((row) => row.alternative_id)} choiceLabels={PLAN_LABELS}
            onChange={setSelectedPlan} />
        </div>
        <div className="toolbar-filter toolbar-filter-wide">
          <span className="toolbar-label">재계획 시나리오
            <InfoTip label="재계획 시나리오">
              <b>도로 통제</b>는 막힌 구간을 제외하고 영향팀만 우회합니다.<br />
              <b>폭우</b>는 위험도와 이동·점검시간을 여유 있게 잡아 영향팀만 다시 계산합니다.<br />
              두 항목 모두 실제 발생 정보가 아닌 비교용 가정입니다.
            </InfoTip>
          </span>
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
          description="OpenStreetMap 배경지도 위에 RoadOps 위험구간·순찰 경로·점검 순서를 올려 표시합니다. 현재 분석 범위는 국토교통부 국가표준링크 중 주요 간선도로 11개입니다."
          sourceRows={allRiskRows} displayRows={riskRows} sourceRowsByQuery={sourceRowsByQuery}
          scopeFilters={[
            { field: "horizon_hours", label: "예측 시점", value: String(horizon) },
            { field: "alternative_id", label: "배분 대안", value: selectedPlan },
            { field: "scenario_id", label: "재계획 시나리오", value: scenarioId },
          ]} className="roadops-map-card">
          <button type="button" className="map-guide-toggle" aria-expanded={mapGuideOpen}
            onClick={() => setMapGuideOpen((open) => !open)}>
            <span>지도 읽는 방법</span><small>배경지도 + 분석도로 11개 · {mapGuideOpen ? "접기" : "펼치기"}</small>
          </button>
          {mapGuideOpen && <div className="map-reading-guide" aria-label="지도 표시 설명">
            <p>배경에는 주변 도로·지명이 표시되지만, 점검 표시는 RoadOps가 분석한 주요 간선도로 11개 범위입니다. 주소는 좌표에서 찾은 인근 지역명이며 지번 확정값이 아닙니다.</p>
            <span><i data-guide="risk" /><b>우선순위 표식</b> 먼저·주의·일반을 도로선과 분리해 표시</span>
            <span><i data-guide="route" /><b>팀 색 점선</b> 순찰팀이 실제로 이동할 경로로, 누르면 소요시간과 전체 코스를 표시</span>
            <span><i data-guide="point" /><b>팀 색 숫자 원</b> 점검 순서 · 집 아이콘은 공개자료 기반 도로관리 거점</span>
          </div>}
          <RoadMap backgroundRows={rows("road_background")} riskRows={riskRows}
            taskRows={effectiveTaskRows} teamRows={effectiveTeamRows} routeRows={routeRows}
            replanRows={replanRows} impactRows={impactRows} selectedRisk={selectedRisk}
            selectedRoute={selectedRoute} onSelectRisk={selectRisk} onSelectTask={selectTask}
            onSelectRoute={selectRoute} onCloseRoute={() => setSelectedRouteKey(null)}
            scenarioId={scenarioId} />
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
            <RiskDetail row={selectedRisk} task={selectedTask} sourceRows={allRiskRows} horizon={horizon} />
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
