import React, { useState } from "react";
import { CRITERIA, normalizeWeights, policyError, policyFingerprint } from "./priority-policy.js";

export function ScoringPolicyPanel({ policy, onApply, onClose }) {
  const [draft, setDraft] = useState(() => ({ ...policy, weights: { ...policy.weights } }));
  const error = policyError(draft);
  const total = Object.values(draft.weights).reduce((sum, value) => sum + (Number(value) || 0), 0);
  const changed = policyFingerprint(draft) !== policyFingerprint(policy);
  const setWeight = (key, value) => setDraft((current) => ({ ...current, weights: { ...current.weights, [key]: value } }));
  return <section className="scoring-policy-panel" aria-label="점수 계산 설정">
    <header><div><span>수동·AI 공통 기준</span><h2>점수에 넣을 항목과 배점</h2>
      <p>담당자가 적용한 기준으로 모든 도로를 다시 계산합니다. AI는 배점을 바꾸지 않습니다.</p></div>
      <button type="button" className="secondary-action" onClick={onClose}>닫기</button></header>
    <div className="scoring-policy-grid">
      {CRITERIA.map(({ key, label, rule }) => <div className="scoring-policy-criterion" key={key}>
        <label><input type="checkbox" checked={Number(draft.weights[key]) > 0}
          onChange={(event) => setWeight(key, event.target.checked ? 10 : 0)} aria-label={`${label} 포함`} />{label}</label>
        <label className="scoring-weight-input"><input type="number" min="0" max="100" step="0.1"
          value={draft.weights[key]} onChange={(event) => setWeight(key, event.target.value)} aria-label={`${label} 배점`} /><span>점</span></label>
        <p>{rule}</p>
      </div>)}
    </div>
    <div className="scoring-policy-method"><label htmlFor="priority-method">자료가 빠졌을 때</label>
      <select id="priority-method" value={draft.method} onChange={(event) => setDraft((current) => ({ ...current, method: event.target.value }))}>
        <option value="available">확인된 근거로 100점 환산</option>
        <option value="complete">선택한 근거가 모두 있어야 산정</option>
      </select>
      <p>{draft.method === "available" ? "항목별 배점 × 근거 반영률 × 항목지수를 합산하고, 확인된 배점 합계로 나눕니다. 근거 반영률이 60% 미만이면 보류합니다." : "적용 대상인 모든 항목의 근거가 완전할 때만 배점 × 항목지수를 합산해 적용 대상 배점의 합계로 나눕니다. 하나라도 부족하면 보류합니다."} 자료 없음과 확인된 0점은 구분합니다.</p>
    </div>
    <footer><div><strong>배점 합계 {Number(total.toFixed(2))} / 100점</strong>
      <p role="status">{error || (changed ? "적용 전 변경사항입니다." : "현재 적용 중인 설정입니다.")}</p>
      <small>이 브라우저에 저장되며 새로고침 후에도 유지됩니다. 초기 배점은 운영 시나리오용이며 검증된 사고확률 모형이 아닙니다.</small></div>
      <button type="button" className="secondary-action" onClick={() => setDraft(normalizeWeights(draft))} disabled={total <= 0}>비율대로 100점 맞추기</button>
      <button type="button" className="primary-action" disabled={Boolean(error) || !changed} onClick={() => onApply(draft)}>설정 적용·다시 계산</button>
    </footer>
  </section>;
}
