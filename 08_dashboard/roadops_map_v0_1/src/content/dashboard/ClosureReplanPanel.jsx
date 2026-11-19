import React, { useEffect, useRef, useState } from "react";
import { DataComponent } from "../../data-app-public.jsx";
import ReplanWorker from "./closure-replanning.worker.js?worker&inline";

const label = (task) => task?.location_label || task?.road_name || task?.task_id;
const minutes = (value) => Number(value).toFixed(1);

export function ClosureReplanPanel({ state, baseRoutes, taskRows, depot, result, onChange, taskLabel = label }) {
  const [closedText, setClosedText] = useState("");
  const [completedCount, setCompletedCount] = useState(0);
  const [elapsed, setElapsed] = useState("");
  const worker = useRef(null);
  const request = useRef(0);
  const timer = useRef(null);
  const onResult = useRef(onChange);
  onResult.current = onChange;
  const sorted = [...baseRoutes].sort((a, b) => Number(a.sequence) - Number(b.sequence));
  const estimatedSpent = sorted.slice(0, completedCount).reduce((sum, row) => sum + Number(row.travel_minutes) + Number(row.service_minutes), 0);
  useEffect(() => {
    try {
      const instance = new ReplanWorker(); worker.current = instance;
      instance.onmessage = ({ data }) => {
        if (data.requestId !== request.current) return;
        clearTimeout(timer.current); onResult.current(data.result);
      };
      instance.onerror = () => {
        clearTimeout(timer.current); request.current += 1;
        onResult.current({ status: "fail", routes: [], message: "계산기를 시작하지 못했습니다. 화면을 다시 열어 주세요." });
      };
    } catch {
      onResult.current({ status: "fail", routes: [], message: "이 브라우저에서는 대체 경로 계산기를 사용할 수 없습니다." });
    }
    return () => { request.current += 1; clearTimeout(timer.current); worker.current?.terminate(); worker.current = null; };
  }, []);
  const invalidate = () => {
    request.current += 1; clearTimeout(timer.current);
    onChange({ status: "dirty", routes: [], message: "입력 조건이 바뀌었습니다. 대체 경로를 계산해 주세요." });
  };
  const calculate = () => {
    const closedLinkIds = closedText.split(/[\s,]+/).filter(Boolean);
    if (!closedLinkIds.length) { onChange({ status: "fail", routes: [], message: "통제 구간 번호를 입력해 주세요." }); return; }
    if (!worker.current) { onChange({ status: "fail", routes: [], message: "계산기를 사용할 수 없습니다. 화면을 다시 열어 주세요." }); return; }
    const requestId = ++request.current;
    onChange({ status: "calculating", routes: [] });
    worker.current.postMessage({ requestId, input: { state, baseRoutes, taskRows, depot, completedCount, closedLinkIds, elapsedMinutes: elapsed.trim() ? Number(elapsed) : null } });
    timer.current = setTimeout(() => {
      if (request.current !== requestId) return;
      request.current += 1;
      onResult.current({ status: "fail", routes: [], message: "계산 시간이 길어져 중단했습니다. 조건 수정으로 돌아간 뒤 화면을 다시 열어 주세요." });
      worker.current?.terminate(); worker.current = null;
    }, 30000);
  };
  return <DataComponent variant="plain" id="closure-replan-control" queryId="travel_route_options" kind="custom"
    title="통제 반영·대체 경로 계산"
    description="선택팀의 남은 방문을 도로망에서 다시 계산합니다. 통제 정보는 담당자가 입력한 가정이며 실제 통제 정보의 자동 수집은 아닙니다."
    sourceRows={baseRoutes} displayRows={result?.status === "pass" ? result.routes : []}
    className="closure-replan-panel">
    <div className="closure-replan-inputs">
      <label>통제 구간 번호<input value={closedText} placeholder="예: 4050430101 (여러 구간은 쉼표로 구분)"
        onChange={(event) => { setClosedText(event.target.value); invalidate(); }} /></label>
      <label>완료한 점검<select value={completedCount} onChange={(event) => { setCompletedCount(Number(event.target.value)); setElapsed(""); invalidate(); }}>
        <option value={0}>아직 완료한 점검 없음</option>
        {sorted.map((row, i) => <option key={row.task_id} value={i + 1}>{i + 1}번째 {taskLabel(taskRows.find((t) => t.task_id === row.task_id))}까지 완료</option>)}
      </select></label>
      <label>이미 사용한 시간(분)<input type="number" min="0" step="0.1" value={elapsed}
        placeholder={`미입력 시 기존 예상 ${minutes(estimatedSpent)}분`}
        onChange={(event) => { setElapsed(event.target.value); invalidate(); }} /></label>
    </div>
    <div className="operation-actions">
      <button type="button" className="secondary-action" onClick={() => { setClosedText(""); setCompletedCount(0); setElapsed(""); request.current += 1; clearTimeout(timer.current); onChange(null); }}>통제 입력 초기화</button>
      <button type="button" className="primary-action" disabled={result?.status === "calculating" || !baseRoutes.length} onClick={calculate}>대체 경로 자동 계산</button>
    </div>
    {result?.status === "calculating" && <p role="status">통제 구간을 피하는 도로와 남은 방문 순서를 계산하고 있습니다.</p>}
    {result?.message && <p role={result.status === "fail" ? "alert" : "status"}>{result.message}</p>}
    {result?.status === "pass" && <div className="closure-replan-result" role="status" data-reviewed-rows="detour-result">
      <strong>완료 {result.completedCount}곳 유지 · 남은 방문 {result.routes.length - result.completedCount}곳 · 보류 {result.unassigned.length}곳</strong>
      <p>사용한 시간 {minutes(result.spentMinutes)}분 + 남은 이동·점검 {minutes(result.remainingMinutes)}분 = 총 {minutes(result.totalMinutes)}분</p>
      <p>가용 {minutes(result.availableMinutes)}분 중 {minutes(result.spareMinutes)}분 여유</p>
      {result.unassigned.map((row) => <p key={row.task_id}><b>{taskLabel(taskRows.find((t) => t.task_id === row.task_id))} 보류</b> — {row.reason}</p>)}
      <p>지도와 위 코스에 대체 경로를 반영했습니다. 현장 상황을 확인한 뒤 변경안을 확정하세요.</p>
    </div>}
    <small className="closure-replan-note">2026.10.14 표준노드링크 도로망 · 새 경로 시간은 제한속도 기반 추정이며 실시간 혼잡·회전 제한은 미반영입니다. 실제 통행 가능 여부는 출발 전 확인하세요.</small>
  </DataComponent>;
}
