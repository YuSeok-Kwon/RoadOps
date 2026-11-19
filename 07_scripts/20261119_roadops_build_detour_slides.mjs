/** Build editable replacements for RoadOps slides 14–15 from actual UI captures.
 * Requires screenshots and capture-evidence.json in the output screenshot folder.
 * Run without flags to render a review candidate; add --finalize after visual review.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {FileBlob, PresentationFile} from '/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const OUT = path.join(ROOT, '02_outputs/ppt/RoadOps_14-15장_우회경로');
const SHOTS = path.join(OUT, '스크린샷');
const BUILD = path.join(ROOT, '999_Temporary/roadops_detour_slides_1415');
const SOURCE = path.join(ROOT, '02_outputs/ppt/RoadOps_15-16장_수정본/RoadOps_15-16장_수정본_편집가능.pptx');
const SKILL = '/Users/yu_seok/.codex/plugins/cache/openai-primary-runtime/presentations/26.1118.11504/skills/presentations';
const RUNTIME = '/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const FONT = '프리텐다드', BOLD = '프리텐다드 Bold';
const C = {ink:'#231F20', green:'#679773', highlight:'#A9BDAE', blue:'#1468B3', muted:'#7F8B95', line:'#DDE5DF', white:'#FFFFFF'};
await fs.mkdir(BUILD, {recursive:true});
const evidence = JSON.parse(await fs.readFile(path.join(SHOTS, 'capture-evidence.json'), 'utf8'));
for (const expected of ['완료 1곳 유지', '남은 방문 2곳', '보류 0곳', '39.8분', '60.8분', '총 100.6분', '19.4분 여유']) {
  if (!evidence.resultText.includes(expected)) throw new Error(`Capture does not support slide claim: ${expected}`);
}
if (evidence.scenario.budgetMinutes !== 120 || evidence.scenario.completedStops !== 1 ||
    evidence.scenario.closedLinkIds.join(',') !== '4050430101') throw new Error('Unexpected capture scenario');

const p = await PresentationFile.importPptx(await FileBlob.load(SOURCE));
if (p.slides.items.length !== 2) throw new Error('Expected the two-slide reference deck');
const before = await p.inspect({select:'$.slides[*]', include:['id','index','elements.id']});
for (const row of before.records) for (const element of row.elements) p.delete(element.id);

function text(s, value, x, y, w, h, size=34, color=C.ink, bold=false) {
  const shape = s.shapes.add({geometry:'textbox', name:value.split('\n')[0],
    position:{left:x, top:y, width:w, height:h}, fill:'none', line:{fill:'none',width:0}});
  shape.text = value;
  shape.text.insets = 0;
  shape.text.style = {typeface:bold ? BOLD : FONT, fontSize:size, color, bold};
  return shape;
}
function rect(s, x, y, w, h, fill) {
  return s.shapes.add({geometry:'rect', position:{left:x,top:y,width:w,height:h}, fill, line:{fill:'none',width:0}});
}
async function image(s, file, x, y, w, h, alt) {
  const bytes = new Uint8Array(await fs.readFile(file));
  return s.images.add({blob:bytes, contentType:'image/png', fit:'contain',
    alt:alt || path.basename(file), position:{left:x,top:y,width:w,height:h}});
}
async function head(index, title, subtitle) {
  const s = p.slides.getItem(index);
  s.background.fill = C.white;
  await image(s, path.join(ROOT, '999_Temporary/roadops_workflow_v04/source-media/image3.png'),
    0,0,1920,1080,'원본 발표 자료의 공통 도로선 배경');
  rect(s,83,115,1660,38,C.highlight);
  text(s,title,96,77,1720,91,60,C.ink,true);
  text(s,subtitle,99,178,1710,76,31,C.muted);
  text(s,`${14+index} / 16`,1750,1010,150,36,22,C.muted);
  return s;
}
function note(s, description) {
  s.speakerNotes.text = description + '\n\n실제 화면 근거\n' + SHOTS + '\n' +
    '입력: 2026-11-19 17:40 저장 자료, 용담팀 2명/120분, 광령리까지 완료, 통제 링크 4050430101.\n' +
    '실제 운영 통제가 아닌 재현 시나리오. 화면은 실행 중인 RoadOps UI에서 직접 캡처했다.\n' +
    '완료 기록 39.793분 + 남은 이동·점검 60.770분 = 전체 100.563분. 여유 19.437분.\n' +
    '광령리→소길리 이동 5.802분, 점검 15분. 소길리→예래동 이동 24.968분, 점검 15분.\n' +
    '새 경로 시간은 도로 링크의 제한속도로 추정한다. 실시간 혼잡과 회전 제한은 반영하지 않는다.\n' +
    '기존 101.2분과 새 100.6분은 산정 조건이 달라 효율 개선 실적으로 비교하지 않는다.\n' +
    '소스: 대체 경로 기능 커밋 b46958d, capture-evidence.json.';
}

{
  const s = await head(0,'통제된 길을 피해 소길리로 가는 경로를 찾습니다',
    '광령리 점검을 마친 뒤, 통제 구간을 제외하고 남은 이동 경로를 다시 계산합니다.');
  text(s,'통제 구간을 제외한 새 이동 경로',110,280,1060,55,35,C.green,true);
  await image(s,path.join(SHOTS,'01_우회경로_지도.png'),110,354,1080,638,
    '실제 RoadOps 지도: 용담 출발, 광령리 완료, 소길리와 예래동으로 이어지는 재계산 경로');
  text(s,'통제 조건 입력',1250,280,560,55,35,C.green,true);
  await image(s,path.join(SHOTS,'02_통제조건_자동계산.png'),1250,358,550,459,
    '통제 링크 4050430101과 광령리까지 완료를 지정하고 대체 경로 자동 계산을 실행한 실제 입력 화면');
  text(s,'완료한 광령리 기록은 유지하고,',1250,860,560,49,31,C.ink);
  text(s,'소길리와 예래동을 방문합니다.',1250,912,560,57,34,C.green,true);
  text(s,'17:40 저장 자료로 재현한 통제 가정 · 실제 RoadOps 계산 화면',99,1020,1600,34,18,C.muted);
  note(s,'14장: 통제 조건을 입력하면 저장된 도로망에서 통제 링크를 제외한 경로를 자동으로 탐색한다. 지도와 입력 화면은 동일한 실행 결과다. 지도상 통제 링크가 매우 짧으므로 위치를 확대·왜곡하거나 가상의 우회선을 추가하지 않았다.');
}
{
  const s = await head(1,'소길리를 포함한 세 곳의 점검 계획을 유지합니다',
    '완료한 광령리 점검을 보존하고, 소길리와 예래동을 방문하는 변경안을 제안합니다.');
  text(s,'완료 기록과 새 방문 순서',110,280,820,55,35,C.green,true);
  await image(s,path.join(SHOTS,'05_방문순서와_변경안확정.png'),110,350,780,638,
    '실제 통제 반영 순찰코스: 광령리 완료, 소길리 5.8분 이동, 예래동 25분 이동, 총 100.6분');
  text(s,'총 예상 소요시간',1040,292,760,55,35,C.green,true);
  text(s,'100.6분',1034,350,780,153,118,C.blue,true);
  text(s,'완료 39.8분 + 남은 60.8분',1045,526,755,58,37,C.ink);
  rect(s,1045,610,750,1.5,C.line);
  text(s,'가용 120분 중',1045,646,750,50,31,C.muted);
  text(s,'19.4분 여유',1040,699,760,93,65,C.green,true);
  text(s,'담당자 확인 후 변경안 확정',1045,839,750,60,39,C.ink,true);
  text(s,'통제·기상과 실제 통행 가능 여부를\n확인한 뒤 실행합니다.',1045,912,755,85,29,C.muted);
  text(s,'새 경로는 제한속도 기반 추정 · 실시간 혼잡과 회전 제한 미반영',99,1020,1600,34,18,C.muted);
  note(s,'15장: 완료 1곳, 남은 방문 2곳, 보류 0곳이다. 총 100.6분은 이미 완료한 광령리의 시간도 포함한다. 남은 시간만을 전체 시간으로 오해하지 않도록 완료/남은 시간을 나눠 표기했다. 방문 순찰코스는 실제 화면이며 제목과 요약 수치는 편집 가능한 PowerPoint 텍스트다.');
}

for (let i=0;i<2;i++) {
  const png = await p.export({slide:p.slides.getItem(i),format:'png',scale:1});
  await fs.writeFile(path.join(BUILD,`slide-${14+i}.png`),new Uint8Array(await png.arrayBuffer()));
}
const candidate = path.join(BUILD,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
await fs.writeFile(path.join(BUILD,'inspection.json'),JSON.stringify((await p.inspect({select:'$.slides[*]',include:['index','elements.text','elements.position']})).records,null,2));
console.log(JSON.stringify({candidate,previews:BUILD}));
if (process.argv.includes('--finalize')) {
  process.env.RUNTIME_NODE_MODULES = path.join(RUNTIME,'node/node_modules');
  const {finalizePresentation} = await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
  const receipt = await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,
    finalPath:path.join(OUT,'RoadOps_14-15장_우회경로_교체용.pptx'),
    pythonExecutable:path.join(RUNTIME,'python/bin/python3'),
    integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),
    layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
    explicitTotalSlideCount:2,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
    layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-heading-fit'],
    fontPolicy:{basis:'reference',families:[FONT,BOLD],referencePath:SOURCE,
      referenceSha256:crypto.createHash('sha256').update(await fs.readFile(SOURCE)).digest('hex')},
    verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
  console.log(JSON.stringify(receipt));
}
