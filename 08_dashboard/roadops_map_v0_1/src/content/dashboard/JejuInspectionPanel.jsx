import React, { useState } from "react";
import { DataComponent } from "../../data-app-public.jsx";
import { SURFACE_ACTIONS, surfaceSummary, matchingHazards, makeInspectionPlan, hotspotsForYear } from "./jeju-inspection.js";
import { inferSurface, resolveSurfaceSelection, surfaceContextKey, makeSurfaceOverride, weatherTimeLabel } from "./surface-weather.js";

const STATUS = { released: "지정 해제", works_completed: "정비 완료 · 지정 상태 확인", review_required: "위치·현장 확인 대상" };
const fmt = (n, digits = 0) => n == null ? "자료 없음" : Number(n).toLocaleString("ko-KR", { maximumFractionDigits: digits });
export function JejuInspectionPanel({ tasks, selectedLinkId, surfaceRows, hazardRows, hotspotRows, hotspotYear, onYear, onSelectTask, onShowHotspot, onApply, plans, depot, horizon, weatherRows = [], currentTime, surfaceOverrides = {}, onSurfaceOverride }) {
  const [tab, setTab] = useState("surface");
  const [period, setPeriod] = useState("2005");
  const [allAreas, setAllAreas] = useState(false);
  const [showReleased, setShowReleased] = useState(false);
  const task = tasks.find(r => String(r.link_id) === String(selectedLinkId)) || tasks[0];
  if (!task) return null;
  const weather = weatherRows.find(r => r.team_id === depot?.team_id && Number(r.horizon_hours) === horizon);
  const automatic = inferSurface(weather, currentTime);
  const contextKey = surfaceContextKey(depot?.team_id, task.link_id, horizon);
  const selection = resolveSurfaceSelection(automatic, surfaceOverrides[contextKey]);
  const surface = selection.surface;
  const startYear = Number(period), endYear = 2020;
  const summary = surfaceSummary(surfaceRows, surface, startYear, endYear);
  const matched = matchingHazards(task, hazardRows);
  const hazards = (allAreas ? hazardRows : matched).filter(r => showReleased || r.designation_status !== "released");
  const plan = makeInspectionPlan({ task, surface, surfaceSelection: selection, surfaceRows, hazards: hazardRows, startYear, endYear });
  const years = [...new Set(hotspotRows.map(r => r.analysis_year))].sort((a,b) => b-a);
  const hotspots = hotspotsForYear(hotspotRows, hotspotYear);
  const applied = plans[String(task.link_id)];
  return <DataComponent variant="plain" id="jeju-inspection-evidence" queryId="surface_accidents"
    queryIds={["surface_accidents", "designated_hazards", "accident_hotspots", "depot_weather"]} kind="custom"
    title="제주 데이터로 점검 항목 준비" description="노면 통계·사고다발 지점·재해위험지구를 확인하고 도로별 점검 항목에 반영합니다."
    sourceRows={surfaceRows} displayRows={tab === "surface" ? summary.rows : tab === "hazards" ? hazards : hotspots}
    sourceRowsByQuery={{ surface_accidents: surfaceRows, designated_hazards: hazardRows, accident_hotspots: hotspotRows, depot_weather: weatherRows }}
    className="jeju-inspection-panel">
    <label className="inspection-road-select">점검할 도로 <select aria-label="제주 데이터 점검 도로" value={String(task.link_id)} onChange={e=>onSelectTask(e.target.value)}>
      {tasks.map(r=><option key={r.task_id} value={String(r.link_id)}>{r.location_label || `${r.administrative_unit} ${r.road_name}`}</option>)}
    </select></label>
    <div className="inspection-tabs" role="tablist" aria-label="제주 데이터 유형">
      {[['surface','노면 사고 통계'],['hotspots','TAAS + 허브 사고다발'],['hazards','붕괴·자연재해']].map(([key,label])=><button key={key} type="button" role="tab" aria-selected={tab===key} onClick={()=>setTab(key)}>{label}</button>)}
    </div>
    {tab === "surface" && <section className="inspection-evidence-view">
      <div className="inspection-weather" data-reviewed-rows="depot_weather">
        <div className="inspection-weather-heading"><strong>{depot?.start_location_name} · {horizon ? `${horizon}시간 후` : "현재"} 예상 노면</strong>
          <span className="inspection-selection-mode">{selection.mode === "manual" ? "담당자 수정" : "날씨 기반 자동 선택"}</span></div>
        <p>{automatic.reason}</p>
        {weather?.valid_at && <p className="inspection-source">기상청 격자 {weather.grid_x}, {weather.grid_y} · {weather.evidence_kind === "observation" ? "관측" : "예보"} {weatherTimeLabel(weather.valid_at)} 기준 (한국시간)</p>}
        <small>거점 날씨로 추정한 조건입니다. 도로의 실제 노면 상태에 맞게 수정할 수 있습니다.</small>
      </div>
      <div className="inspection-controls"><label>예상 노면 <select aria-label="예상 노면" value={surface} onChange={e=>onSurfaceOverride(contextKey, makeSurfaceOverride(e.target.value, automatic))}><option value="">미확인 · 직접 확인</option>{Object.keys(SURFACE_ACTIONS).map(s=><option key={s}>{s}</option>)}</select></label>
        {selection.mode === "manual" && <button type="button" className="inspection-auto-reset" onClick={()=>onSurfaceOverride(contextKey, null)}>자동 추천으로 되돌리기</button>}
        <label>집계 기간 <select aria-label="노면 통계 기간" value={period} onChange={e=>setPeriod(e.target.value)}><option value="2005">2005–2020년</option><option value="2018">2018–2020년</option></select></label></div>
      {selection.mode === "manual" && <p className="inspection-source">담당자 수정값은 날씨가 갱신되어도 유지됩니다. 현재 자동 추천: {automatic.surface || "미확인"}</p>}
      <p className="inspection-source"><a href="https://jejudatahub.net/data/view/data/891" target="_blank" rel="noreferrer">제주데이터허브 · 제주 노면 상태별 교통사고 통계</a> · {surface || "미확인"} 조건의 과거 통계</p>
      {surface ? <div data-reviewed-rows><div className="inspection-metrics"><div><span>해당 노면 사고</span><strong>{fmt(summary.completeYears ? summary.accidents : null)}<small>건</small></strong></div><div><span>사망자</span><strong>{fmt(summary.completeYears ? summary.fatalities : null)}<small>명</small></strong></div><div><span>사고 100건당 사망자</span><strong>{fmt(summary.fatalitiesPer100,2)}<small>명</small></strong></div></div>
        <p>{summary.completeYears}개 연도 집계{summary.missingYears > 0 && ` · ${summary.missingYears}개 연도 결측 제외`}. 통행량 분모가 없어 사고 발생확률·현재 도로 위험률로 해석하지 않습니다.</p></div>
        : <p>노면 상태를 선택하면 과거 피해 통계와 확인할 점검 항목을 제안합니다.</p>}
    </section>}
    {tab === "hotspots" && <section className="inspection-evidence-view"><div className="inspection-controls"><label>지도에 표시할 분석연도 <select aria-label="사고다발 분석연도" value={hotspotYear} onChange={e=>onYear(Number(e.target.value))}>{years.map(y=><option key={y}>{y}</option>)}</select></label><span>연도별 선정지점 {hotspots.length}곳</span></div>
      <p>TAAS 최신 자료와 허브의 과거 선정지점을 연도별로 비교합니다. 서로 다른 연도의 사고를 합산하지 않습니다.</p>
      <div className="inspection-table-wrap" data-reviewed-rows="accident_hotspots"><table><thead><tr><th>발생 지점</th><th>사고</th><th>출처</th><th>지도</th></tr></thead><tbody>{hotspots.map(r=><tr key={r.hotspot_id}><td>{r.location_name}</td><td>{fmt(r.accident_count)}건</td><td>{r.source_label}</td><td><button type="button" onClick={()=>onShowHotspot(r)}>위치 보기</button></td></tr>)}</tbody></table></div>
      <p className="inspection-source">허브 공개 CSV: 2017–2022년 36행 · 전체 API 결과와 범위가 다릅니다. 최근 3개년 이외의 자료는 현재 우선순위 점수에 더하지 않습니다.</p>
    </section>}
    {tab === "hazards" && <section className="inspection-evidence-view"><div className="inspection-controls"><label><input type="checkbox" checked={allAreas} onChange={e=>setAllAreas(e.target.checked)}/> 제주시 전체 지구 보기</label><label><input type="checkbox" checked={showReleased} onChange={e=>setShowReleased(e.target.checked)}/> 해제 이력 포함</label></div>
      <p>2026.06.30 기준 · {allAreas ? "제주시 전체" : "선택 도로와 같은 행정지역"} {hazards.length}건. 정확한 좌표·경계가 없어 도로 위의 위험지점으로 표시하거나 자동 통제하지 않습니다.</p>
      <div className="inspection-table-wrap" data-reviewed-rows="designated_hazards"><table><thead><tr><th>지구·위치</th><th>유형·등급</th><th>현재 자료의 상태</th></tr></thead><tbody>{hazards.map(r=><tr key={r.hazard_id}><td><strong>{r.name}</strong><br/>{r.location}</td><td>{r.hazard_type} · {r.grade}</td><td>{STATUS[r.designation_status]}<br/><small>{r.remarks || r.works_status}</small></td></tr>)}</tbody></table></div>
      {!hazards.length && <p>이 행정지역에 일치하는 미해제 자료가 없습니다. 위험이 없다는 뜻은 아닙니다.</p>}
      <p className="inspection-source">제주데이터허브 435·436이 연결한 공공데이터포털 최신 원본. 해제된 지구는 점검 항목 자동 제안에서 제외합니다.</p>
    </section>}
    <section className="inspection-actions"><strong>이 도로에 제안하는 점검 항목</strong>
      {plan.actions.length ? <ul>{plan.actions.map(item=><li key={item}>{item}</li>)}</ul> : <p>확인한 노면 조건 또는 일치하는 재해위험지구가 있어야 항목을 생성합니다.</p>}
      <button type="button" className="primary-action" disabled={!plan.actions.length} onClick={()=>onApply(plan)}>점검계획에 반영</button>
      {applied && <p role="status">반영된 점검 항목 {applied.actions.length}개 · 추천 순찰코스와 확인 기록에 포함됩니다.</p>}
      {applied && JSON.stringify(applied) !== JSON.stringify(plan) && <p className="inspection-source">조건 또는 근거가 변경되었습니다. 새 내용을 사용하려면 점검계획에 다시 반영하세요.</p>}
      <small>현장 확인 전 제안입니다. 점검 범위가 늘어나면 소요시간도 함께 조정하세요.</small>
    </section>
  </DataComponent>;
}
