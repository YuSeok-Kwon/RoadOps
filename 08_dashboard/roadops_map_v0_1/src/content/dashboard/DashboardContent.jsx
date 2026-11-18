import React, { useEffect, useMemo, useState } from "react";

import {
  DataComponent,
  Dropdown,
  useDataApp,
  useDashboardTabs,
} from "../../data-app-public.jsx";
import { WorkflowPanel } from "./WorkflowPanel.jsx";
import {
  buildManualRoutes,
  historicalPlaces,
  nearbyRows,
  routeSummary,
  tasksForDepot,
} from "./operation-flow.js";
import radarSnapshot from "../assets/kma-radar.json";
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
  "gateway:airport_inflow_pressure": "제주공항 시간대별 유입 압력",
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
const OPERATION_SESSION_KEY = "roadops-operation-session-v1";
const OPERATION_PHASES = new Set(["select", "review", "manual", "manual-review", "ai-config", "ai-result"]);

function readOperationSession() {
  const fallback = {
    phase: "select",
    selectedDepotId: null,
    manualTaskIds: [],
    horizonIndex: 0,
    selectedPlan: "safety_first",
    scenarioId: "none",
    selectedRiskId: null,
    selectedRouteKey: null,
    mapExpanded: false,
    surfaceView: "map",
    mapLayers: { accidentHotspots: true, complaintHotspots: false, crimeCaution: false },
  };
  if (typeof sessionStorage === "undefined") return fallback;
  try {
    const stored = JSON.parse(sessionStorage.getItem(OPERATION_SESSION_KEY) || "null");
    if (!stored || typeof stored !== "object") return fallback;
    return {
      ...fallback,
      ...stored,
      phase: OPERATION_PHASES.has(stored.phase) ? stored.phase : fallback.phase,
      manualTaskIds: Array.isArray(stored.manualTaskIds) ? stored.manualTaskIds.map(String) : [],
      surfaceView: ["map", "weather"].includes(stored.surfaceView) ? stored.surfaceView : fallback.surfaceView,
      mapLayers: { ...fallback.mapLayers, ...(stored.mapLayers || {}) },
    };
  } catch {
    return fallback;
  }
}
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
  return row?.location_label
    || LINK_LOCATION_LABELS[String(row?.link_id)]
    || [row?.administrative_city, row?.administrative_unit, row?.road_name].filter(Boolean).join(" ")
    || "위치 확인 필요";
}

// Open-source Lucide v0.468.0 icon geometry (ISC) is embedded locally so the
// protected dashboard runtime does not need a new package dependency.
const OPEN_ICON_NODES = {
  warehouse: [
    ["path", { d: "M22 8.35V20a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8.35A2 2 0 0 1 3.26 6.5l8-3.2a2 2 0 0 1 1.48 0l8 3.2A2 2 0 0 1 22 8.35Z" }],
    ["path", { d: "M6 18h12" }],
    ["path", { d: "M6 14h12" }],
    ["rect", { width: 12, height: 12, x: 6, y: 10 }],
  ],
  accident: [
    ["path", { d: "m21 8-2 2-1.5-3.7A2 2 0 0 0 15.646 5H8.4a2 2 0 0 0-1.903 1.257L5 10 3 8" }],
    ["path", { d: "M7 14h.01" }],
    ["path", { d: "M17 14h.01" }],
    ["rect", { width: 18, height: 8, x: 3, y: 10, rx: 2 }],
    ["path", { d: "M5 18v2" }],
    ["path", { d: "M19 18v2" }],
  ],
  complaint: [
    ["path", { d: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" }],
    ["path", { d: "M13 8H7" }],
    ["path", { d: "M17 12H7" }],
  ],
  crime: [
    ["path", { d: "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" }],
    ["path", { d: "M12 8v4" }],
    ["path", { d: "M12 16h.01" }],
  ],
  police: [
    ["path", { d: "M3.85 8.62a4 4 0 0 1 4.78-4.77 4 4 0 0 1 6.74 0 4 4 0 0 1 4.78 4.78 4 4 0 0 1 0 6.74 4 4 0 0 1-4.77 4.78 4 4 0 0 1-6.75 0 4 4 0 0 1-4.78-4.77 4 4 0 0 1 0-6.76Z" }],
    ["path", { d: "m9 12 2 2 4-4" }],
  ],
  fire: [
    ["path", { d: "M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z" }],
  ],
  layers: [
    ["path", { d: "M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z" }],
    ["path", { d: "M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12" }],
    ["path", { d: "M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17" }],
  ],
  warning: [
    ["path", { d: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" }],
    ["path", { d: "M12 9v4" }],
    ["path", { d: "M12 17h.01" }],
  ],
};

function OpenIcon({ name, className = "", strokeWidth = 1.8, ...props }) {
  const nodes = OPEN_ICON_NODES[name] || OPEN_ICON_NODES.layers;
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round"
    className={className} aria-hidden="true" {...props}>
    {nodes.map(([tag, attributes], index) => React.createElement(tag, { ...attributes, key: index }))}
  </svg>;
}

function HomeIcon({ className = "", ...props }) {
  return <OpenIcon name="warehouse" className={className} strokeWidth={2} {...props} />;
}

function LayerIcon({ type, className = "" }) {
  return <OpenIcon name={type} className={`layer-icon ${className}`.trim()} data-type={type} />;
}

function MapFacilityGlyph({ kind }) {
  return kind === "police"
    ? <path className="facility-glyph" d="M0-5 4-3.5v3.2C4 2.3 2.4 4.1 0 5.3-2.4 4.1-4 2.3-4-.3v-3.2Z" />
    : <path className="facility-glyph" d="M1-5c.3 2-1.7 2.6-.7 4.3.8-.8 1-1.6.9-2.4C4-1.1 4.4 1 3.6 3.1 3 4.7 1.7 5.5 0 5.5s-3-1-3.6-2.5c-.7-1.8-.1-3.4 1.6-4.8-.1 1.3.1 2.2.7 2.7C-1.4-.9-.6-3.3 1-5Z" />;
}

/** @param {{available: any, value?: any, unavailableLabel: any}} props */
function LayerStatus({ available, value = null, unavailableLabel }) {
  if (available) {
    if (value === undefined || value === null || value === "" || value === "연결") return null;
    return <b className="layer-status-connected">{value}</b>;
  }
  return <span className="layer-status-warning" role="img"
    aria-label={unavailableLabel} title={unavailableLabel}>
    <LayerIcon type="warning" />
  </span>;
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
    <span className="roadops-metric-copy">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </span>
  </div>;
}

function weatherTemperature(row) {
  const minimum = Number(row?.temperature_min_c);
  const maximum = Number(row?.temperature_max_c);
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum)) return "확인 불가";
  if (minimum === maximum) return `${number(minimum)}°C`;
  return `${number(minimum)}–${number(maximum)}°C`;
}

function weatherRainfall(row) {
  const label = String(row?.rainfall_amount_label ?? "").trim();
  return label || "자료 없음";
}

function weatherRainfallDetail(row) {
  const amount = weatherRainfall(row);
  if (amount === "0mm") return "강수 없음";
  return `${Number(row?.horizon_hours) === 0 ? "최근 1시간 강수량" : "시간당 예상 강수량"} ${amount}`;
}

function weatherRainfallMetric(row) {
  const amount = weatherRainfall(row);
  return amount === "0mm" ? "없음" : amount;
}

function weatherWindDetail(row) {
  return row?.maximum_wind_speed_mps == null
    ? "최대풍속 확인 불가"
    : `최대풍속 ${number(row.maximum_wind_speed_mps)}m/s`;
}

function validationSummary(row) {
  if (!row) return { label: "검증 정보 없음", tone: "pending", detail: "아직 예측 검증 결과가 없습니다." };
  if (row.validation_status === "descriptive_only") {
    return { label: "현재값 산출", tone: "current", detail: row.note };
  }
  if (row.validation_status === "pending") {
    return { label: "검증 표본 대기", tone: "pending", detail: row.note };
  }
  const detail = `비교 ${number(row.matched_points, 0)}건 · RoadOps 오차 ${number(row.forecast_mae, 2)} · 현재값 유지 오차 ${number(row.persistence_mae, 2)}`;
  if (row.validation_status === "insufficient_evidence") {
    return { label: `초기 검증 ${number(row.matched_points, 0)}건`, tone: "limited", detail: `${detail}. ${row.note}` };
  }
  return {
    label: Number(row.mae_improvement) > 0 ? "기준선 대비 개선" : "개선 미확인",
    tone: Number(row.mae_improvement) > 0 ? "pass" : "limited",
    detail,
  };
}

function WeatherForecastStrip({ rows, validationRows, horizon, onSelect }) {
  const validation = validationSummary(validationRows.find((row) => Number(row.horizon_hours) === horizon));
  return <DataComponent variant="plain" id="weather-forecast-strip" queryId="weather_forecast"
    queryIds={["weather_forecast", "forecast_validation"]}
    kind="custom" title="제주 단기 기상" description="기상청 예보 격자의 제주 전역 범위입니다."
    showHeading={false} showActions={false} sourceRows={[...rows, ...validationRows]} displayRows={rows}>
    <div className="weather-strip-inner">
      <div className="weather-strip-title">
        <span>제주 단기 기상</span>
        <small>기상청 · 제주 전역 격자 범위</small>
        <b className="forecast-validation-badge" data-tone={validation.tone}
          title={validation.detail}>{validation.label}</b>
      </div>
      <div className="weather-forecast-list">
        {rows.map((row) => <button type="button" key={row.horizon_hours}
          data-selected={Number(row.horizon_hours) === horizon || undefined}
          data-status={row.status} onClick={() => onSelect(Number(row.horizon_hours))}>
          <span>{Number(row.horizon_hours) === 0 ? "현재" : `${row.horizon_hours}시간 후`}</span>
          <strong>{weatherTemperature(row)}</strong>
          <small>{row.sky_summary}</small>
          <em>
            <b>{weatherRainfallDetail(row)}</b>
            <i>{weatherWindDetail(row)}</i>
          </em>
        </button>)}
      </div>
    </div>
  </DataComponent>;
}

function weatherHumidityDetail(row) {
  const minimum = Number(row?.humidity_min_percent);
  const maximum = Number(row?.humidity_max_percent);
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum)) return "확인 불가";
  if (minimum === maximum) return `${number(minimum, 0)}%`;
  return `${number(minimum, 0)}–${number(maximum, 0)}%`;
}

function weatherSourceLabel(row) {
  const source = String(row?.forecast_sources || "");
  if (source.includes("ultra_short")) return "기상청 초단기예보";
  if (source.includes("village")) return "기상청 단기예보";
  return "기상청 예보";
}

function WeatherMapView({ backgroundRows, weatherRows, radarRows, selectedWeather, horizon, onSelectHorizon }) {
  const { width, height, project, projectMercator, mapToMercator } = useProjection(backgroundRows, []);
  const mapView = { zoom: 1, centerX: width / 2, centerY: height / 2 };
  const viewBox = `0 0 ${width} ${height}`;
  const coverage = Number(selectedWeather?.coverage_ratio);
  const gridCount = Number(selectedWeather?.grid_count);
  const usableGridCount = Number(selectedWeather?.usable_grid_count);
  const currentView = Number(horizon) === 0;
  const radarFrame = radarRows.find((row) => Number(row.horizon_hours) === Number(horizon));
  const radarReady = radarFrame?.status === "ready" && radarFrame?.image_data_uri;

  return <div className="operation-weather-view">
    <div className="weather-view-summary" aria-label="선택 시점 기상 요약">
      <div className="weather-view-time">
        <span>{currentView ? "현재 기상" : `${horizon}시간 후 예보`}</span>
        <strong>{dateTime(selectedWeather?.target_at)}</strong>
        <small>{weatherSourceLabel(selectedWeather)} · 제주 전역 격자 종합</small>
      </div>
      <dl className="weather-view-metrics">
        <div><dt>기온</dt><dd>{weatherTemperature(selectedWeather)}</dd></div>
        <div className="weather-rainfall-metric"><dt>{currentView ? "최근 1시간 강수량" : "시간당 예상 강수량"}</dt><dd>{weatherRainfallMetric(selectedWeather)}</dd><small>{selectedWeather?.precipitation_summary || "강수 형태 확인 불가"}</small></div>
        <div><dt>습도</dt><dd>{weatherHumidityDetail(selectedWeather)}</dd></div>
        <div><dt>최대풍속</dt><dd>{selectedWeather?.maximum_wind_speed_mps == null ? "확인 불가" : `${number(selectedWeather.maximum_wind_speed_mps)}m/s`}</dd></div>
      </dl>
    </div>

    <div className="weather-view-body">
      <div className="weather-radar-map" aria-label="제주 강수 분포 지도">
        {radarReady ? <img className="weather-radar-image" src={radarFrame.image_data_uri}
          alt={`${currentView ? "레이더 강수 실황" : `${horizon}시간 후 강수예측`} ${dateTime(radarFrame.valid_at)}`} /> : <svg viewBox={viewBox} role="img" aria-label="제주도 기상 배경지도">
          <BasemapTiles width={width} height={height} zoom={mapView.zoom}
            centerX={mapView.centerX} centerY={mapView.centerY}
            projectMercator={projectMercator} mapToMercator={mapToMercator} />
          <g className="weather-road-context" aria-hidden="true">
            {backgroundRows.map((row, index) => <path key={row.link_id || index}
              d={pathFor(geometry(row.geometry_json), project)} />)}
          </g>
        </svg>}
        {!radarReady && <div className="weather-radar-status" data-current={currentView || undefined}>
          <span>{currentView ? "현재 강수 관측" : `${horizon}시간 후 강수 예측`}</span>
          <strong>강수영상을 불러오지 못했습니다</strong>
          <p>{currentView
            ? "마지막 정상 레이더 영상을 확인 중입니다. 수치 기상정보는 계속 제공됩니다."
            : "해당 예측 시점의 영상을 확인 중입니다. 수치 예보는 계속 제공됩니다."}</p>
        </div>}
        <span className="weather-map-badge">{radarReady
          ? `${currentView ? "레이더 실황" : "강수예측"} · ${dateTime(radarFrame.valid_at)}`
          : selectedWeather?.sky_summary || "기상 확인"}</span>
        <span className="weather-map-attribution">{radarReady ? "기상청 API허브" : "© OpenStreetMap contributors"}</span>
      </div>

      <aside className="weather-timeline" aria-label="시간대별 기상 예보">
        <header><span>시간대별 기상</span><small>같은 시점으로 지도와 위험도를 함께 바꿉니다.</small></header>
        <div className="weather-timeline-list">
          {weatherRows.map((row) => {
            const rowHorizon = Number(row.horizon_hours);
            return <button type="button" key={rowHorizon}
              aria-pressed={rowHorizon === Number(horizon)} onClick={() => onSelectHorizon(rowHorizon)}>
              <span>{rowHorizon === 0 ? "현재" : `${rowHorizon}시간 후`}</span>
              <strong>{weatherTemperature(row)}</strong>
              <small>{weatherRainfallDetail(row)} · {weatherWindDetail(row)}</small>
            </button>;
          })}
        </div>
        <dl className="weather-data-quality">
          <div><dt>사용 격자</dt><dd>{Number.isFinite(usableGridCount) && Number.isFinite(gridCount) ? `${usableGridCount}/${gridCount}` : "확인 불가"}</dd></div>
          <div><dt>자료 반영률</dt><dd>{Number.isFinite(coverage) ? percentage(coverage) : "확인 불가"}</dd></div>
        </dl>
        <p>강수량은 제주 전역 격자의 범위이며 한 지점의 정확한 측정값이 아닙니다.</p>
      </aside>
    </div>
  </div>;
}

function MapLegend({
  showScenario,
  showAccidentHotspots,
  showTrafficAccidents,
  showComplaintHotspots,
  showCrimeCaution,
  showPoliceFacilities,
  showFireFacilities,
}) {
  return <div className="roadops-map-legend" aria-label="지도 범례">
    <div className="legend-group">
      <span className="legend-title">점검 우선순위</span>
      <span><i data-priority="first">먼저</i>가장 먼저 확인</span>
      <span><i data-priority="caution">주의</i>주의해서 확인</span>
      <span><i data-priority="normal">일반</i>일반 순서</span>
    </div>
    {showAccidentHotspots && <div className="legend-group">
      <span title="한국도로교통공단 선정 교통사고 다발지역"><i className="legend-accident" />교통사고 다발</span>
    </div>}
    {showTrafficAccidents && <div className="legend-group">
      <span title="생활안전지도 연간 교통사고 다발구역"><i className="legend-traffic-overlay" />교통사고 비교</span>
    </div>}
    {showComplaintHotspots && <div className="legend-group">
      <span title="신고자 정보를 제거한 3건 이상 민원 집계"><i className="legend-complaint" />민원 집계</span>
    </div>}
    {showCrimeCaution && <div className="legend-group">
      <span title="경찰청 연간 범죄주의구간 밀도분석"><i className="legend-crime" />범죄주의</span>
    </div>}
    {(showPoliceFacilities || showFireFacilities) && <div className="legend-group">
      {showPoliceFacilities && <span title="경찰관서"><i className="legend-service police"><LayerIcon type="police" /></i>경찰</span>}
      {showFireFacilities && <span title="소방서·119안전센터"><i className="legend-service fire"><LayerIcon type="fire" /></i>소방</span>}
    </div>}
    <div className="legend-group">
      <span className="legend-title">순찰</span>
      <span title="순찰팀 이동 경로"><i className="legend-line" />이동</span>
      <span title="공개자료 기반 출발 거점"><i className="legend-start"><HomeIcon /></i>출발</span>
      <span title="점검 순서"><i className="legend-point">1</i>순서</span>
      <span title="현재 계획에서 미배정"><i className="legend-point legend-unassigned">미</i>미배정</span>
      <span title="점검 제외 조건 적용"><i className="legend-point legend-excluded">제</i>제외</span>
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
  accidentRows,
  complaintRows,
  crimeCautionRows,
  emergencyFacilityRows,
  trafficAccidentOverlayRows,
  showAccidentHotspots,
  showComplaintHotspots,
  showCrimeCaution,
  showPoliceFacilities,
  showFireFacilities,
  showTrafficAccidents,
  selectedRisk,
  selectedRoute,
  onSelectRisk,
  onSelectTask,
  onSelectRoute,
  onCloseRoute,
  scenarioId,
  horizon,
  mode = "select",
  selectedDepotId = null,
  manualTaskIds = [],
}) {
  const overlayRows = [...riskRows, ...routeRows, ...replanRows, ...impactRows];
  const { width, height, project, projectMercator, mapToMercator } = useProjection(backgroundRows, overlayRows);
  const [mapView, setMapView] = useState({ zoom: 1, centerX: width / 2, centerY: height / 2 });
  const scenarioActive = scenarioId !== "none";
  const affectedTeams = new Set(replanRows.map((row) => row.team_id));
  const taskByLink = new Map(taskRows.map((row) => [String(row.link_id), row]));
  const sequenceByTask = new Map(routeRows.map((row) => [String(row.task_id), Number(row.sequence)]));
  const teamByTask = new Map(routeRows.map((row) => [String(row.task_id), row.team_id]));
  const manualSequenceByTask = new Map(manualTaskIds.map((taskId, index) => [String(taskId), index + 1]));
  const selectedDepot = teamRows.find((row) => row.team_id === selectedDepotId) ?? null;

  useEffect(() => {
    if (!selectedDepot) {
      setMapView({ zoom: 1, centerX: width / 2, centerY: height / 2 });
      return;
    }
    const [centerX, centerY] = project(selectedDepot.start_longitude, selectedDepot.start_latitude);
    const zoom = mode === "manual" || mode === "ai-result" ? 2.5 : 1.8;
    setMapView({ zoom, centerX, centerY });
  }, [selectedDepot?.team_id, selectedDepot?.start_longitude, selectedDepot?.start_latitude, mode]);

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
      <span>{horizon === 0 ? "현재 선택 구간" : `${horizon}시간 후 선택 구간`}</span>
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

      {showTrafficAccidents && trafficAccidentOverlayRows.map((row) => {
        const [minLongitude, minLatitude, maxLongitude, maxLatitude] = row.bbox || [];
        const [left, top] = project(minLongitude, maxLatitude);
        const [right, bottom] = project(maxLongitude, minLatitude);
        return <image key={row.layer_id} className="traffic-accident-overlay"
          href={row.data_url} x={left} y={top} width={right - left} height={bottom - top}
          preserveAspectRatio="none">
          <title>생활안전지도·한국도로교통공단 2025년 교통사고다발구역</title>
        </image>;
      })}

      {showCrimeCaution && crimeCautionRows.map((row) => {
        const [minLongitude, minLatitude, maxLongitude, maxLatitude] = row.bbox || [];
        const [left, top] = project(minLongitude, maxLatitude);
        const [right, bottom] = project(maxLongitude, minLatitude);
        return <image key={row.layer_id} className="crime-caution-overlay"
          href={row.data_url} x={left} y={top} width={right - left} height={bottom - top}
          preserveAspectRatio="none">
          <title>생활안전지도·경찰청 2025년 범죄주의구간 밀도분석</title>
        </image>;
      })}

      <g className="map-grid" aria-hidden="true">
        {[160, 320, 480, 640, 800].map((x) => <line key={`x-${x}`} x1={x} x2={x} y1="20" y2={height - 20} />)}
        {[120, 240, 360, 480].map((y) => <line key={`y-${y}`} x1="20" x2={width - 20} y1={y} y2={y} />)}
      </g>

      <g className="map-background" data-reviewed-rows="road_background">
        {backgroundRows.map((row) => <path key={row.road_name}
          d={pathFor(geometry(row.geometry_json), project)} />)}
      </g>

      {showAccidentHotspots && <g className="accident-hotspots" data-reviewed-rows="accident_hotspots">
        {accidentRows.map((row) => <path key={row.hotspot_id}
          d={pathFor(geometry(row.geometry_json), project)}>
          <title>{`${row.location_name} · ${row.analysis_year}년 사고 ${row.accident_count}건·사상 ${row.casualty_count}명`}</title>
        </path>)}
      </g>}

      {showComplaintHotspots && <g className="complaint-hotspots" data-reviewed-rows="complaint_hotspots">
        {complaintRows.map((row) => {
          const [x, y] = project(row.longitude, row.latitude);
          const category = row.top_categories?.[0]?.category || "도로 민원";
          const radius = Math.min(15, 6 + Math.sqrt(Number(row.complaint_count) || 0));
          return <g key={row.hotspot_id} transform={`translate(${x} ${y}) scale(${markerScale})`}>
            <circle r={radius}>
              <title>{`${category} 중심 · ${number(row.complaint_count, 0)}건 · 약 500m 격자 비식별 집계`}</title>
            </circle>
            <text y="3">{number(row.complaint_count, 0)}</text>
          </g>;
        })}
      </g>}

      <g className="emergency-facilities" data-reviewed-rows="emergency_facilities">
        {emergencyFacilityRows.filter((row) => (
          row.facility_kind === "police" ? showPoliceFacilities : showFireFacilities
        )).map((row) => {
          const [x, y] = project(row.longitude, row.latitude);
          const contact = row.phone_number ? ` · ${row.phone_number}` : "";
          return <g key={row.facility_id} className={`emergency-facility ${row.facility_kind}`}
            transform={`translate(${x} ${y}) scale(${markerScale})`}>
            <circle r="8">
              <title>{`${row.facility_name} · ${row.facility_type} · ${row.road_address}${contact}`}</title>
            </circle>
            <MapFacilityGlyph kind={row.facility_kind} />
          </g>;
        })}
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
          const sequence = mode === "manual"
            ? manualSequenceByTask.get(String(row.task_id))
            : sequenceByTask.get(String(row.task_id));
          const teamId = teamByTask.get(String(row.task_id));
          const excluded = Boolean(row.excluded);
          const priorityLevel = effectivePriorityLevel(row);
          const selected = selectedRisk?.link_id === row.link_id;
          const select = () => onSelectTask(row.link_id);
          const assigned = Boolean(sequence);
          const assignmentState = excluded ? "제외" : assigned ? `${sequence}번째 점검` : "점검 후보";
          return <g key={row.task_id} className={`${selected ? "task-point selected" : "task-point"}${!assigned && !excluded ? " candidate" : ""}`}
            transform={`translate(${x} ${y})`} role="button" tabIndex={0}
            aria-label={`${locationLabel(row)}, ${assignmentState}`}
            onClick={select} onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") select();
            }} style={{ "--task-color": TEAM_COLORS[teamId] || "#475569" }}>
            <g transform={`scale(${markerScale})`}>
              <circle r={row.mandatory ? 9 : 8} data-candidate={!assigned && !excluded || undefined}
                data-excluded={excluded || undefined} data-mandatory={row.mandatory || undefined}>
                <title>{excluded
                  ? `${locationLabel(row)} · ${row.road_name} · 현재 점검 제외 조건이 적용된 후보`
                  : assigned
                  ? `${locationLabel(row)} · ${row.road_name} · ${sequence}번째 점검`
                  : `${locationLabel(row)} · ${row.road_name} · 경로에 추가할 수 있는 점검 후보`}</title>
              </circle>
              <text className={assigned ? undefined : excluded ? "excluded-label" : "candidate-label"} y="3.5">{sequence || (excluded ? "제" : "+")}</text>
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
          const isSelected = row.team_id === selectedDepotId;
          return <g key={row.team_id} className={isSelected ? "team-point selected" : "team-point"}
            transform={`translate(${x} ${y})`}>
            <g transform={`scale(${markerScale})`}>
              <circle r={isSelected ? "14" : "12"} data-available={row.available === false ? "false" : "true"}
                style={{ fill: TEAM_COLORS[row.team_id] || "#475569" }}>
                <title>{`${row.team_name} · ${row.start_location_name || "출발 거점"} · ${row.available === false ? "비가용" : "가용"}`}</title>
              </circle>
              <HomeIcon className="team-home-icon" x="-8" y="-8" width="16" height="16" />
              <text className="team-start-name" x="16" y="4">{row.start_location_name || row.team_name || "출발 거점"}</text>
            </g>
          </g>;
        })}
      </g>
    </svg>
    <RouteDetail route={selectedRoute} routeRows={routeRows} taskRows={taskRows}
      teamRows={teamRows} onClose={onCloseRoute} />
    <a className="map-attribution" href="https://www.openstreetmap.org/copyright"
      target="_blank" rel="noopener">© OpenStreetMap contributors</a>
    <MapLegend showScenario={scenarioActive} showAccidentHotspots={showAccidentHotspots}
      showTrafficAccidents={showTrafficAccidents}
      showComplaintHotspots={showComplaintHotspots} showCrimeCaution={showCrimeCaution}
      showPoliceFacilities={showPoliceFacilities} showFireFacilities={showFireFacilities} />
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
      <div><span>주소 정밀도</span><b>{({
        official_parcel: "SGIS 공식 지번",
        official_road_address: "SGIS 공식 도로명주소",
        official_locality: "SGIS 공식 행정구역",
        parcel_or_building: "공개지도 지번·건물번호",
        road_or_locality: "공개지도 도로·리 단위",
      })[row.address_precision] || "주소 확인 필요"}</b></div>
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

function HistoricalSimilarity({ rows, selectedLinkId }) {
  return <DataComponent variant="plain" id="historical-similarity" queryId="historical_similarity"
    kind="custom" title="비슷했던 과거 상황"
    description="현재 노면기상과 비슷한 저장 이력에서 당시 도로 위험정보를 함께 찾았습니다."
    sourceRows={rows} displayRows={rows} className="historical-similarity-card">
    {rows.length ? <ol className="similarity-list">
      {rows.slice(0, 3).map((row) => {
        const linked = Array.isArray(row.event_link_ids) && row.event_link_ids.includes(String(selectedLinkId));
        return <li key={row.observed_at}>
          <div><strong>{dateTime(row.observed_at)}</strong><span>{number(row.similarity_score, 0)}% 비슷함</span></div>
          <p>당시 도로 위험정보 {number(row.event_count, 0)}건{linked ? " · 이 구간에서도 확인됨" : ""}</p>
          <small>비교 가능한 기상항목 {percentage(row.evidence_coverage_ratio)}</small>
        </li>;
      })}
    </ol> : <p className="similarity-empty">비교할 과거 수집 이력이 아직 없습니다.</p>}
    <p className="similarity-note">과거와 비슷하다는 뜻이며, 같은 사건이 다시 발생한다는 예측은 아닙니다.</p>
  </DataComponent>;
}

function CrimeContext({ rows, administrativeCity }) {
  const row = rows.find((item) => item.administrative_city === administrativeCity);
  if (!row) return null;
  const categories = patrolCrimeCategories(row);
  const displayedTotal = categories.reduce((sum, item) => sum + Number(item.occurrence_count || 0), 0);
  return <DataComponent variant="plain" id="crime-context" queryId="crime_statistics"
    kind="custom" title={`${row.administrative_city} 생활안전 참고`}
    description={`${row.analysis_year}년 경찰청 비식별 행정시 통계 중 현장 순찰 관련 항목입니다.`}
    sourceRows={rows} displayRows={[row]} className="crime-context-card"
    scopeFilters={[{ field: "administrative_city", label: "행정시", value: row.administrative_city }]}>
    <div className="crime-total"><span>화면 표시 항목 합계</span><strong>{number(displayedTotal, 0)}건</strong></div>
    <ol className="crime-category-list">
      {categories.map((item, index) => <li key={item.crime_category}>
        <b>{index + 1}</b><span>{item.crime_category}</span><strong>{number(item.occurrence_count, 0)}건</strong>
      </li>)}
    </ol>
    <p className="crime-context-note">사기·사이버 등 도로 순찰과 직접 관련이 낮은 항목은 숨겼습니다. 시 단위 참고 통계이며 이 도로 또는 특정 동의 범죄 건수는 아닙니다.</p>
  </DataComponent>;
}

const OPERATION_STEP = {
  select: 1,
  review: 2,
  manual: 3,
  "manual-review": 4,
  "ai-config": 3,
  "ai-result": 4,
};

function OperationSteps({ phase }) {
  const activeStep = OPERATION_STEP[phase] || 1;
  return <nav className="operation-steps" aria-label="순찰계획 진행 단계">
    {["거점 선택", "상황 검토", "경로 설정", "최종 확인"].map((label, index) => <span
      key={label} data-active={activeStep === index + 1 || undefined}
      data-complete={activeStep > index + 1 || undefined}>
      <b>{index + 1}</b>{label}
    </span>)}
  </nav>;
}

function DepotSelector({ teams, selectedDepotId, onSelect }) {
  return <DataComponent variant="plain" id="depot-selector" queryId="teams" kind="custom"
    title="어디에서 출발하나요?" description="실제 공개자료 기반 도로관리 거점을 먼저 선택합니다."
    sourceRows={teams} displayRows={teams} className="depot-selector-card">
    <div className="depot-list">
      {teams.map((team) => <button type="button" key={team.team_id}
        data-selected={team.team_id === selectedDepotId || undefined}
        onClick={() => onSelect(team.team_id)}>
        <span className="depot-home" style={{ "--team-color": TEAM_COLORS[team.team_id] }}><HomeIcon /></span>
        <span><strong>{team.start_location_name || team.team_name}</strong><small>{team.start_address || team.team_name}</small></span>
        <b>{team.available === false ? "출동 불가" : "선택"}</b>
      </button>)}
    </div>
  </DataComponent>;
}

function depotAdministrativeCity(depot) {
  const address = String(depot?.start_location_address || "");
  if (address.includes("서귀포시")) return "서귀포시";
  if (address.includes("제주시")) return "제주시";
  return "제주 전역";
}

function patrolCrimeCategories(row) {
  const excluded = /(사기|사이버|온라인|정보통신|지능|기타)/;
  return (Array.isArray(row?.top_categories) ? row.top_categories : [])
    .filter((item) => !excluded.test(String(item.crime_category || "")))
    .slice(0, 4);
}

function DepotEvidence({
  depot,
  tasks,
  accidents,
  history,
  weather,
  crimeRows,
  crimeOverlayRows,
  onSelectTask,
  onShowCrime,
}) {
  const [expandedEvidence, setExpandedEvidence] = useState(null);
  useEffect(() => setExpandedEvidence(null), [depot?.team_id, weather?.horizon_hours]);
  if (!depot) return <div className="operation-empty-state">
    <HomeIcon />
    <strong>왼쪽에서 출발 거점을 선택하세요.</strong>
    <span>선택한 거점 주변의 기상·도로 위험·사고다발·과거 유사상황을 한곳에서 확인할 수 있습니다.</span>
  </div>;
  const administrativeCity = depotAdministrativeCity(depot);
  const crimeRow = crimeRows.find((row) => row.administrative_city === administrativeCity);
  const crimeCategories = patrolCrimeCategories(crimeRow);
  const crimeAvailable = crimeOverlayRows.length > 0;
  const toggleEvidence = (key) => setExpandedEvidence((current) => current === key ? null : key);
  return <DataComponent variant="plain" id="depot-evidence" queryId="field_tasks"
    queryIds={["field_tasks", "risk_links", "weather_forecast", "accident_hotspots", "historical_similarity", "crime_statistics", "crime_caution_overlay"]}
    kind="custom" title={`${depot.start_location_name} 주변 상황`}
    description="출동 전 담당자가 확인할 근거를 장소 중심으로 정리했습니다."
    sourceRows={tasks} displayRows={tasks} className="depot-evidence-card">
    <div className="evidence-weather">
      <span>선택 시점 기상</span><strong>{weather ? `${weatherTemperature(weather)} · ${weather.sky_summary}` : "확인 불가"}</strong>
      <small>{weather ? `${weatherRainfallDetail(weather)} · ${weatherWindDetail(weather)}` : "예보 자료 없음"}</small>
    </div>
    <section className="evidence-section">
      <div className="evidence-section-head"><strong>우선 검토 도로</strong><span>{tasks.length}곳</span></div>
      <div className="evidence-road-list">
        {tasks.slice(0, 4).map((task) => <button type="button" key={task.task_id}
          onClick={() => onSelectTask(task.link_id)}>
          <span><strong>{locationLabel(task)}</strong><small>{priorityReasons(task)[0] || "현장 상태 확인 필요"}</small></span>
          <b data-priority={effectivePriorityLevel(task)}>{number(task.priority_score)}점</b>
        </button>)}
      </div>
    </section>
    <section className="evidence-section evidence-compact-grid">
      <div>
        <div className="evidence-section-head"><strong>주변 교통사고 다발지역</strong><span>한국도로교통공단</span></div>
        {accidents.slice(0, 2).map((row) => {
          const key = `accident:${row.hotspot_id}`;
          const expanded = expandedEvidence === key;
          return <div className="evidence-disclosure" key={row.hotspot_id} data-expanded={expanded || undefined}>
            <button type="button" aria-expanded={expanded} onClick={() => toggleEvidence(key)}>
              <span><b>{row.location_name}</b><small>교통사고 {number(row.accident_count, 0)}건 · 약 {number(row.distance_km)}km</small></span>
              <i>{expanded ? "접기" : "자세히"}</i>
            </button>
            {expanded && <dl>
              <div><dt>기준 연도</dt><dd>{row.analysis_year}년</dd></div>
              <div><dt>사상자</dt><dd>{number(row.casualty_count, 0)}명</dd></div>
              <div><dt>사망</dt><dd>{number(row.fatality_count, 0)}명</dd></div>
              <div><dt>중상</dt><dd>{number(row.serious_injury_count, 0)}명</dd></div>
            </dl>}
          </div>;
        })}
        {!accidents.length && <p><span>주변 공개자료 없음</span></p>}
      </div>
      <div>
        <div className="evidence-section-head"><strong>생활안전 참고</strong><span>도로 위험점수와 분리</span></div>
        <div className="evidence-disclosure" data-expanded={expandedEvidence === "crime" || undefined}>
          <button type="button" aria-expanded={expandedEvidence === "crime"} onClick={() => {
            const opening = expandedEvidence !== "crime";
            toggleEvidence("crime");
            if (opening && crimeAvailable) onShowCrime?.();
          }}>
            <span><b>{crimeAvailable ? `${administrativeCity} 범죄주의 밀도 지도` : "범죄주의 지도 확인 필요"}</b>
              <small>{crimeCategories.length ? crimeCategories.map((item) => item.crime_category).join(" · ") : "생활안전 공간자료"}</small></span>
            <i>{expandedEvidence === "crime" ? "접기" : "자세히"}</i>
          </button>
          {expandedEvidence === "crime" && <div className="crime-evidence-detail">
            <dl>
              <div><dt>선택 거점 위치</dt><dd>{depot.start_location_address || depot.start_location_name}</dd></div>
              <div><dt>지도 표시 범위</dt><dd>경찰청 범죄주의구간 밀도 계층 · 제주 전역</dd></div>
              <div><dt>통계 범위</dt><dd>{crimeRow ? `${crimeRow.analysis_year}년 ${crimeRow.administrative_city} 비식별 집계` : "행정시 집계 확인 필요"}</dd></div>
            </dl>
            {crimeCategories.length > 0 && <ul>{crimeCategories.map((item) => <li key={item.crime_category}>
              <span>{item.crime_category}</span><b>{number(item.occurrence_count, 0)}건</b>
            </li>)}</ul>}
            <p>사기·사이버 등 도로 순찰과 직접 관련이 낮은 항목은 숨겼습니다. 원자료가 동별 정확한 건수를 제공하지 않아 특정 동의 범죄 건수로 해석할 수 없습니다.</p>
          </div>}
        </div>
      </div>
    </section>
    <section className="evidence-section">
      <div className="evidence-section-head"><strong>비슷했던 날의 사건 장소</strong><span>과거 수집 이력</span></div>
      <div className="similar-place-list">
        {history.slice(0, 2).map((row) => {
          const key = `history:${row.observed_at}`;
          const expanded = expandedEvidence === key;
          const places = row.matched_places.slice(0, 3).map(locationLabel);
          return <div key={row.observed_at} data-expanded={expanded || undefined}>
            <button type="button" aria-expanded={expanded} onClick={() => toggleEvidence(key)}>
              <span><b>{number(row.similarity_score, 0)}% 유사</b>{dateTime(row.observed_at)}</span>
              <strong>{places.length ? places.join(" · ") : "제공 좌표 확인 필요"}</strong>
              <small>제주 C-ITS 도로 돌발정보 {number(row.event_count, 0)}건</small>
            </button>
            {expanded && <dl>
              <div><dt>위험정보</dt><dd>제주 C-ITS 도로 돌발정보</dd></div>
              <div><dt>발생 위치</dt><dd>{places.length ? places.join(" · ") : "제공 좌표 확인 필요"}</dd></div>
              <div><dt>제공 코드</dt><dd>{Array.isArray(row.event_codes) && row.event_codes.length ? row.event_codes.join(" · ") : "확인 불가"}</dd></div>
              <div><dt>당시 건수</dt><dd>{number(row.event_count, 0)}건</dd></div>
            </dl>}
          </div>;
        })}
      </div>
    </section>
  </DataComponent>;
}

function RouteChoice({ depot, onManual, onAi }) {
  if (!depot) return null;
  return <div className="route-choice-bar">
    <div><span>다음 단계</span><strong>담당자가 직접 경로를 정하거나 AI 추천안을 만들 수 있습니다.</strong></div>
    <button type="button" className="secondary-action" onClick={onManual}>지도에서 직접 선택</button>
    <button type="button" className="primary-action" onClick={onAi}>AI 자동선택</button>
  </div>;
}

function ManualRoutePanel({ depot, candidates, selectedTaskIds, onToggle, routes, onReview, onBack, reviewing, onConfirm }) {
  const summary = routeSummary(routes);
  const selected = new Set(selectedTaskIds.map(String));
  return <DataComponent variant="plain" id="manual-route-builder" queryId="field_tasks" kind="custom"
    title={reviewing ? "최종 순찰계획 검토" : "지도에서 순찰 순서 지정"}
    description={reviewing ? "소요시간과 누락된 후보를 확인한 뒤 계획을 확정합니다." : "지도 또는 목록을 누른 순서대로 순찰 코스가 만들어집니다."}
    sourceRows={candidates} displayRows={candidates} className="manual-route-panel">
    <div className="manual-summary">
      <span><b>{selectedTaskIds.length}</b>개 장소</span>
      <span><b>{number(summary.travelMinutes)}</b>분 이동</span>
      <span><b>{number(summary.serviceMinutes, 0)}</b>분 점검</span>
    </div>
    <ol className="manual-stop-list">
      {selectedTaskIds.map((taskId, index) => {
        const task = candidates.find((row) => String(row.task_id) === String(taskId));
        if (!task) return null;
        return <li key={taskId}><b>{index + 1}</b><span><strong>{locationLabel(task)}</strong><small>{priorityReasons(task)[0]}</small></span>
          {!reviewing && <button type="button" onClick={() => onToggle(task.task_id)}>삭제</button>}</li>;
      })}
    </ol>
    {!reviewing && <div className="manual-candidate-list">
      <span>추가 가능한 장소</span>
      {candidates.filter((task) => !selected.has(String(task.task_id))).map((task) => <button type="button"
        key={task.task_id} onClick={() => onToggle(task.task_id)}>
        <span><strong>{locationLabel(task)}</strong><small>{RISK_LABELS[task.risk_level] || "확인"} · {number(task.priority_score)}점</small></span><b>추가</b>
      </button>)}
    </div>}
    {reviewing && <div className="manual-omission">
      <strong>이번 계획에서 빠진 추천 장소 {Math.max(0, candidates.length - selectedTaskIds.length)}곳</strong>
      <span>빠진 장소는 다음 순찰계획 후보로 유지됩니다.</span>
    </div>}
    <div className="operation-actions">
      <button type="button" className="secondary-action" onClick={onBack}>{reviewing ? "경로 수정" : "이전"}</button>
      {reviewing
        ? <button type="button" className="primary-action" disabled={!routes.length} onClick={onConfirm}>계획 확정</button>
        : <button type="button" className="primary-action" disabled={!routes.length} onClick={onReview}>최종 검토</button>}
    </div>
  </DataComponent>;
}

function AiResultPanel({ depot, routes, tasks, selectedRouteKey, onSelectRoute, onBack, onConfirm }) {
  const summary = routeSummary(routes);
  return <DataComponent variant="plain" id="ai-route-result" queryId="plan_routes" kind="custom"
    title="AI 추천 순찰코스" description={`${depot?.start_location_name || "선택 거점"} 출발 기준으로 위험도와 이동시간을 함께 비교했습니다.`}
    sourceRows={routes} displayRows={routes} className="ai-result-panel">
    <div className="ai-result-summary">
      <span><b>{routes.length}</b>곳 점검</span><span><b>{number(summary.travelMinutes)}</b>분 이동</span>
      <span><b>{number(summary.travelMinutes + summary.serviceMinutes)}</b>분 예상</span>
    </div>
    <ol className="ai-stop-list">
      {[...routes].sort((left, right) => Number(left.sequence) - Number(right.sequence)).map((route, index) => {
        const task = tasks.find((row) => row.task_id === route.task_id);
        const selected = routeKey(route) === selectedRouteKey;
        return <li key={routeKey(route)} data-selected={selected || undefined}>
          <button type="button" onClick={() => onSelectRoute(route)}>
            <b>{index + 1}</b><span><strong>{locationLabel(task || route)}</strong><small>{number(route.travel_minutes)}분 이동 · {number(route.service_minutes, 0)}분 점검</small></span>
          </button>
          {selected && <p><strong>선정 이유</strong>{priorityReasons(task || route).slice(0, 2).join(" · ")}</p>}
        </li>;
      })}
    </ol>
    <div className="operation-actions">
      <button type="button" className="secondary-action" onClick={onBack}>조건 수정</button>
      <button type="button" className="primary-action" disabled={!routes.length} onClick={onConfirm}>계획 확정</button>
    </div>
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

function LegacyDashboardContent() {
  useDashboardTabs([{ id: "dashboard", label: "현장 운영 지도" }]);
  const { queries, snapshot, appTitle, setAppTitle } = useDataApp();
  const [horizonIndex, setHorizonIndex] = useState(0);
  const [selectedPlan, setSelectedPlan] = useState("safety_first");
  const [scenarioId, setScenarioId] = useState("none");
  const [selectedRiskId, setSelectedRiskId] = useState(/** @type {any} */ (null));
  const [selectedRouteKey, setSelectedRouteKey] = useState(/** @type {any} */ (null));
  const [workflowState, setWorkflowState] = useState(/** @type {any} */ (null));
  const [workflowPlan, setWorkflowPlan] = useState(/** @type {any} */ (null));
  const [inspectorTab, setInspectorTab] = useState("priorities");
  const [mapGuideOpen, setMapGuideOpen] = useState(false);
  const [currentTime, setCurrentTime] = useState(() => new Date());
  const [mapLayers, setMapLayers] = useState({
    accidentHotspots: true,
    complaintHotspots: true,
    crimeCaution: false,
    policeFacilities: false,
    fireFacilities: false,
    trafficAccidents: false,
  });
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
  }, [selectedPlan, scenarioId]);

  useEffect(() => {
    setSelectedRiskId(null);
    setSelectedRouteKey(null);
  }, [horizon]);

  useEffect(() => {
    const timer = window.setInterval(() => setCurrentTime(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const rows = (queryId) => queries[queryId]?.rows ?? [];
  const metadata = /** @type {any} */ (rows("map_metadata")[0] ?? {});
  const weatherRows = rows("weather_forecast");
  const currentWeather = weatherRows.find((row) => Number(row.horizon_hours) === 0) ?? weatherRows[0];
  const forecastValidationRows = rows("forecast_validation");
  const allRiskRows = rows("risk_links");
  const riskRows = allRiskRows.filter((row) => Number(row.horizon_hours) === horizon && row.has_geometry);
  const riskByLink = new Map(riskRows.map((row) => [String(row.link_id), row]));
  const selectedRisk = riskRows.find((row) => row.link_id === selectedRiskId)
    ?? [...riskRows].sort((left, right) => Number(right.priority_score) - Number(left.priority_score))[0]
    ?? null;
  const basePlanMetrics = rows("plan_metrics");
  const planMetrics = workflowPlan?.planMetrics?.length ? workflowPlan.planMetrics : basePlanMetrics;
  const selectedMetrics = planMetrics.find((row) => row.alternative_id === selectedPlan) ?? {};
  const workflowTasks = new Map((workflowState?.tasks ?? []).map((task) => [task.taskId, task]));
  const workflowResources = new Map((workflowState?.resources ?? []).map((resource) => [resource.teamId, resource]));
  const effectiveTaskRows = rows("field_tasks").map((row) => {
    const horizonRisk = riskByLink.get(String(row.link_id));
    const synchronizedRow = horizonRisk ? {
      ...row,
      priority_score: horizonRisk.priority_score,
      risk_level: horizonRisk.risk_level,
      location_label: horizonRisk.location_label || row.location_label,
    } : row;
    const decision = workflowTasks.get(String(row.task_id));
    return decision ? {
      ...synchronizedRow,
      excluded: decision.excluded,
      fixed_team_id: decision.fixed ? decision.assignedTeamId : null,
      assigned_team_id: decision.assignedTeamId,
      manual_priority_level: decision.manualPriorityLevel,
      manual_priority_reason: decision.priorityReason,
      effective_priority_level: decision.manualPriorityLevel || decision.suggestedPriorityLevel,
    } : synchronizedRow;
  });
  const effectiveTeamRows = rows("teams").map((row) => ({
    ...row,
    available: workflowResources.get(String(row.team_id))?.available ?? true,
  }));
  const selectedTask = effectiveTaskRows.find((row) => row.link_id === selectedRisk?.link_id) ?? null;
  const selectedAuthority = rows("governance_authorities")
    .find((row) => row.link_id === selectedRisk?.link_id) ?? null;
  const allRouteRows = workflowPlan?.routes?.length ? workflowPlan.routes : rows("plan_routes");
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
  const emergencyFacilities = rows("emergency_facilities");
  const policeFacilityCount = emergencyFacilities.filter((row) => row.facility_kind === "police").length;
  const fireFacilityCount = emergencyFacilities.filter((row) => row.facility_kind === "fire").length;
  const mapQueryIds = ["risk_links", "road_background", "accident_hotspots", "complaint_hotspots", "crime_caution_overlay", "emergency_facilities", "traffic_accident_overlay", "field_tasks", "governance_authorities", "teams", "plan_routes", "travel_route_options", "travel_route_links", "replan_routes", "scenario_impacts"];
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
      <div className="toolbar-primary">
        <div className="toolbar-title">
          <span className="roadops-signal" aria-hidden="true"><i /><i /><i /></span>
          <div><span className="eyebrow">ROADOPS / JEJU</span><strong>도로 현장 운영 상황판</strong></div>
        </div>
        <div className="toolbar-live-state">
          <span className="live-pill"><i />자동 갱신</span>
          <small>{Number(metadata.automatic_refresh_interval_minutes) > 0
            ? `${Number(metadata.automatic_refresh_interval_minutes)}분 주기`
            : "주기 미설정"}</small>
        </div>
        <div className="data-status-group">
          <span>데이터 기준</span>
          <strong>{dateTime(metadata.latest_risk_target_at)}</strong>
        </div>
        <div className="command-fact command-fact-weather">
          <span>현재 날씨</span>
          <strong>{currentWeather ? `${weatherTemperature(currentWeather)} · ${currentWeather.sky_summary} · ${weatherRainfallDetail(currentWeather)}` : "확인 불가"}</strong>
        </div>
        <div className="command-fact command-fact-time">
          <span>현재 시각</span>
          <strong>{currentTime.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</strong>
        </div>
        <div className="theme-control">
          <span>화면</span>
          <div className="theme-buttons" role="group" aria-label="화면 테마 선택">
            <button type="button" aria-pressed={colorMode === "dark"}
              onClick={() => setColorMode("dark")}>다크</button>
            <button type="button" aria-pressed={colorMode === "light"}
              onClick={() => setColorMode("light")}>화이트</button>
          </div>
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
      </div>
    </section>

    <section className="roadops-weather" aria-label="제주 단기 기상">
      <WeatherForecastStrip rows={weatherRows} validationRows={forecastValidationRows} horizon={horizon}
        onSelect={(hours) => setHorizonIndex(Math.max(0, HORIZONS.indexOf(hours)))} />
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
          <div className="map-layer-controls" role="group" aria-label="지도 계층 선택">
            <span className="map-layer-heading"><LayerIcon type="layers" />표시</span>
            <label title="한국도로교통공단 선정 교통사고 다발지역"><input type="checkbox" checked={mapLayers.accidentHotspots}
              onChange={(event) => setMapLayers((current) => ({ ...current, accidentHotspots: event.target.checked }))} />
              <LayerIcon type="accident" />교통사고 다발
              <LayerStatus available={rows("accident_hotspots").length > 0} value={rows("accident_hotspots").length}
                unavailableLabel="교통사고 다발지역 자료를 연결하지 못했습니다." /></label>
            <label title={rows("complaint_hotspots").length ? "비식별 도로민원 다발지역을 표시합니다." : "승인된 제주 도로민원 내보내기 자료가 필요합니다."}>
              <input type="checkbox" checked={mapLayers.complaintHotspots && rows("complaint_hotspots").length > 0}
                disabled={!rows("complaint_hotspots").length}
                onChange={(event) => setMapLayers((current) => ({ ...current, complaintHotspots: event.target.checked }))} />
              <LayerIcon type="complaint" />민원
              <LayerStatus available={rows("complaint_hotspots").length > 0} value={rows("complaint_hotspots").length}
                unavailableLabel="민원 자료가 연결되지 않았습니다." />
            </label>
            <label title={rows("crime_caution_overlay").length ? "경찰청 연간 범죄 밀도분석을 표시합니다." : "생활안전지도 사용승인과 인증키가 필요합니다."}>
              <input type="checkbox" checked={mapLayers.crimeCaution}
                disabled={!rows("crime_caution_overlay").length}
                onChange={(event) => setMapLayers((current) => ({ ...current, crimeCaution: event.target.checked }))} />
              <LayerIcon type="crime" />범죄주의
              <LayerStatus available={rows("crime_caution_overlay").length > 0}
                unavailableLabel="범죄주의구간이 연결되지 않았습니다." />
            </label>
            <label title="경찰 인계 판단을 돕기 위해 제주 경찰관서 위치를 표시합니다.">
              <input type="checkbox" checked={mapLayers.policeFacilities}
                disabled={!policeFacilityCount}
                onChange={(event) => setMapLayers((current) => ({ ...current, policeFacilities: event.target.checked }))} />
              <LayerIcon type="police" />경찰
              <LayerStatus available={policeFacilityCount > 0} value={policeFacilityCount}
                unavailableLabel="경찰관서 자료가 연결되지 않았습니다." />
            </label>
            <label title="소방 인계 판단을 돕기 위해 제주 소방서·119안전센터 위치를 표시합니다.">
              <input type="checkbox" checked={mapLayers.fireFacilities}
                disabled={!fireFacilityCount}
                onChange={(event) => setMapLayers((current) => ({ ...current, fireFacilities: event.target.checked }))} />
              <LayerIcon type="fire" />소방
              <LayerStatus available={fireFacilityCount > 0} value={fireFacilityCount}
                unavailableLabel="소방시설 자료가 연결되지 않았습니다." />
            </label>
            <label title="TAAS 사고다발지역과 별도로 생활안전지도 연간 사고 계층을 비교 표시합니다.">
              <input type="checkbox" checked={mapLayers.trafficAccidents}
                disabled={!rows("traffic_accident_overlay").length}
                onChange={(event) => setMapLayers((current) => ({ ...current, trafficAccidents: event.target.checked }))} />
              <LayerIcon type="layers" />사고비교
              <LayerStatus available={rows("traffic_accident_overlay").length > 0}
                unavailableLabel="사고 비교 계층이 연결되지 않았습니다." />
            </label>
          </div>
          <button type="button" className="map-guide-toggle" aria-expanded={mapGuideOpen}
            onClick={() => setMapGuideOpen((open) => !open)}>
            <span>지도 읽는 방법</span><small>배경지도 + 분석도로 11개 · {mapGuideOpen ? "접기" : "펼치기"}</small>
          </button>
          {mapGuideOpen && <div className="map-reading-guide" aria-label="지도 표시 설명">
            <p>배경에는 주변 도로·지명이 표시되지만, 점검 표시는 RoadOps가 분석한 주요 간선도로 11개 범위입니다. SGIS 인증정보가 있으면 공식 도로명·지번을 우선하고, 없으면 공개지도의 인근 주소를 표시합니다.</p>
            <span><i data-guide="risk" /><b>우선순위 표식</b> 먼저·주의·일반을 도로선과 분리해 표시</span>
            <span><i data-guide="route" /><b>팀 색 점선</b> 순찰팀이 실제로 이동할 경로로, 누르면 소요시간과 전체 코스를 표시</span>
            <span><i data-guide="point" /><b>팀 색 숫자 원</b> 점검 순서 · 집 아이콘은 공개자료 기반 도로관리 거점</span>
            <span><i data-guide="unassigned" /><b>‘미’ 원</b> 현재 근무시간·경로 제약 안에서 배정되지 않은 후보</span>
            <span><i data-guide="excluded" /><b>‘제’ 원</b> 담당자가 설정한 점검 제외 조건이 적용된 후보</span>
            <span><i data-guide="accident" /><b>빗금 영역</b> 한국도로교통공단이 선정한 2025년 사고다발지역</span>
            <span><i data-guide="complaint" /><b>보라색 원</b> 신고자 정보를 제거하고 3건 이상만 묶은 약 500m 도로민원 집계</span>
            <span><i data-guide="crime" /><b>반투명 밀도</b> 생활안전지도·경찰청의 2025년 범죄주의구간(위험점수와 분리)</span>
            <span><i data-guide="facility" /><b>방패·불꽃</b> 경찰·소방 인계를 위한 공식 시설 위치(위험점수와 분리)</span>
            <span><i data-guide="traffic-overlay" /><b>붉은 반투명 계층</b> 생활안전지도 사고다발구역 교차검증 계층</span>
          </div>}
          <RoadMap backgroundRows={rows("road_background")} riskRows={riskRows}
            taskRows={effectiveTaskRows} teamRows={effectiveTeamRows} routeRows={routeRows}
            replanRows={replanRows} impactRows={impactRows} selectedRisk={selectedRisk}
            accidentRows={rows("accident_hotspots")} showAccidentHotspots={mapLayers.accidentHotspots}
            complaintRows={rows("complaint_hotspots")}
            showComplaintHotspots={mapLayers.complaintHotspots && rows("complaint_hotspots").length > 0}
            crimeCautionRows={rows("crime_caution_overlay")}
            emergencyFacilityRows={emergencyFacilities}
            trafficAccidentOverlayRows={rows("traffic_accident_overlay")}
            showCrimeCaution={mapLayers.crimeCaution && rows("crime_caution_overlay").length > 0}
            showPoliceFacilities={mapLayers.policeFacilities}
            showFireFacilities={mapLayers.fireFacilities}
            showTrafficAccidents={mapLayers.trafficAccidents && rows("traffic_accident_overlay").length > 0}
            selectedRoute={selectedRoute} onSelectRisk={selectRisk} onSelectTask={selectTask}
            onSelectRoute={selectRoute} onCloseRoute={() => setSelectedRouteKey(null)}
            scenarioId={scenarioId} horizon={horizon} />
        </DataComponent>
        <ReplanSummary rows={rows("scenario_summary")} scenarioId={scenarioId} />
      </section>

      <aside className="roadops-inspector">
        <div className="inspector-status-head">
          <div><span>ACTIVE OPERATIONS</span><strong>현장 대응 대기열</strong></div>
          <span className="inspector-alert" data-active={highRiskCount > 0 || undefined}>
            <i />{highRiskCount > 0 ? `우선 확인 ${highRiskCount}` : "긴급 항목 없음"}
          </span>
        </div>
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
            <HistoricalSimilarity rows={rows("historical_similarity")} selectedLinkId={selectedRisk?.link_id} />
            <CrimeContext rows={rows("crime_statistics")}
              administrativeCity={selectedTask?.administrative_city || selectedAuthority?.administrative_city} />
            <AuthorityDetail task={selectedTask} authority={selectedAuthority}
              taskRows={rows("field_tasks")} authorityRows={rows("governance_authorities")} />
          </>}
          {inspectorTab === "plan" && <>
            <PlanComparison rows={planMetrics} selectedPlan={selectedPlan} onSelect={setSelectedPlan} />
            <WorkflowPanel teams={rows("teams")} tasks={rows("field_tasks")}
              governanceRows={rows("governance_authorities")}
              routes={rows("plan_routes")} planMetrics={basePlanMetrics} metadata={metadata}
              routeOptions={rows("travel_route_options")} routeLinks={rows("travel_route_links")}
              selectedPlan={selectedPlan} scenarioId={scenarioId} onStateChange={setWorkflowState}
              onResultChange={setWorkflowPlan} />
          </>}
        </div>
      </aside>
    </div>

    <footer className="roadops-disclaimer">
      운영 우선순위 시나리오이며 사고확률이 아닙니다. 모든 배분·재계획 결과는 현장 지시 전 책임자의 확인과 확정이 필요합니다.
    </footer>
  </article>;
}

export function DashboardContent() {
  useDashboardTabs([{ id: "dashboard", label: "현장 운영 지도" }]);
  const { queries, snapshot, appTitle, setAppTitle } = useDataApp();
  const rows = (queryId) => queries[queryId]?.rows ?? [];
  const [initialOperation] = useState(readOperationSession);
  const [phase, setPhase] = useState(initialOperation.phase);
  const [selectedDepotId, setSelectedDepotId] = useState(initialOperation.selectedDepotId);
  const [manualTaskIds, setManualTaskIds] = useState(initialOperation.manualTaskIds);
  const [horizonIndex, setHorizonIndex] = useState(initialOperation.horizonIndex);
  const [selectedPlan, setSelectedPlan] = useState(initialOperation.selectedPlan);
  const [scenarioId, setScenarioId] = useState(initialOperation.scenarioId);
  const [selectedRiskId, setSelectedRiskId] = useState(initialOperation.selectedRiskId);
  const [selectedRouteKey, setSelectedRouteKey] = useState(initialOperation.selectedRouteKey);
  const [workflowState, setWorkflowState] = useState(null);
  const [workflowPlan, setWorkflowPlan] = useState(null);
  const [mapExpanded, setMapExpanded] = useState(initialOperation.mapExpanded);
  const [surfaceView, setSurfaceView] = useState(initialOperation.surfaceView);
  const [confirmedMessage, setConfirmedMessage] = useState("");
  const [currentTime, setCurrentTime] = useState(() => new Date());
  const [mapLayers, setMapLayers] = useState(initialOperation.mapLayers);
  const [colorMode, setColorMode] = useState(() => {
    if (typeof localStorage === "undefined") return "light";
    return localStorage.getItem("roadops-color-mode") === "dark" ? "dark" : "light";
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
    const timer = window.setInterval(() => setCurrentTime(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (typeof sessionStorage === "undefined") return;
    sessionStorage.setItem(OPERATION_SESSION_KEY, JSON.stringify({
      phase,
      selectedDepotId,
      manualTaskIds,
      horizonIndex,
      selectedPlan,
      scenarioId,
      selectedRiskId,
      selectedRouteKey,
      mapExpanded,
      surfaceView,
      mapLayers,
    }));
  }, [phase, selectedDepotId, manualTaskIds, horizonIndex, selectedPlan, scenarioId,
    selectedRiskId, selectedRouteKey, mapExpanded, surfaceView, mapLayers]);

  useEffect(() => {
    setSelectedRiskId(null);
    setSelectedRouteKey(null);
  }, [horizon, selectedPlan, scenarioId]);

  const metadata = rows("map_metadata")[0] ?? {};
  const weatherRows = rows("weather_forecast");
  const radarRows = Array.isArray(radarSnapshot?.records) ? radarSnapshot.records : [];
  const selectedWeather = weatherRows.find((row) => Number(row.horizon_hours) === horizon) ?? weatherRows[0];
  const allRiskRows = rows("risk_links");
  const riskRows = allRiskRows.filter((row) => Number(row.horizon_hours) === horizon && row.has_geometry);
  const riskByLink = new Map(riskRows.map((row) => [String(row.link_id), row]));
  const selectedRisk = riskRows.find((row) => String(row.link_id) === String(selectedRiskId)) ?? null;
  const basePlanMetrics = rows("plan_metrics");
  const planMetrics = workflowPlan?.planMetrics?.length ? workflowPlan.planMetrics : basePlanMetrics;
  const workflowTasks = new Map((workflowState?.tasks ?? []).map((task) => [String(task.taskId), task]));
  const workflowResources = new Map((workflowState?.resources ?? []).map((resource) => [String(resource.teamId), resource]));
  const effectiveTaskRows = rows("field_tasks").map((row) => {
    const risk = riskByLink.get(String(row.link_id));
    const synchronized = risk ? {
      ...row,
      priority_score: risk.priority_score,
      risk_level: risk.risk_level,
      location_label: risk.location_label || row.location_label,
    } : row;
    const decision = workflowTasks.get(String(row.task_id));
    return decision ? {
      ...synchronized,
      excluded: decision.excluded,
      assigned_team_id: decision.assignedTeamId,
      manual_priority_level: decision.manualPriorityLevel,
      manual_priority_reason: decision.priorityReason,
      effective_priority_level: decision.manualPriorityLevel || decision.suggestedPriorityLevel,
    } : synchronized;
  });
  const effectiveTeamRows = rows("teams").map((row) => ({
    ...row,
    available: workflowResources.get(String(row.team_id))?.available ?? true,
  }));
  const selectedDepot = effectiveTeamRows.find((row) => row.team_id === selectedDepotId) ?? null;
  const allRouteRows = workflowPlan?.routes?.length ? workflowPlan.routes : rows("plan_routes");
  const candidates = tasksForDepot({
    tasks: effectiveTaskRows,
    routes: allRouteRows,
    depotId: selectedDepotId,
    depot: selectedDepot,
    planId: selectedPlan,
    limit: 6,
  });
  const manualRoutes = buildManualRoutes({
    selectedTaskIds: manualTaskIds,
    tasks: effectiveTaskRows,
    routes: allRouteRows,
    depotId: selectedDepotId,
    planId: selectedPlan,
    routeOptions: rows("travel_route_options"),
    routeLinks: rows("travel_route_links"),
  });
  const plannedRoutes = effectiveTaskRows.flatMap((task) => {
    const decision = workflowTasks.get(String(task.task_id));
    if (decision?.excluded) return [];
    const assignedTeamId = decision?.assignedTeamId
      ?? allRouteRows.find((row) => row.alternative_id === selectedPlan && row.task_id === task.task_id)?.team_id;
    const route = allRouteRows.find((row) => row.alternative_id === selectedPlan
      && row.task_id === task.task_id && row.team_id === assignedTeamId)
      ?? allRouteRows.find((row) => row.task_id === task.task_id && row.team_id === assignedTeamId);
    return route ? [{ ...route, alternative_id: selectedPlan }] : [];
  });
  const aiRoutes = plannedRoutes.filter((row) => row.team_id === selectedDepotId)
    .sort((left, right) => Number(left.sequence) - Number(right.sequence));
  const visibleRoutes = phase === "manual" || phase === "manual-review"
    ? manualRoutes
    : phase === "ai-result" ? aiRoutes : [];
  const visibleTasks = selectedDepot ? candidates : [];
  const selectedRoute = visibleRoutes.find((row) => routeKey(row) === selectedRouteKey) ?? null;
  const nearbyAccidents = nearbyRows(selectedDepot, rows("accident_hotspots"), 3);
  const similarHistory = historicalPlaces(rows("historical_similarity"), effectiveTaskRows, 3);
  const replanRows = phase === "ai-result"
    ? rows("replan_routes").filter((row) => row.scenario_id === scenarioId && row.team_id === selectedDepotId)
    : [];
  const impactRows = phase === "ai-result" ? rows("scenario_impacts").filter((row) => row.scenario_id === scenarioId) : [];
  const mapQueryIds = ["risk_links", "road_background", "accident_hotspots", "complaint_hotspots", "crime_caution_overlay", "field_tasks", "teams", "plan_routes", "travel_route_options", "travel_route_links", "replan_routes", "scenario_impacts"];
  const viewQueryIds = [...mapQueryIds, "weather_forecast"];
  const sourceRowsByQuery = Object.fromEntries(viewQueryIds.map((queryId) => [queryId, rows(queryId)]));

  const chooseDepot = (teamId) => {
    setSelectedDepotId(teamId);
    setManualTaskIds([]);
    setSelectedRiskId(null);
    setSelectedRouteKey(null);
    setWorkflowPlan(null);
    setWorkflowState(null);
    setConfirmedMessage("");
    setPhase("review");
  };

  const toggleManualTask = (taskId) => {
    setManualTaskIds((current) => current.includes(taskId)
      ? current.filter((id) => id !== taskId)
      : [...current, taskId]);
    const task = effectiveTaskRows.find((row) => row.task_id === taskId);
    if (task) setSelectedRiskId(task.link_id);
  };

  const selectTask = (linkId) => {
    const task = visibleTasks.find((row) => String(row.link_id) === String(linkId));
    if (phase === "manual" && task) toggleManualTask(task.task_id);
    setSelectedRiskId(linkId);
  };

  const selectRoute = (row) => {
    setSelectedRouteKey(routeKey(row));
    setSelectedRiskId(row.link_id);
  };

  const resetOperation = (message = "") => {
    setConfirmedMessage(message);
    setPhase("select");
    setSelectedDepotId(null);
    setManualTaskIds([]);
    setSelectedRiskId(null);
    setSelectedRouteKey(null);
    setWorkflowState(null);
    setWorkflowPlan(null);
    setMapExpanded(false);
  };

  const mapPanel = <DataComponent variant="plain" id="roadops-operation-map"
    queryId={surfaceView === "weather" ? "weather_forecast" : "risk_links"}
    queryIds={viewQueryIds} kind="custom"
    title={surfaceView === "weather" ? "제주 기상 상황"
      : phase === "manual" || phase === "manual-review" ? "순찰 지점을 순서대로 선택하세요"
        : phase === "ai-result" ? "AI 추천 경로" : "선택 거점과 주변 점검 후보"}
    description={surfaceView === "weather" ? "현재 강수 관측과 1·3·6시간 후 예상 강수 분포를 구분해 확인합니다."
      : phase === "select" ? "경로는 거점을 선택한 뒤에만 만들어집니다."
        : "배경지도 위에 선택 거점, 점검 후보와 확정된 경로만 표시합니다."}
    sourceRows={surfaceView === "weather" ? [...weatherRows, ...radarRows] : allRiskRows}
    displayRows={surfaceView === "weather" ? (selectedWeather ? [selectedWeather] : []) : riskRows}
    sourceRowsByQuery={sourceRowsByQuery}
    scopeFilters={[{ field: "horizon_hours", label: "예측 시점", value: String(horizon) }]}
    className={`operation-map-card${mapExpanded ? " expanded" : ""}${surfaceView === "weather" ? " weather-active" : ""}`}>
    <div className="operation-map-toolbar">
      <div className="operation-view-switch" role="group" aria-label="상황판 보기 선택">
        <button type="button" aria-pressed={surfaceView === "map"} onClick={() => setSurfaceView("map")}>지도뷰</button>
        <button type="button" aria-pressed={surfaceView === "weather"} onClick={() => setSurfaceView("weather")}>날씨뷰</button>
      </div>
      <div className="operation-map-tools">
        {surfaceView === "map" && <div className="operation-layer-buttons" role="group" aria-label="지도 참고 계층">
          <label title="한국도로교통공단 교통사고 다발지역"><input type="checkbox" checked={mapLayers.accidentHotspots}
            onChange={(event) => setMapLayers((current) => ({ ...current, accidentHotspots: event.target.checked }))} />
            <LayerIcon type="accident" />교통사고 다발</label>
          <label title="경찰청 범죄주의 밀도 계층"><input type="checkbox" checked={mapLayers.crimeCaution}
            onChange={(event) => setMapLayers((current) => ({ ...current, crimeCaution: event.target.checked }))} />
            <LayerIcon type="crime" />범죄주의</label>
          {rows("complaint_hotspots").length > 0 && <label title="비식별 도로민원 다발지역"><input type="checkbox" checked={mapLayers.complaintHotspots}
            onChange={(event) => setMapLayers((current) => ({ ...current, complaintHotspots: event.target.checked }))} />
            <LayerIcon type="complaint" />민원</label>}
        </div>}
        <button type="button" className="map-size-button" onClick={() => setMapExpanded((value) => !value)}>
          {mapExpanded ? "기본 크기" : `${surfaceView === "weather" ? "날씨뷰" : "지도"} 크게`}
        </button>
      </div>
    </div>
    {surfaceView === "map" ? <RoadMap backgroundRows={rows("road_background")} riskRows={riskRows}
      taskRows={visibleTasks} teamRows={effectiveTeamRows} routeRows={visibleRoutes}
      replanRows={replanRows} impactRows={impactRows} selectedRisk={selectedRisk}
      accidentRows={rows("accident_hotspots")} showAccidentHotspots={mapLayers.accidentHotspots}
      complaintRows={rows("complaint_hotspots")} showComplaintHotspots={mapLayers.complaintHotspots}
      crimeCautionRows={rows("crime_caution_overlay")} showCrimeCaution={mapLayers.crimeCaution}
      emergencyFacilityRows={[]} trafficAccidentOverlayRows={[]}
      showPoliceFacilities={false} showFireFacilities={false} showTrafficAccidents={false}
      selectedRoute={selectedRoute} onSelectRisk={(row) => setSelectedRiskId(row.link_id)}
      onSelectTask={selectTask} onSelectRoute={selectRoute} onCloseRoute={() => setSelectedRouteKey(null)}
      scenarioId={phase === "ai-result" ? scenarioId : "none"} horizon={horizon}
      mode={phase === "manual" || phase === "manual-review" ? "manual" : phase}
      selectedDepotId={selectedDepotId} manualTaskIds={manualTaskIds} />
      : <WeatherMapView backgroundRows={rows("road_background")} weatherRows={weatherRows} radarRows={radarRows}
        selectedWeather={selectedWeather} horizon={horizon}
        onSelectHorizon={(hours) => setHorizonIndex(Math.max(0, HORIZONS.indexOf(hours)))} />}
  </DataComponent>;

  return <article className="roadops-page roadops-operation-page" data-dashboard-layout="viewport" data-color-mode={colorMode}>
    <section className="roadops-toolbar operation-toolbar" aria-label="운영 상황 제어">
      <div className="toolbar-primary">
        <div className="toolbar-title"><div><span className="eyebrow">ROADOPS / JEJU</span><strong>도로 현장 운영 상황판</strong></div></div>
        <div className="toolbar-live-state"><span className="live-pill"><i />자동 갱신</span><small>{Number(metadata.automatic_refresh_interval_minutes) || 10}분 주기</small></div>
        <div className="data-status-group"><span>최근 갱신</span><strong>{dateTime(metadata.generated_at || snapshot.generatedAt)}</strong></div>
        <div className="command-fact command-fact-weather"><span>{horizon === 0 ? "현재 날씨" : `${horizon}시간 후 날씨`}</span><strong>{selectedWeather ? `${weatherTemperature(selectedWeather)} · ${selectedWeather.sky_summary} · ${weatherRainfallDetail(selectedWeather)}` : "확인 불가"}</strong></div>
        <div className="command-fact command-fact-time"><span>현재 시각</span><strong>{currentTime.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</strong></div>
        <div className="theme-control"><span>화면</span><div className="theme-buttons" role="group" aria-label="화면 테마 선택">
          <button type="button" aria-pressed={colorMode === "dark"} onClick={() => setColorMode("dark")}>다크</button>
          <button type="button" aria-pressed={colorMode === "light"} onClick={() => setColorMode("light")}>화이트</button>
        </div></div>
      </div>
      <div className="operation-horizon-row">
        <span>예측 시점</span>
        <div className="horizon-buttons" role="group" aria-label="예측 시간 선택">
          {HORIZONS.map((hours, index) => <button type="button" key={hours} aria-pressed={horizonIndex === index}
            onClick={() => setHorizonIndex(index)}>{hours === 0 ? "현재" : `${hours}시간 후`}</button>)}
        </div>
        {selectedDepot && <div className="selected-depot-chip"><HomeIcon /><span>{selectedDepot.start_location_name}</span></div>}
      </div>
    </section>

    <OperationSteps phase={phase} />
    {confirmedMessage && <div className="operation-confirmed" role="status">✓ {confirmedMessage}</div>}

    {(phase === "select" || phase === "review") && <section className="operation-stage operation-stage-initial">
      <DepotSelector teams={effectiveTeamRows} selectedDepotId={selectedDepotId} onSelect={chooseDepot} />
      <section className="operation-map-slot">{mapPanel}</section>
      <section className="operation-evidence-slot">
        <DepotEvidence depot={selectedDepot} tasks={candidates} accidents={nearbyAccidents}
          history={similarHistory} weather={selectedWeather}
          crimeRows={rows("crime_statistics")}
          crimeOverlayRows={rows("crime_caution_overlay")}
          onShowCrime={() => setMapLayers((current) => ({ ...current, crimeCaution: true }))}
          onSelectTask={(linkId) => setSelectedRiskId(linkId)} />
      </section>
      <RouteChoice depot={selectedDepot}
        onManual={() => { setPhase("manual"); setSurfaceView("map"); setMapExpanded(true); setManualTaskIds([]); }}
        onAi={() => { setPhase("ai-config"); setMapExpanded(false); }} />
    </section>}

    {(phase === "manual" || phase === "manual-review") && <section className="operation-stage operation-stage-plan">
      <section className="operation-map-slot">{mapPanel}</section>
      <section className="operation-plan-slot">
        <ManualRoutePanel depot={selectedDepot} candidates={candidates} selectedTaskIds={manualTaskIds}
          onToggle={toggleManualTask} routes={manualRoutes} reviewing={phase === "manual-review"}
          onBack={() => setPhase(phase === "manual-review" ? "manual" : "review")}
          onReview={() => setPhase("manual-review")}
          onConfirm={() => resetOperation(`${selectedDepot?.start_location_name} 수동 순찰계획을 확정했습니다.`)} />
      </section>
    </section>}

    {phase === "ai-config" && <section className="operation-stage operation-stage-ai-config">
      <header className="ai-config-head">
        <div><span>AI 자동선택</span><strong>{selectedDepot?.start_location_name} 출동 조건을 확인하세요.</strong>
          <p>출동 인원·가용 시간·점검 제외 조건을 바꾸면 가능한 계획을 즉시 다시 비교합니다.</p></div>
        <button type="button" className="secondary-action" onClick={() => setPhase("review")}>이전</button>
      </header>
      <PlanComparison rows={planMetrics} selectedPlan={selectedPlan} onSelect={setSelectedPlan} />
      <WorkflowPanel teams={effectiveTeamRows.filter((team) => team.team_id === selectedDepotId)}
        tasks={candidates} governanceRows={rows("governance_authorities")}
        routes={rows("plan_routes").filter((route) => route.team_id === selectedDepotId)}
        planMetrics={basePlanMetrics} metadata={metadata}
        routeOptions={rows("travel_route_options")} routeLinks={rows("travel_route_links")}
        optimizeOnMount
        provenanceRows={{
          teams: rows("teams"),
          field_tasks: rows("field_tasks"),
          governance_authorities: rows("governance_authorities"),
          plan_routes: rows("plan_routes"),
          plan_metrics: rows("plan_metrics"),
          travel_route_options: rows("travel_route_options"),
          travel_route_links: rows("travel_route_links"),
          map_metadata: rows("map_metadata"),
        }}
        selectedPlan={selectedPlan} scenarioId={scenarioId} onStateChange={setWorkflowState}
        onResultChange={setWorkflowPlan} />
      <div className="ai-generate-bar"><div><span>조건 검토가 끝났나요?</span><strong>AI가 위험도와 이동시간을 비교해 추천 코스를 만듭니다.</strong></div>
        <button type="button" className="primary-action"
          disabled={workflowPlan?.optimizationStatus !== "ready" || !(workflowPlan?.routes?.length)}
          onClick={() => { setPhase("ai-result"); setSurfaceView("map"); setMapExpanded(true); }}>추천 경로 만들기</button></div>
    </section>}

    {phase === "ai-result" && <section className="operation-stage operation-stage-plan">
      <section className="operation-map-slot">{mapPanel}</section>
      <section className="operation-plan-slot">
        <AiResultPanel depot={selectedDepot} routes={aiRoutes} tasks={effectiveTaskRows}
          selectedRouteKey={selectedRouteKey} onSelectRoute={selectRoute}
          onBack={() => setPhase("ai-config")}
          onConfirm={() => resetOperation(`${selectedDepot?.start_location_name} AI 순찰계획을 확정했습니다.`)} />
      </section>
    </section>}

    <footer className="roadops-disclaimer">
      운영 우선순위 시나리오이며 사고확률이 아닙니다. 모든 경로는 현장 지시 전 담당자의 확인과 확정이 필요합니다.
    </footer>
  </article>;
}
