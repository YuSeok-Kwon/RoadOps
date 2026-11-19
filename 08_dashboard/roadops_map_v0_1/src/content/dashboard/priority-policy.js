export const POLICY_VERSION = "roadops-operator-priority-v0.2";
export const POLICY_STORAGE_KEY = "roadops:operator-priority:v0.2";
export const CRITERIA = [
  { key: "event", label: "현재 도로 위험상황", rule: "돌발 70 · 통제 90 · 작업 55. 해당 유형이 아니면 계산 대상에서 제외합니다." },
  { key: "structural", label: "과거 사고·도로 구조", rule: "TAAS 위험등급과 도로 선형 심각도를 7:3으로 반영합니다." },
  { key: "weather_road", label: "기상·노면 상태", rule: "비·눈·바람·가시거리·마찰 등 확인된 신호 중 가장 높은 지수를 사용합니다." },
  { key: "traffic", label: "실시간 교통", rule: "통행속도 저하·점유율 중 높은 지수. 미래 시점의 교통값은 미확인입니다." },
  { key: "gateway", label: "공항 유입", rule: "시간대별 유입·운항차질에 공항에서 20km까지의 거리감쇠를 적용합니다." },
  { key: "accident_hotspot", label: "주변 사고다발지역", rule: "1km 이내 거리감쇠 × 사고건수/40(최대 1). 과거 사고·도로 구조와 함께 선택하면 겹치는 지수를 차감합니다." },
  { key: "similar_history", label: "과거 유사상황", rule: "24시간 이전~90일 이내, 유사도 80% 이상 같은 도로의 사건 기록. 하루 한 번, 3일 상당에서 지수 100입니다." },
  { key: "city_safety", label: "생활안전 순찰 수요", rule: "두 행정시의 강력·절도·폭력 건수 중 해당 시의 비중. 같은 시의 도로에 동일 적용하며 도로별 범죄위험은 아닙니다." },
];
export const DEFAULT_POLICY = {
  version: POLICY_VERSION, method: "available",
  weights: { event: 30, structural: 20, weather_road: 20, traffic: 10, gateway: 5, accident_hotspot: 8, similar_history: 5, city_safety: 2 },
};
function numeric(value) {
  if (value == null || typeof value === "boolean" || String(value).trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
const round = (value, digits = 6) => Number(value.toFixed(digits));
export function policyError(policy) {
  if (policy?.version !== POLICY_VERSION || !["available", "complete"].includes(policy.method)) return "지원하지 않는 점수 계산 방식입니다.";
  if (Object.keys(policy.weights || {}).sort().join() !== CRITERIA.map((row) => row.key).sort().join()) return "점수 항목이 일치하지 않습니다.";
  const weights = Object.values(policy.weights).map(numeric);
  if (weights.some((value) => value == null || value < 0 || value > 100)) return "배점은 0~100의 숫자로 입력하세요.";
  if (Math.abs(weights.reduce((sum, value) => sum + value, 0) - 100) > 1e-6) return "선택한 항목의 배점 합계를 100점으로 맞춰주세요.";
  if (!["event", "structural", "weather_road", "traffic"].some((key) => Number(policy.weights[key]) > 0)) return "도로 관련 항목을 하나 이상 포함하세요.";
  return null;
}
export function policyFingerprint(policy) {
  return JSON.stringify([policy.version, policy.method, ...CRITERIA.map(({ key }) => Number(policy.weights[key]))]);
}
export function parsePolicy(value) {
  try {
    const policy = typeof value === "string" ? JSON.parse(value) : value;
    return policyError(policy) ? null : { ...policy, weights: Object.fromEntries(CRITERIA.map(({ key }) => [key, Number(policy.weights[key])])) };
  } catch { return null; }
}
export function normalizeWeights(policy) {
  const selected = CRITERIA.filter(({ key }) => (numeric(policy.weights[key]) ?? 0) > 0);
  const sum = selected.reduce((total, { key }) => total + Number(policy.weights[key]), 0);
  if (!sum) return policy;
  const weights = Object.fromEntries(CRITERIA.map(({ key }) => [key, 0]));
  let remaining = 100;
  selected.forEach(({ key }, index) => {
    weights[key] = index === selected.length - 1 ? round(remaining, 2) : round(Number(policy.weights[key]) * 100 / sum, 2);
    remaining -= weights[key];
  });
  return { ...policy, weights };
}
export function calculatePriority(inputs, policy) {
  const error = policyError(policy);
  if (error) throw new Error(error);
  const originals = new Map((inputs.factors || []).map((row) => [row.key, row]));
  const factors = CRITERIA.map(({ key, label }) => {
    const original = originals.get(key) || { key, label, status: "unavailable", description: "자료가 없습니다." };
    const row = { ...original, weight: Number(policy.weights[key]), contribution: null };
    let value = numeric(row.value);
    let coverage = numeric(row.coverage) ?? 0;
    if (value == null || value < 0 || value > 100 || coverage < 0 || coverage > 1) { value = null; coverage = 0; }
    if (key === "accident_hotspot" && row.weight > 0 && Number(policy.weights.structural) > 0 && value != null) {
      const structural = numeric(originals.get("structural")?.value);
      if (structural != null) {
        row.overlap_deduction = Math.min(value, Math.max(0, structural));
        value = Math.max(0, value - structural);
        row.description += " 과거 사고·도로 구조와 함께 선택해 겹치는 항목지수를 차감했습니다.";
      }
    }
    if (!row.weight) row.status = "excluded";
    return { ...row, value, coverage };
  });
  const applicable = factors.filter((row) => row.weight > 0 && row.status !== "not_applicable");
  const expected = applicable.reduce((sum, row) => sum + row.weight, 0);
  const observed = applicable.reduce((sum, row) => sum + (row.value == null ? 0 : row.weight * row.coverage), 0);
  const coverage = expected ? observed / expected : 0;
  const threshold = policy.method === "complete" ? 1 - 1e-9 : .6 - 1e-9;
  const roadEvidence = applicable.some((row) => ["event", "structural", "weather_road", "traffic"].includes(row.key) && row.value != null && row.coverage > 0);
  const available = !inputs.blocked && coverage >= threshold && observed > 0 && roadEvidence;
  let score = null;
  if (available) {
    applicable.forEach((row) => { if (row.value != null) row.contribution = round(row.weight * row.coverage * row.value / observed); });
    score = round(factors.reduce((sum, row) => sum + (row.contribution ?? 0), 0), 3);
  }
  const lower = expected ? applicable.reduce((sum, row) => sum + row.weight * row.coverage * (row.value ?? 0), 0) / expected : null;
  const upper = lower == null ? null : lower + (1 - coverage) * 100;
  return { score, available, coverage: round(coverage), factors, lower: available ? round(lower, 3) : null, upper: available ? round(upper, 3) : null, method: policy.method };
}
export function applyPriorityPolicy(rows, policy) {
  return rows.map((row) => {
    if (!row.priority_candidates?.length) return row;
    const candidates = row.priority_candidates.map((input) => ({ ...input, result: calculatePriority(input, policy) }));
    candidates.sort((a, b) => (b.result.score ?? -1) - (a.result.score ?? -1));
    const basis = candidates[0];
    const result = basis.result;
    return { ...row, priority_score: result.score, score_lower_bound: result.lower, score_upper_bound: result.upper,
      ranking_eligible: result.available, evidence_coverage_ratio: result.coverage,
      risk_level: result.score == null ? null : result.score >= 75 ? "critical" : result.score >= 50 ? "high" : result.score >= 25 ? "moderate" : "low",
      score_basis_event_id: basis.event_id, score_basis_event_type: basis.event_type,
      priority_result: result, scoring_policy_json: JSON.stringify(policy),
      score_basis_drivers: result.factors.filter((factor) => factor.contribution != null).map((factor) => `policy:${factor.key}:${factor.contribution}`).join("|") };
  });
}
