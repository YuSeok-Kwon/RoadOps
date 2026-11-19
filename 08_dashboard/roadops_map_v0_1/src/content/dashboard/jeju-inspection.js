// Historical evidence informs inspection tasks; it does not invent live hazards.
const numeric = (value) => value == null || value === "" ? null : Number(value);
export const SURFACE_ACTIONS = {
  "건조": ["노면 파손·이물질과 배수구 막힘 확인"],
  "젖음/습기": ["물고임·배수구 막힘 확인", "미끄럼 방지시설과 노면 상태 확인"],
  "서리/결빙": ["결빙 구간과 노면온도 현장 확인", "제설·미끄럼 방지 자재 및 통행 조치 검토"],
  "적설": ["적설 깊이와 제설 상태 확인", "제설 장비 접근과 통행 가능 여부 확인"],
  "해빙": ["해빙으로 인한 노면 파손과 사면 이완 확인"],
  "기타": ["노면 상태를 현장에서 확인하고 유형 기록"],
};
export function surfaceSummary(rows, surface, startYear = 2005, endYear = 2020) {
  const selected = rows.filter(r => r.surface === surface && Number(r.year) >= startYear && Number(r.year) <= endYear);
  const valid = selected.filter(r => [r.accident_count, r.fatality_count, r.injury_count].every(v => numeric(v) != null && Number.isFinite(numeric(v)) && numeric(v) >= 0));
  const sum = key => valid.reduce((total, r) => total + Number(r[key]), 0);
  const accidents = sum("accident_count"), fatalities = sum("fatality_count"), injuries = sum("injury_count");
  return { surface, startYear, endYear, rows: selected, completeYears: valid.length,
    missingYears: endYear - startYear + 1 - valid.length, accidents, fatalities, injuries,
    fatalitiesPer100: accidents > 0 ? fatalities * 100 / accidents : null };
}
export function matchingHazards(task, records) {
  if (!task || !String(task.administrative_city || task.location_label || "").includes("제주시")) return [];
  const location = [task.administrative_unit, task.location_label, task.road_address, task.address].filter(Boolean).join(" ");
  const tokens = location.match(/[가-힣0-9]+(?:읍|면|동|리)/g) || [];
  return records.filter(row => tokens.some(token => String(row.location).includes(token)))
    .map(row => ({ ...row, match_precision: "same_administrative_area", road_location_confirmed: false }));
}
export function makeInspectionPlan({ task, surface, surfaceSelection = null, surfaceRows, hazards, startYear = 2005, endYear = 2020 }) {
  const summary = surfaceSummary(surfaceRows, surface, startYear, endYear);
  const matched = matchingHazards(task, hazards).filter(r => r.designation_status === "review_required");
  const actions = [];
  if (SURFACE_ACTIONS[surface] && summary.completeYears > 0) actions.push(...SURFACE_ACTIONS[surface]);
  for (const hazard of matched) {
    const check = hazard.hazard_type.includes("붕괴") ? "사면·낙석 및 접근 가능 여부" : hazard.hazard_type.includes("해일") ? "해안 월파·통행 상황" : "배수·침수·유실 징후";
    actions.push(`${hazard.name}: 정확한 지구 위치와 ${check} 확인 (같은 행정지역 참고)`);
  }
  return { version: "jeju-inspection-v1", linkId: String(task?.link_id || ""),
    surface: surface || "미확인",
    surfaceBasis: `${surfaceSelection?.mode === "automatic" ? "거점 날씨 기반 자동 추정" : "담당자 선택"} · 현장 확인 필요`,
    surfaceSelection, startYear, endYear,
    statisticalEvidence: summary.completeYears ? { accidents: summary.accidents, fatalities: summary.fatalities, completeYears: summary.completeYears, missingYears: summary.missingYears } : null,
    hazardIds: matched.map(r => r.hazard_id), actions: [...new Set(actions)],
    sourceUrls: [...new Set([...(summary.completeYears ? ["https://jejudatahub.net/data/view/data/891"] : []), ...(surfaceSelection?.weather?.source_url ? [surfaceSelection.weather.source_url] : []), ...matched.map(r => r.source_url)])],
    automaticClosure: false, scoreAdjustment: 0,
    note: "과거 통계·행정지역 참고로 생성한 점검 항목. 실제 노면·지구 위치·추가 소요시간은 담당자 확인." };
}
export function latestHotspotYear(rows) {
  return Math.max(0, ...rows.map(r => Number(r.analysis_year) || 0));
}
export function hotspotsForYear(rows, year) {
  return rows.filter(r => Number(r.analysis_year) === Number(year));
}
