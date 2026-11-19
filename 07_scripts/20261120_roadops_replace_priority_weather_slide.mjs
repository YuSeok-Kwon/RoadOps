/** Single replacement for Canva slide 7, preserving the RoadOps reference design.
 * --capture: capture the running app without changing DOM, styles, or data.
 * Default: render a review candidate. --finalize: validate the reviewed candidate.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {FileBlob, PresentationFile} from '/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const RUNTIME = '/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const SKILL = '/Users/yu_seok/.codex/plugins/cache/openai-primary-runtime/presentations/26.1118.11504/skills/presentations';
const SOURCE = path.join(ROOT, '02_outputs/ppt/RoadOps_제주데이터활용_15장_20261120/RoadOps_공모전_기획서_15장_20261120_v2.pptx');
const BUILD = path.join(ROOT, '999_Temporary/roadops_slide7_20261120');
const OUT = path.join(ROOT, '02_outputs/ppt/RoadOps_7장_교체용_20261120');
const CAPTURE = path.join(OUT, '실제화면');
const FINAL = path.join(OUT, 'RoadOps_7장_우선순위와_시간별예보_교체용_1장.pptx');
const PREVIEW = path.join(OUT, 'RoadOps_7장_미리보기.png');
const CANDIDATE = path.join(BUILD, 'replacement-candidate.pptx');
const FONT = '프리텐다드';
const BOLD = '프리텐다드 Bold';
const C = {ink:'#231F20',green:'#679773',highlight:'#A9BDAE',muted:'#7F8B95',line:'#DDE5DF',light:'#F0F5F0'};

await fs.mkdir(BUILD, {recursive:true});
await fs.mkdir(CAPTURE, {recursive:true});
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const sourceHash = sha256(await fs.readFile(SOURCE));

async function captureApp() {
  const {chromium} = await import(path.join(RUNTIME, 'node/node_modules/playwright/index.mjs'));
  const browser = await chromium.launch({headless:true,executablePath:'/Users/yu_seok/Library/Caches/ms-playwright/chromium-1148/chrome-mac/Chromium.app/Contents/MacOS/Chromium'});
  try {
    const page = await browser.newPage({viewport:{width:1600,height:1200},deviceScaleFactor:4});
    await page.goto('http://127.0.0.1:5173/', {waitUntil:'networkidle'});
    await page.getByRole('button',{name:'화이트',exact:true}).click();
    await page.getByRole('button',{name:'날씨뷰',exact:true}).click();
    const timeline = page.locator('.weather-timeline-list');
    await timeline.waitFor();
    await page.evaluate(() => document.fonts.ready);
    const evidence = {
      capturedAt:new Date().toISOString(),url:page.url(),
      method:'Unmodified actual app DOM; element screenshots and rectangular crops only.',
      weatherSummary:await page.locator('.weather-view-summary').innerText(),
      weatherTimeline:await page.locator('.weather-timeline').innerText(),
      timelineBox:await timeline.boundingBox(),
      rows:await timeline.locator('button').allTextContents(),
      textWidths:await timeline.locator('button small').evaluateAll(es => es.map(e => ({text:e.innerText,width:e.clientWidth,scroll:e.scrollWidth}))),
      criteria:[]
    };
    if (evidence.rows.length !== 4) throw Error('Expected current / 1 / 3 / 6 hour rows');
    if (evidence.textWidths.some(e => e.scroll > e.width)) throw Error('Forecast text is clipped');
    await timeline.screenshot({path:path.join(CAPTURE,'01_현재_1_3_6시간_실제예보.png')});
    await page.locator('.operation-weather-view').screenshot({path:path.join(BUILD,'weather-full-context.png')});

    // Compact existing controls without inventing a new screen: crop each actual
    // criterion's label and numeric input, then arrange the eight crops on the slide.
    await page.setViewportSize({width:1200,height:1200});
    await page.getByRole('button',{name:'점수 기준·배점 설정',exact:true}).click();
    const criteria = page.locator('.scoring-policy-criterion');
    if (await criteria.count() !== 8) throw Error('Expected eight priority criteria');
    for (let i=0; i<8; i++) {
      const criterion = criteria.nth(i);
      await criterion.scrollIntoViewIfNeeded();
      const a = await criterion.locator(':scope > label').nth(0).boundingBox();
      const b = await criterion.locator(':scope > label').nth(1).boundingBox();
      const left = Math.min(a.x,b.x)-7;
      const input = await criterion.locator('input[type=number]').boundingBox();
      const top = input.y+input.height/2-22;
      const right = Math.max(a.x+a.width,b.x+b.width)+7;
      const clip = {x:left,y:top,width:right-left,height:44};
      const filename = `02_배점_${String(i+1).padStart(2,'0')}.png`;
      await page.screenshot({path:path.join(CAPTURE,filename),clip});
      evidence.criteria.push({filename,clip,text:await criterion.innerText(),weight:await criterion.locator('input[type=number]').inputValue()});
    }
    await fs.writeFile(path.join(CAPTURE,'capture-evidence.json'),JSON.stringify(evidence,null,2));
    console.log(JSON.stringify({captured:CAPTURE,forecastRows:evidence.rows,criteria:evidence.criteria.map(e=>({name:e.text.split('\n')[0],weight:e.weight,clip:e.clip}))}));
  } finally {
    await browser.close();
  }
}

if (process.argv.includes('--capture')) {
  await captureApp();
  process.exit(0);
}

if (process.argv.includes('--finalize')) {
  // Finalize the exact candidate already rendered and reviewed, without recapture.
  const manifest = JSON.parse(await fs.readFile(path.join(BUILD,'candidate-manifest.json'),'utf8'));
  if (manifest.sourceSha256 !== sourceHash) throw Error('Reference changed since review');
  if (manifest.candidateSha256 !== sha256(await fs.readFile(CANDIDATE))) throw Error('Candidate changed since review');
  process.env.RUNTIME_NODE_MODULES = path.join(RUNTIME,'node/node_modules');
  const {finalizePresentation} = await import(path.join(SKILL,'container_tools/artifact_tool_utils.mjs'));
  const receipt = await finalizePresentation({workspaceDir:ROOT,candidatePath:CANDIDATE,finalPath:FINAL,pythonExecutable:path.join(RUNTIME,'python/bin/python3'),integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),explicitTotalSlideCount:1,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-heading-fit'],fontPolicy:{basis:'reference',families:[FONT,BOLD],referencePath:SOURCE,referenceSha256:sourceHash},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
  const finalDeck = await PresentationFile.importPptx(await FileBlob.load(FINAL));
  const image = await finalDeck.export({slide:finalDeck.slides.getItem(0),format:'png',scale:1});
  await fs.writeFile(PREVIEW,new Uint8Array(await image.arrayBuffer()));
  console.log(JSON.stringify({finalPath:receipt.finalPath,preview:PREVIEW,slideCount:receipt.firstPartyImport.slideCount,layoutPassed:receipt.presentationLayout.findingCount===0}));
  process.exit(0);
}

const evidence = JSON.parse(await fs.readFile(path.join(CAPTURE,'capture-evidence.json'),'utf8'));
const p = await PresentationFile.importPptx(await FileBlob.load(SOURCE));
const query = {select:'$.slides[*]',include:['index','id','elements.id','elements.kind','elements.text','elements.position']};
const before = (await p.inspect(query)).records;
if (before.length !== 15) throw Error('Expected the 15-slide reference');
const sourceIndex = before.findIndex(slide => slide.elements.some(e => e.text?.includes('판단 기준을 고르고, 기상 변화를 확인합니다')));
if (sourceIndex < 0) throw Error('Cannot identify priority/weather source slide');
const sourceSlide = before[sourceIndex];
const original = await p.export({slide:p.slides.getItem(sourceIndex),format:'png',scale:1});
await fs.writeFile(path.join(BUILD,'source-slide.png'),new Uint8Array(await original.arrayBuffer()));
const background = sourceSlide.elements.find(e => e.kind==='image' && e.position.left===0 && e.position.top===0 && e.position.width===1920 && e.position.height===1080);
if (!background) throw Error('Cannot identify original background');
for (const e of sourceSlide.elements) if (e.id !== background.id) p.delete(e.id);
p.slides.delete(before.map((_,i)=>i).filter(i=>i!==sourceIndex));
if (p.slides.items.length !== 1) throw Error('Replacement must contain exactly one slide');
const s = p.slides.getItem(0);

function text(value,x,y,width,height,size=29,color=C.ink,bold=false) {
  const shape=s.shapes.add({geometry:'textbox',name:value.split('\n')[0],position:{left:x,top:y,width,height},fill:'none',line:{fill:'none',width:0}});
  shape.text=value;
  shape.text.insets=0;
  shape.text.style={typeface:bold?BOLD:FONT,fontSize:size,color,bold};
  return shape;
}
function rect(x,y,width,height,fill) {
  return s.shapes.add({geometry:'rect',position:{left:x,top:y,width,height},fill,line:{fill:'none',width:0}});
}
async function screenshot(file,x,y,width,height,alt) {
  s.images.add({blob:new Uint8Array(await fs.readFile(path.join(CAPTURE,file))),contentType:'image/png',alt,fit:'contain',position:{left:x,top:y,width,height}});
}

rect(83,115,1530,38,C.highlight);
text('어느 도로를 먼저 점검할지 기준을 정합니다',96,78,1710,90,54,C.ink,true);
text('담당자가 판단 항목과 배점을 조정하고, 현재와 이후의 기상 조건을 함께 검토합니다.',100,181,1710,75,30,C.muted);

text('담당자가 정하는 8개 항목과 배점',110,285,900,48,34,C.green,true);
text('운영 목적에 맞춰 항목을 선택하고, 같은 기준으로 비교',110,337,900,43,27);

for (let i=0;i<8;i++) {
  const row = Math.floor(i/2);
  const col = i%2;
  await screenshot(evidence.criteria[i].filename,110+col*445,400+row*79,420,70,`실제 점수 설정 화면: ${evidence.criteria[i].text.split('\n')[0]} ${evidence.criteria[i].weight}점`);
}
text('계산 결과의 근거까지 확인',110,749,880,45,31,C.green,true);
text('같은 기준을 수동 검토와 자동 계획에 적용합니다.\n점수 근거와 자료 부족을 함께 확인하고,\n담당자가 적용할 배점을 최종 결정합니다.',110,802,880,116,29);
text('화면의 배점은 운영 시나리오 예시이며 조정할 수 있습니다.',110,919,900,30,20,C.muted);

text('현재·1시간·3시간·6시간 후 예보',1055,285,770,48,34,C.green,true);
text('기온·강수·바람을 비교해 출동 시점 검토',1055,337,770,43,27);
const weatherWidth=500;
const weatherHeight=weatherWidth*evidence.timelineBox.height/evidence.timelineBox.width;
await screenshot('01_현재_1_3_6시간_실제예보.png',1140,389,weatherWidth,weatherHeight,'실제 RoadOps 시간대별 기상: 현재와 1·3·6시간 후 기온, 강수량, 최대풍속');
text(`기상청 · ${evidence.weatherSummary.split('\n')[1]} · 제주 전역 격자 종합`,1055,919,770,30,20,C.muted);

rect(110,968,1690,52,C.light);
text('예보가 달라지면 점검 대상을 재검토하고, 이동·작업시간을 반영해 방문 순서를 정합니다.',130,978,1650,40,29,C.green,true);
text('07 / 15',1750,1030,150,34,22,C.muted);

s.speakerNotes.text=[
  '사용자가 Canva에서 교체할 7장 한 장만 제작. 기준 원본의 배경, 초록 강조선, 프리텐다드 글꼴과 좌우 구성을 유지했다. 원본 PPTX에서 이 내용은 8장이지만, 사용자의 최신 순서에 맞춰 07 / 15로 표기했다.',
  '5장은 거점 날씨를 참고한 예상 노면과 도로별 점검 항목, 7장은 담당자가 설정하는 우선순위 기준과 시간대별 기상 비교를 설명한다. 오른쪽 화면은 거점 한 곳의 관측값이 아니라 제주 전역 격자를 종합한 범위다.',
  '오른쪽은 실행 중인 실제 앱의 시간대별 기상 목록을 그대로 캡처했다. 지도와 불필요한 여백은 제외했다. 왼쪽은 동일 앱의 8개 배점 컨트롤을 각각 캡처해 2열로 배치했다. DOM, CSS, 수치, 문구를 바꾸지 않았다.',
  '배점 설정은 담당자의 권한이며 LLM이 임의 변경하지 않는다. 우선순위 점수는 최종 방문 순서와 구분한다. 가용시간, 필수 대상, 이동시간과 점검 작업시간 등을 함께 검토한다. 예보 변경에 따른 재검토는 사용자의 검토 절차를 뜻하며 자동 확정을 주장하지 않는다.',
  '배점의 초기값은 운영 시나리오용이다. 사고 발생확률, 사고 감소 성과, 기상 예측 정확도를 의미하지 않는다.',
  `캡처 시각: ${evidence.capturedAt}`,
  `실제 화면의 기상 요약:\n${evidence.weatherSummary}`,
  `실제 화면의 시간대별 예보:\n${evidence.weatherTimeline}`,
  '출처: RoadOps 실행 화면, 기상청 초단기예보 연동 자료.',
  path.join(CAPTURE,'capture-evidence.json'),
  path.join(ROOT,'08_dashboard/roadops_map_v0_1/src/content/dashboard/DashboardContent.jsx'),
  path.join(ROOT,'08_dashboard/roadops_map_v0_1/src/content/dashboard/ScoringPolicyPanel.jsx')
].join('\n\n');

await fs.writeFile(path.join(BUILD,'layout.json'),JSON.stringify((await p.inspect(query)).records,null,2));
const rendered=await p.export({slide:s,format:'png',scale:1});
await fs.writeFile(path.join(BUILD,'preview.png'),new Uint8Array(await rendered.arrayBuffer()));
await (await PresentationFile.exportPptx(p)).save(CANDIDATE);
if (sourceHash!==sha256(await fs.readFile(SOURCE))) throw Error('Reference deck changed');
await fs.writeFile(path.join(BUILD,'candidate-manifest.json'),JSON.stringify({sourceSha256:sourceHash,candidateSha256:sha256(await fs.readFile(CANDIDATE)),sourceSlide:sourceIndex+1,outputSlideCount:1,capturedAt:evidence.capturedAt},null,2));
console.log(JSON.stringify({candidate:CANDIDATE,preview:path.join(BUILD,'preview.png'),sourcePreview:path.join(BUILD,'source-slide.png'),slideCount:1}));
