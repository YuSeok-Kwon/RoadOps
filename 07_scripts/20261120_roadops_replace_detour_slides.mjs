/** Two editable replacement slides, using actual verified before/after app captures. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {FileBlob,PresentationFile} from '/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const ROOT=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const BUILD=path.join(ROOT,'999_Temporary/roadops_detour_1213_20261120');
const OUT=path.join(ROOT,'02_outputs/ppt/RoadOps_12-13장_통제전후_교체용_20261120');
const CAPTURE=path.join(BUILD,'actual-screens');
const SOURCE=path.join(ROOT,'02_outputs/ppt/RoadOps_제주데이터활용_15장_20261120/RoadOps_공모전_기획서_15장_20261120_v2.pptx');
const FINAL=path.join(OUT,'RoadOps_12-13장_통제전후_검증_교체용_2장.pptx');
const CANDIDATE=path.join(BUILD,'replacement-candidate.pptx');
const SKILL='/Users/yu_seok/.codex/plugins/cache/openai-primary-runtime/presentations/26.1118.11504/skills/presentations';
const RUNTIME='/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const FONT='프리텐다드',BOLD='프리텐다드 Bold';
const C={ink:'#231F20',green:'#679773',highlight:'#A9BDAE',blue:'#1468B3',muted:'#7F8B95',line:'#DDE5DF',amber:'#A65D15'};
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
await fs.mkdir(OUT,{recursive:true});
const sourceHash=hash(await fs.readFile(SOURCE));
if(process.argv.includes('--finalize')){
 const manifest=JSON.parse(await fs.readFile(path.join(BUILD,'candidate-manifest.json'),'utf8'));
 assert.equal(manifest.candidateSha256,hash(await fs.readFile(CANDIDATE)));assert.equal(manifest.sourceSha256,sourceHash);
 process.env.RUNTIME_NODE_MODULES=path.join(RUNTIME,'node/node_modules');
 const {finalizePresentation}=await import(path.join(SKILL,'container_tools/artifact_tool_utils.mjs'));
 const receipt=await finalizePresentation({workspaceDir:ROOT,candidatePath:CANDIDATE,finalPath:FINAL,
  pythonExecutable:path.join(RUNTIME,'python/bin/python3'),integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
  explicitTotalSlideCount:2,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
  layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-heading-fit'],
  fontPolicy:{basis:'reference',families:[FONT,BOLD],referencePath:SOURCE,referenceSha256:sourceHash},
  verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
 const final=await PresentationFile.importPptx(await FileBlob.load(FINAL));
 for(let i=0;i<2;i++){const png=await final.export({slide:final.slides.getItem(i),format:'png',scale:1});await fs.writeFile(path.join(BUILD,`final-${12+i}.png`),new Uint8Array(await png.arrayBuffer()));}
 console.log(JSON.stringify({finalPath:receipt.finalPath,slideCount:receipt.firstPartyImport.slideCount,layoutPassed:receipt.presentationLayout.findingCount===0}));process.exit(0);
}
const evidence=JSON.parse(await fs.readFile(path.join(BUILD,'capture-evidence.json'),'utf8'));
const verified=JSON.parse(await fs.readFile(path.join(BUILD,'verified-result.json'),'utf8'));
const independent=JSON.parse(await fs.readFile(path.join(BUILD,'independent-verification.json'),'utf8'));
assert.equal(independent.status,'pass');assert.equal(independent.legs.length,4);
assert.deepEqual(evidence.visibleRoutePathsChanged,[false,false,true]);assert.equal(evidence.beforeView,evidence.afterView);
assert.equal(verified.comparison.beforeTotalMinutes,100.57);assert.equal(verified.totalMinutes,125.613);
for(const word of ['100.6분','125.6분','25.0분','5.6분 초과'])assert.ok(evidence.resultText.includes(word));
const p=await PresentationFile.importPptx(await FileBlob.load(SOURCE));
const layout=(await p.inspect({select:'$.slides[*]',include:['id','index','elements.id','elements.kind','elements.text','elements.position']})).records;
const chosen=['통제된 길을 피해 소길리로 가는 경로를 찾습니다','완료한 점검을 보존하고, 소길리도 방문합니다'].map(title=>layout.findIndex(s=>s.elements.some(e=>e.text===title)));
assert.ok(chosen.every(i=>i>=0));
for(const [i,idx] of chosen.entries()){
 const png=await p.export({slide:p.slides.getItem(idx),format:'png',scale:1});await fs.writeFile(path.join(BUILD,`reference-${12+i}.png`),new Uint8Array(await png.arrayBuffer()));
 const bg=layout[idx].elements.find(e=>e.kind==='image'&&e.position.left===0&&e.position.top===0&&e.position.width===1920&&e.position.height===1080);
 assert.ok(bg);for(const e of layout[idx].elements)if(e.id!==bg.id)p.delete(e.id);
}
p.slides.delete(layout.map((_,i)=>i).filter(i=>!chosen.includes(i)));assert.equal(p.slides.items.length,2);
function text(s,v,x,y,w,h,size=30,color=C.ink,bold=false){const a=s.shapes.add({geometry:'textbox',name:v.split('\n')[0],position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});a.text=v;a.text.insets=0;a.text.style={typeface:bold?BOLD:FONT,fontSize:size,color,bold};return a;}
function rect(s,x,y,w,h,fill){return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:'none',width:0}});}
async function shot(s,file,x,y,w,h,alt){s.images.add({blob:new Uint8Array(await fs.readFile(path.join(CAPTURE,file))),contentType:'image/png',alt,fit:'contain',position:{left:x,top:y,width:w,height:h}});}
function head(s,n,title,subtitle){rect(s,83,115,1535,38,C.highlight);text(s,title,96,78,1720,90,54,C.ink,true);text(s,subtitle,100,181,1710,78,30,C.muted);text(s,`${n} / 15`,1750,1020,150,35,22,C.muted);}
function note(s,body){s.speakerNotes.text=body+'\n\n시연 조건 및 산정 기준\n2026-11-19 17:40 저장 자료. 용담 2명, 가용 120분, 광령리 점검 완료 후 소길리와 예래동 방문 유지. 1100로 방향 링크 4050000302(약398m) 통제를 가정한 사례로 실제 현재 통제 정보가 아니다.\n완료 소요시간39.8분은 두 비교안에 동일하게 입력한 시연 가정이며 실측 기록이 아니다. 완료 구간의 경로와 기록은 보존한다. 남은 이동은 통제 전후 모두 같은 2026-10-14 표준노드링크와 제한속도 비용, 동일 방문순서, 각15분 점검 조건으로 재계산했다.\n통제 전:39.8+5.802+15+24.968+15=100.570분. 통제 후:39.8+5.802+15+50.011+15=125.613분. 추가25.043분, 120분 대비5.613분 초과.\n10장의 최초 저장 코스101.2분과 직접 비교하지 않는다. 이번 통제 전100.6분도 광령리 완료 시점에서 동일 비용으로 재계산한 비교 기준이다.\n신호대기·회전제한·실시간혼잡·거점복귀시간 미포함. 시간 초과를 승인한 출동계획이 아니라 세 곳을 모두 유지할 경우의 예상치를 제시하며 담당자가 시간 연장 또는 지원 여부를 판단한다.\n출처: '+path.join(BUILD,'capture-evidence.json')+'\n'+path.join(BUILD,'verified-result.json')+'\n'+path.join(BUILD,'independent-verification.json')+'\n'+path.join(ROOT,'08_dashboard/roadops_map_v0_1/src/content/assets/routing-network.json')+'\n지도 배경: © OpenStreetMap contributors';}
{
 const s=p.slides.getItem(0);
 head(s,12,'1100로 통제를 반영해 예래동 우회 경로를 찾습니다','광령리 점검을 마친 상황에서, 남은 소길리·예래동 방문을 유지하고 이동 경로를 다시 계산합니다.');
 text(s,'통제 전 · 같은 기준으로 재계산',110,282,820,52,34,C.green,true);
 text(s,'통제 후 · 1100로 통제 구간 제외',980,282,820,52,34,C.green,true);
 await shot(s,'01_before_map.png',110,350,820,470,'통제 전 실제 지도. 소길리에서 예래동으로 가는 경로가 통제 가정 구간을 통과한다.');
 await shot(s,'03_after_map.png',980,350,820,470,'통제 후 실제 지도. 같은 배율과 위치에서 서쪽으로 바뀐 우회 경로와 통제 구간을 확인한다.');
 text(s,'소길리에서 예래동까지 25.0분',110,837,820,52,34,C.ink,true);
 text(s,'소길리에서 예래동까지 50.0분',980,837,820,52,34,C.blue,true);
 text(s,'1100로를 지나는 이동 경로입니다.\n두 지도는 같은 범위와 배율로 비교합니다.',110,899,820,80,28);
 text(s,'통제 구간을 피해 서쪽 경로로 연결합니다.\n같은 곳을 방문해도 이동에 25.0분이 더 필요합니다.',980,899,820,80,28);
 text(s,'2026.11.19 저장 자료의 통제 가정 · 1100로 방향 구간 약 398m · 두 경로 모두 제한속도 기준 추정',100,1020,1600,35,19,C.muted);
 note(s,'통제 전후 실제 지도 두 장을 같은 범위와 배율로 비교한다. 완료한 광령리와 다음 소길리까지 경로는 같고, 소길리에서 예래동으로 향하는 마지막 이동 경로가 바뀐다.');
}
{
 const s=p.slides.getItem(1);
 head(s,13,'통제 후 5.6분 초과를 미리 확인합니다','광령리 점검 완료 시점에서, 남은 두 곳의 이동·점검 시간을 통제 전후 같은 기준으로 계산합니다.');
 text(s,'실제 재계산 결과',110,282,810,50,34,C.green,true);
 await shot(s,'04_after_course.png',110,350,795,545,'실제 통제 후 방문 유지 시 예상 코스. 광령리 완료, 소길리5.8분 이동, 예래동50.0분 이동, 총125.6분.');
 text(s,'완료 39.8분 + 남은 85.8분',110,915,820,49,34,C.green,true);
 text(s,'남은 이동 55.8분과 두 곳의 점검 30분을 합산합니다.',110,969,820,43,26);
 text(s,'세 곳을 모두 점검할 때의 총 예상시간',1020,282,790,50,33,C.green,true);
 text(s,'125.6분',1010,352,800,140,112,C.amber,true);
 text(s,'통제 전 100.6분보다 25.0분 증가',1020,510,790,55,34);
 text(s,'가용 120분보다 5.6분 초과 예상',1020,583,790,60,38,C.amber,true);
 rect(s,1020,676,780,1.5,C.line);
 text(s,'시간 연장·지원 필요를 사전에 판단',1020,716,790,60,37,C.ink,true);
 text(s,'남은 두 곳을 모두 점검하면 120분을 넘깁니다.\n담당자는 예상 초과 시간을 확인하고,\n근무시간 연장이나 다른 팀의 지원을 검토합니다.',1020,793,790,160,30);
 text(s,'완료 39.8분은 공통 시연 입력값 · 남은 이동은 같은 도로망·제한속도로 계산 · 실시간 혼잡·거점 복귀시간 미포함',100,1030,1610,31,18,C.muted);
 note(s,'통제로 이동시간이25.043분 늘어 총125.613분이 된다. 120분을 지킨다는 설명을 삭제하고, 모두 방문하려면5.613분 추가가 필요하다는 점과 담당자의 시간 연장·지원 판단을 설명한다. 초과를 미리 아는 것이 이 사례의 포인트다.');
}
for(let i=0;i<2;i++){const png=await p.export({slide:p.slides.getItem(i),format:'png',scale:1});await fs.writeFile(path.join(BUILD,`preview-${12+i}.png`),new Uint8Array(await png.arrayBuffer()));}
await (await PresentationFile.exportPptx(p)).save(CANDIDATE);
await fs.writeFile(path.join(BUILD,'candidate-manifest.json'),JSON.stringify({sourceSha256:sourceHash,candidateSha256:hash(await fs.readFile(CANDIDATE)),slideCount:2},null,2));
console.log(JSON.stringify({candidate:CANDIDATE,previews:[12,13].map(n=>path.join(BUILD,`preview-${n}.png`))}));
