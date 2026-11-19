// Operational suggestions, not a road-surface observation or a trained risk model.
export const SURFACE_RULE_VERSION = "depot-weather-v1";
export const WEATHER_MAX_AGE_MINUTES = 180;
const PTY = { 0: "강수 없음", 1: "비", 2: "비/눈", 3: "눈", 4: "소나기", 5: "빗방울", 6: "빗방울/눈날림", 7: "눈날림" };
const number = value => value == null || String(value).trim() === "" || typeof value === "boolean" ? null : Number.isFinite(Number(value)) ? Number(value) : null;
const stamp = value => typeof value === "string" && value ? Date.parse(value) : NaN;
const minutes = (a, b) => (a - b) / 60000;

export function surfaceContextKey(depotId, linkId, horizon) {
  return JSON.stringify([String(depotId), String(linkId), Number(horizon)]);
}

export function inferSurface(weather, now = new Date()) {
  const unknown = reason => ({ surface: "", reason, weather: weather || null, ruleVersion: SURFACE_RULE_VERSION });
  if (!weather || weather.status !== "usable") return unknown("거점 날씨 자료가 없어 담당자 확인이 필요합니다.");
  const current = Number(new Date(now));
  const generated = stamp(weather.generated_at), valid = stamp(weather.valid_at), target = stamp(weather.target_at);
  const age = minutes(current, generated);
  if (![current, generated, valid, target].every(Number.isFinite) || age < -5 || age > WEATHER_MAX_AGE_MINUTES)
    return unknown("날씨 자료의 기준시각을 확인하거나 최신 자료를 불러와 주세요.");
  const horizon = number(weather.horizon_hours);
  if (![0, 1, 3, 6].includes(horizon) || Math.abs(minutes(target, generated) - horizon * 60) > 60)
    return unknown("선택 시점과 날씨 자료가 일치하지 않습니다.");
  if (weather.evidence_kind === "observation") {
    if (horizon !== 0 || minutes(current, valid) > 120 || minutes(current, valid) < -5)
      return unknown("현재 관측자료가 오래되어 담당자 확인이 필요합니다.");
  } else if (weather.evidence_kind !== "forecast" || Math.abs(minutes(valid, target)) > 60) {
    return unknown("선택 시점에 맞는 예보가 없습니다.");
  }
  const temperature = number(weather.temperature_c), pty = number(weather.precipitation_type);
  const humidity = number(weather.humidity_percent);
  if (temperature == null || temperature < -50 || temperature > 60 || pty == null || !Object.hasOwn(PTY, pty))
    return unknown("기온 또는 강수형태 자료가 누락되어 담당자 확인이 필요합니다.");
  const raw = String(weather.rainfall_raw ?? "").trim();
  const rainfall = number(raw.replace(/mm$/i, "").trim());
  const positiveRain = rainfall > 0 || /^(1mm|1\.0mm)\s*미만$/.test(raw);
  const noRain = rainfall === 0 || raw === "강수없음" || raw === "강수 없음";
  const result = (surface, reason) => ({ surface, reason, weather, ruleVersion: SURFACE_RULE_VERSION });
  const basis = `${PTY[pty]} · 기온 ${temperature}℃`;
  if ([3, 7].includes(pty) || ([2, 6].includes(pty) && temperature <= 0))
    return result("적설", `${basis} → 적설 가능성 점검`);
  if (pty !== 0 || positiveRain)
    return result(temperature <= 0 ? "서리/결빙" : "젖음/습기", `${basis} → ${temperature <= 0 ? "결빙 가능성" : "젖은 노면"} 점검`);
  if (temperature <= 0 && humidity != null && humidity >= 90 && humidity <= 100)
    return result("서리/결빙", `${basis} · 습도 ${humidity}% → 서리·결빙 가능성 점검`);
  if (!noRain || (temperature <= 0 && (humidity == null || humidity < 0 || humidity > 100)))
    return unknown("강수량 또는 저온 시 습도 자료가 부족해 담당자 확인이 필요합니다.");
  return result("건조", `${basis} → 건조 추정 · 잔류 물기·눈은 현장 확인`);
}

export function resolveSurfaceSelection(automatic, override) {
  const manual = override && typeof override.surface === "string";
  return {
    mode: manual ? "manual" : "automatic",
    surface: manual ? override.surface : automatic.surface,
    recommendedSurface: automatic.surface,
    reason: automatic.reason,
    ruleVersion: automatic.ruleVersion,
    weather: automatic.weather,
    // Retain what the operator saw when making the override as well as the latest basis.
    overrideBasis: manual ? override.basis : null,
    modifiedAt: manual ? override.modifiedAt : null,
  };
}

export function makeSurfaceOverride(surface, automatic, now = new Date()) {
  return { surface, modifiedAt: new Date(now).toISOString(), basis: automatic };
}

export function weatherTimeLabel(value) {
  const parsed = stamp(value);
  return Number.isFinite(parsed) ? new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(parsed) : "시각 미확인";
}
