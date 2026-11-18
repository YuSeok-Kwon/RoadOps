const DRIVER_DETAILS = {
  "event:active_road_event": ["현재 도로 위험상황", "C-ITS에 등록된 도로 돌발정보를 반영했습니다."],
  "event:active_road_closure": ["도로 통제", "C-ITS에 등록된 도로 통제정보를 반영했습니다."],
  "event:active_road_work": ["도로 작업", "C-ITS에 등록된 도로 작업정보를 반영했습니다."],
  "structural:taas": ["과거 교통사고 위험", "TAAS 도로 위험등급을 중심으로 구조위험을 반영했습니다."],
  "structural:jeju_datahub_geometry": ["도로 선형 위험", "제주데이터허브의 도로 선형별 사고 심각도를 중심으로 구조위험을 반영했습니다."],
  "traffic:speed_to_limit_ratio": ["통행속도 저하", "제한속도 대비 실제 통행속도를 반영했습니다."],
  "traffic:occupancy_rate": ["교통 점유율", "도로의 차량 점유율을 반영했습니다."],
  "weather_road:kma_wind_speed": ["바람 영향", "기상청 풍속 자료를 기상·노면 위험에 반영했습니다."],
  "weather_road:kma_precipitation_type": ["비·눈 영향", "기상청 강수형태 자료를 기상·노면 위험에 반영했습니다."],
  "weather_road:kma_rainfall_1h": ["강수량 영향", "기상청 시간당 강수량을 기상·노면 위험에 반영했습니다."],
  "weather_road:cits_visibility": ["시야 확보 상태", "C-ITS 가시거리 센서값을 기상·노면 위험에 반영했습니다."],
  "weather_road:cits_friction": ["노면 미끄럼 위험", "C-ITS 노면 마찰계수를 기상·노면 위험에 반영했습니다."],
  "weather_road:cits_road_temperature": ["낮은 노면온도", "C-ITS 노면온도 센서값을 반영했습니다. 실제 결빙 여부는 현장 확인이 필요합니다."],
  "weather_road:cits_snow": ["노면 적설", "C-ITS 적설 센서값을 기상·노면 위험에 반영했습니다."],
  "weather_road:cits_water_film": ["노면 수막", "C-ITS 수막 센서값을 기상·노면 위험에 반영했습니다."],
  "gateway:airport_inflow_pressure": ["제주공항 유입 영향", "제주공항 시간대별 유입 압력을 반영했습니다."],
};

function finiteNumber(value) {
  if (value == null || typeof value === "boolean" || String(value).trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function parseDriver(value) {
  const raw = String(value || "").trim();
  const splitAt = raw.lastIndexOf(":");
  const key = splitAt > -1 ? raw.slice(0, splitAt) : raw;
  const [label, description] = DRIVER_DETAILS[key]
    || ["기타 확인 요소", "세부 산정 기준은 원본 점수 근거에서 확인해야 합니다."];
  return { raw, key, label, description, contribution: splitAt > -1 ? finiteNumber(raw.slice(splitAt + 1)) : null };
}

export function scoreExplanation(row) {
  const score = finiteNumber(row?.priority_score);
  const unavailable = { score, drivers: [], remainder: null, capAdjustment: null, available: false };
  if (score == null) return unavailable;
  // Older multi-event snapshots merge drivers from different scores. Do not add them.
  const basis = row.score_basis_drivers ?? (Number(row.event_count) <= 1 ? row.risk_drivers : null);
  const drivers = String(basis || "").split("|").filter((value) => value.trim()).map(parseDriver)
    .sort((left, right) => (right.contribution ?? -1) - (left.contribution ?? -1));
  if (!drivers.length || drivers.some((driver) => driver.contribution == null || driver.contribution < 0)) return unavailable;
  const sum = drivers.reduce((total, driver) => total + driver.contribution, 0);
  // Contributions are stored to three decimals; tolerate their rounding only.
  const tolerance = (drivers.length + 1) * 0.0005 + 1e-9;
  if (sum > score + tolerance && score !== 100) return unavailable;
  return {
    score, drivers, available: true,
    remainder: score - sum > tolerance ? score - sum : null,
    capAdjustment: sum - score > tolerance ? sum - score : null,
  };
}

export function prioritySummary(row) {
  const explanation = scoreExplanation(row);
  if (!explanation.available) return explanation.score == null
    ? "점수 산정에 필요한 근거가 부족합니다."
    : "이 점수에 대응하는 세부 근거를 확인해야 합니다.";
  const drivers = explanation.drivers.filter((driver) => driver.contribution > 0).slice(0, 2);
  return drivers.length
    ? drivers.map((driver) => `${driver.label} ${driver.contribution.toFixed(1)}점`).join(" · ")
    : "확인된 주요 요인의 점수 기여는 0점입니다.";
}
