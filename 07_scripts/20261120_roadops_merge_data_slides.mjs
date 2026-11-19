/** Create only the requested single-slide replacement for RoadOps slides 4–5.
 * Import the latest local deck as the design reference and preserve its background.
 * Run without flags for a preview; use --finalize only after visual review.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {FileBlob, PresentationFile} from '/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const RUNTIME = '/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const SKILL = '/Users/yu_seok/.codex/plugins/cache/openai-primary-runtime/presentations/26.1118.11504/skills/presentations';
const PREVIOUS = path.join(ROOT, '02_outputs/ppt/RoadOps_제주데이터활용_15장_20261120');
const SOURCE = path.join(PREVIOUS, 'RoadOps_공모전_기획서_15장_20261120_v2.pptx');
const SCREENSHOT = path.join(PREVIOUS, '실제화면/01_노면통계와_점검계획.png');
const BUILD = path.join(ROOT, '999_Temporary/roadops_merge_data_20261120');
const OUT = path.join(ROOT, '02_outputs/ppt/RoadOps_4-5장_통합_교체용_20261120');
const FINAL = path.join(OUT, 'RoadOps_4-5장_통합_교체용_1장.pptx');
const PREVIEW = path.join(OUT, 'RoadOps_4-5장_통합_미리보기.png');
const FONT = '프리텐다드';
const BOLD = '프리텐다드 Bold';
const C = {ink:'#231F20',green:'#679773',highlight:'#A9BDAE',muted:'#7F8B95',line:'#DDE5DF',light:'#F0F5F0'};

await fs.mkdir(BUILD, {recursive:true});
await fs.mkdir(OUT, {recursive:true});
const sourceHash = crypto.createHash('sha256').update(await fs.readFile(SOURCE)).digest('hex');
const p = await PresentationFile.importPptx(await FileBlob.load(SOURCE));
const query = {select:'$.slides[*]',include:['index','id','elements.id','elements.kind','elements.text','elements.position']};
const before = (await p.inspect(query)).records;
if (before.length !== 15) throw Error('Expected the latest 15-slide reference deck');
const originalSlide = before[3];
const background = originalSlide.elements.find(e => e.kind === 'image' && e.position.left === 0 && e.position.top === 0 && e.position.width === 1920 && e.position.height === 1080);
if (!background) throw Error('Cannot identify the original full-slide background');
for (const element of originalSlide.elements) {
  if (element.id !== background.id) p.delete(element.id);
}
// Retain only slide 4. Do not build or export the declined full-deck revision.
p.slides.delete(before.map((_, i) => i).filter(i => i !== 3));
if (p.slides.items.length !== 1) throw Error('The requested deliverable must have exactly one slide');
const s = p.slides.getItem(0);

function text(value, x, y, width, height, size=29, color=C.ink, bold=false) {
  const shape = s.shapes.add({geometry:'textbox',name:value.split('\n')[0],position:{left:x,top:y,width,height},fill:'none',line:{fill:'none',width:0}});
  shape.text = value;
  shape.text.insets = 0;
  shape.text.style = {typeface:bold ? BOLD : FONT,fontSize:size,color,bold};
  return shape;
}
function rect(x,y,width,height,fill) {
  return s.shapes.add({geometry:'rect',position:{left:x,top:y,width,height},fill,line:{fill:'none',width:0}});
}

rect(83,115,1710,38,C.highlight);
text('제주 데이터를 확인하고, 도로별 점검 항목을 준비합니다',96,78,1720,90,54,C.ink,true);
text('노면별 사고통계와 사고·재해 이력을 살펴, 현장에서 확인할 내용을 점검계획에 담습니다.',100,181,1710,75,30,C.muted);

text('노면 조건을 선택하고 점검계획에 반영',110,285,990,50,32,C.green,true);
s.images.add({blob:new Uint8Array(await fs.readFile(SCREENSHOT)),contentType:'image/png',alt:'실제 RoadOps 화면: 젖음/습기 통계 확인 후 배수·미끄럼 점검 항목 2개를 점검계획에 반영',fit:'contain',position:{left:110,top:339,width:960,height:664}});

text('노면별 사고통계',1170,285,640,48,34,C.green,true);
text('선택한 노면의 과거 사고 규모를 확인합니다.\n노면 유형별 규칙으로 점검 항목을 제안합니다.',1170,341,640,83,28);
rect(1170,434,630,1,C.line);

text('TAAS + 허브 사고다발지역',1170,459,640,48,34,C.green,true);
text('사고가 집중된 지점을 지도에서 확인하고,\n주변 도로 점검의 참고 근거로 활용합니다.',1170,515,640,83,28);
rect(1170,608,630,1,C.line);

text('붕괴위험·자연재해 지구',1170,633,640,48,34,C.green,true);
text('같은 행정지역의 재해 유형·관리 상태를 보고,\n사면·낙석, 배수·침수 점검을 보완합니다.',1170,689,640,83,28);

rect(1170,804,630,190,C.light);
text('‘젖음/습기’ 선택 시 제안하는 점검',1198,823,575,45,29,C.green,true);
text('물고임·배수구 막힘 확인\n미끄럼 방지시설과 노면 상태 확인',1198,873,575,76,28);
text('선택한 도로의 점검계획에 반영',1198,955,575,38,27,C.ink,true);

// Keep the source deck's page identity, without assuming the user's current total.
text('04',1750,1013,150,35,22,C.muted);
text('과거 통계와 행정지역 자료를 참고하며, 실제 노면 상태와 재해지구의 정확한 위치는 담당자가 확인합니다.',110,1017,1600,35,18,C.muted);

s.speakerNotes.text = [
  '기존 4장과 5장을 합친 교체용 한 장. 전체 기획서 수정본은 생성하지 않는다. 기존 배경·색상·글꼴을 유지하고 실제 화면 하나와 데이터별 활용 설명을 배치했다.',
  '노면 통계는 제주 지역의 2005–2020년 과거 집계이며 특정 도로의 현재 상태나 사고 발생확률이 아니다. 젖음/습기 7,218건, 사망자 226명은 선택 기간 합계다. 점검 항목은 선택한 노면 유형에 연결된 규칙으로 제안한다. 통계 수치로 인과관계를 추론하거나 도로별 위험률을 산출하지 않는다.',
  'TAAS 최신 자료와 제주데이터허브 과거 사고다발지역 자료는 분석연도별 지점 조회와 지도 확인에 사용한다. 서로 다른 연도의 건수를 합산하거나 오래된 자료를 현재 우선순위 점수에 임의로 가산하지 않는다.',
  '붕괴위험급경사지·자연재해위험개선지구는 정확한 좌표와 경계가 없어 같은 행정지역의 참고자료로만 사용한다. 지정 해제와 정비 완료를 구분하며, 위치·현장 확인 대상 자료에 한해 점검 항목을 보완한다. 해당 도로가 실제 재해지구 안에 있다고 단정하거나 자동 통제하지 않는다.',
  '왼쪽은 2026.11.20 실제 기능 화면이다. 버튼 실행 후 점검 항목 두 개가 추천 순찰코스와 확인 기록에 반영된 검증 화면을 그대로 사용했다.',
  '출처 및 검증 근거',
  'https://jejudatahub.net/data/view/data/891',
  'https://jejudatahub.net/data/view/data/863',
  'https://jejudatahub.net/data/view/data/436',
  'https://jejudatahub.net/data/view/data/435',
  'https://www.data.go.kr/data/15056032/fileData.do',
  'https://www.data.go.kr/data/15056033/fileData.do',
  path.join(PREVIOUS,'실제화면/capture-evidence.json'),
  path.join(ROOT,'04_docs/deployment/20261120_roadops_jeju_inspection_evidence.md')
].join('\n\n');

const after = (await p.inspect(query)).records;
await fs.writeFile(path.join(BUILD,'layout.json'),JSON.stringify(after,null,2));
const rendered = await p.export({slide:s,format:'png',scale:1});
await fs.writeFile(path.join(BUILD,'preview.png'),new Uint8Array(await rendered.arrayBuffer()));
const candidate = path.join(BUILD,'merged-slide-candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
if (crypto.createHash('sha256').update(await fs.readFile(SOURCE)).digest('hex') !== sourceHash) throw Error('Reference deck changed');
if (process.argv.includes('--finalize')) {
  process.env.RUNTIME_NODE_MODULES = path.join(RUNTIME,'node/node_modules');
  const {finalizePresentation} = await import(path.join(SKILL,'container_tools/artifact_tool_utils.mjs'));
  const receipt = await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:FINAL,pythonExecutable:path.join(RUNTIME,'python/bin/python3'),integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),explicitTotalSlideCount:1,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-heading-fit'],fontPolicy:{basis:'reference',families:[FONT,BOLD],referencePath:SOURCE,referenceSha256:sourceHash},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
  await fs.copyFile(path.join(BUILD,'preview.png'),PREVIEW);
  console.log(JSON.stringify({finalPath:receipt.finalPath,preview:PREVIEW,slideCount:receipt.firstPartyImport.slideCount,layoutPassed:receipt.presentationLayout.findingCount===0}));
} else {
  console.log(JSON.stringify({candidate,preview:path.join(BUILD,'preview.png'),slideCount:1,sourceUnchanged:true}));
}
