import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { surfaceSummary, matchingHazards, makeInspectionPlan, hotspotsForYear } from '../src/content/dashboard/jeju-inspection.js';
import { createWorkflowState, workflowFingerprint, createApprovalRecord } from '../src/content/dashboard/workflow-policy.js';
const data = JSON.parse(fs.readFileSync(new URL('../../../demo/jeju_inspection_evidence_v0_1.json', import.meta.url)));
test('rates use pooled accidents and preserve missing years', () => {
  const rows = [{year:2019,surface:'젖음/습기',accident_count:10,fatality_count:2,injury_count:12}, {year:2020,surface:'젖음/습기',accident_count:90,fatality_count:0,injury_count:98}];
  assert.equal(surfaceSummary(rows,'젖음/습기',2019,2020).fatalitiesPer100,2);
  const missing=surfaceSummary([{...rows[0],accident_count:null}],'젖음/습기',2019,2020);
  assert.equal(missing.fatalitiesPer100,null); assert.equal(missing.missingYears,2);
});
test('released Gwangnyeong is excluded and regional matches never become closures', () => {
  const task={link_id:'1',administrative_city:'제주시',administrative_unit:'애월읍',location_label:'제주시 애월읍 광령리'};
  const matching=matchingHazards(task,data.designated_hazards);
  assert(matching.some(r=>r.name==='광령리' && r.designation_status==='released'));
  const p=makeInspectionPlan({task,surface:'젖음/습기',surfaceRows:data.surface_accidents,hazards:data.designated_hazards});
  assert(p.actions.some(a=>a.includes('물고임'))); assert(!p.actions.some(a=>a.startsWith('광령리:')));
  assert.equal(p.automaticClosure,false); assert.equal(p.scoreAdjustment,0);
  assert.equal(matchingHazards({...task,administrative_city:'서귀포시'},data.designated_hazards).length,0);
});
test('unknown surface creates no fabricated surface evidence', () => {
  const p=makeInspectionPlan({task:{link_id:'1'},surface:'',surfaceRows:data.surface_accidents,hazards:[]});
  assert.equal(p.statisticalEvidence,null); assert.deepEqual(p.actions,[]);
});
test('different years stay separate on map',()=>{
  assert.equal(hotspotsForYear(data.hub_accident_hotspots,2022).length,6);
  assert.equal(hotspotsForYear(data.hub_accident_hotspots,2025).length,0);
});
test('inspection evidence changes confirmation fingerprint and is retained in approval',()=>{
  const state=createWorkflowState({tasks:[{task_id:'t',link_id:'1',inspection_plan:{actions:['배수 확인'],sourceUrls:['hub891']}}]});
  const before=workflowFingerprint(state); state.tasks[0].inspectionPlan.actions.push('사면 확인');
  assert.notEqual(workflowFingerprint(state),before);
  assert.equal(createApprovalRecord(state,'none','2026-11-20').inspectionPlans[0].actions.length,2);
});
