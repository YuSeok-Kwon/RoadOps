import test from 'node:test';
import assert from 'node:assert/strict';
import { inferSurface, resolveSurfaceSelection, surfaceContextKey, makeSurfaceOverride } from '../src/content/dashboard/surface-weather.js';
import { makeInspectionPlan } from '../src/content/dashboard/jeju-inspection.js';
import { createWorkflowState, createApprovalRecord } from '../src/content/dashboard/workflow-policy.js';
const now = new Date('2026-11-20T01:30:00+09:00');
const weather = {team_id:'north', status:'usable', horizon_hours:0, evidence_kind:'observation', generated_at:'2026-11-20T01:20:00+09:00', valid_at:'2026-11-20T01:00:00+09:00', target_at:'2026-11-20T01:00:00+09:00', temperature_c:5, precipitation_type:1, rainfall_raw:'1', humidity_percent:90, source_url:'https://www.data.go.kr/data/15084084/openapi.do'};
const infer = patch => inferSurface({...weather, ...patch}, now).surface;

test('rain, snow, freezing and dry suggestions use actual inputs', () => {
  assert.equal(infer({}), '젖음/습기');
  assert.equal(infer({temperature_c:0}), '서리/결빙');
  for (const pty of [3,7]) assert.equal(infer({precipitation_type:pty}), '적설');
  for (const pty of [2,6]) {
    assert.equal(infer({precipitation_type:pty,temperature_c:-1}), '적설');
    assert.equal(infer({precipitation_type:pty,temperature_c:1}), '젖음/습기');
  }
  assert.equal(infer({precipitation_type:0,rainfall_raw:'0',temperature_c:-1,humidity_percent:90}), '서리/결빙');
  assert.equal(infer({precipitation_type:0,rainfall_raw:'강수없음'}), '건조');
  assert.equal(infer({precipitation_type:0,rainfall_raw:'1.0mm 미만'}), '젖음/습기');
});

test('missing, invalid and stale weather never imply dry conditions', () => {
  for (const patch of [{status:'unavailable'}, {temperature_c:null}, {temperature_c:''}, {precipitation_type:''}, {precipitation_type:9},
    {generated_at:null}, {valid_at:null}, {generated_at:'2026-11-19T20:00:00+09:00'}, {valid_at:'2026-11-19T23:00:00+09:00'},
    {precipitation_type:0,rainfall_raw:''}, {precipitation_type:0,temperature_c:-1,rainfall_raw:'0',humidity_percent:null}]) {
    assert.equal(infer(patch), '', JSON.stringify(patch));
  }
  assert.equal(inferSurface(null, now).surface,'');
});

test('future weather must be forecast for the requested horizon', () => {
  assert.equal(infer({horizon_hours:3}), '');
  assert.equal(infer({horizon_hours:3,evidence_kind:'forecast',target_at:'2026-11-20T04:00:00+09:00',valid_at:'2026-11-20T04:00:00+09:00'}), '젖음/습기');
  assert.equal(infer({evidence_kind:'forecast',valid_at:'2026-11-20T04:00:00+09:00'}), '');
});

test('manual overrides survive new weather, unknown weather and session serialization; reset uses latest recommendation', () => {
  const auto = inferSurface(weather,now);
  const override = JSON.parse(JSON.stringify(makeSurfaceOverride('해빙',auto,now)));
  const dry = inferSurface({...weather,precipitation_type:0,rainfall_raw:0},now);
  assert.equal(resolveSurfaceSelection(dry,override).surface,'해빙');
  assert.equal(resolveSurfaceSelection(inferSurface(null,now),override).surface,'해빙');
  assert.equal(resolveSurfaceSelection(dry,null).surface,'건조');
  assert.equal(resolveSurfaceSelection(dry,makeSurfaceOverride('',auto,now)).surface,'');
  assert.notEqual(surfaceContextKey('north',1,0),surfaceContextKey('west',1,0));
  assert.notEqual(surfaceContextKey('north',1,0),surfaceContextKey('north',2,0));
  assert.notEqual(surfaceContextKey('north',1,0),surfaceContextKey('north',1,3));
  assert.equal(override.basis.weather.precipitation_type,1);
});

test('weather provenance and manual decision reach approval without changing score or closure', () => {
  const auto = inferSurface(weather,now);
  const selection = resolveSurfaceSelection(auto,makeSurfaceOverride('적설',auto,now));
  const plan = makeInspectionPlan({task:{link_id:'1'},surface:selection.surface,surfaceSelection:selection,surfaceRows:[{year:2020,surface:'적설',accident_count:2,fatality_count:0,injury_count:2}],hazards:[]});
  const state = createWorkflowState({tasks:[{task_id:'t',link_id:'1',inspection_plan:plan}]});
  const saved = createApprovalRecord(state,'none',now.toISOString()).inspectionPlans[0];
  assert.deepEqual(saved.surfaceSelection,selection);
  assert(saved.actions.some(a=>a.includes('적설')));
  assert(saved.sourceUrls.includes(weather.source_url));
  assert.equal(saved.scoreAdjustment,0); assert.equal(saved.automaticClosure,false);
});
