/** Combine verification and deployment content into one replacement slide.
 * Keep the RoadOps template and write no full-deck revision.
 * Render first; run --finalize after inspecting the preview.
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
const BUILD = path.join(ROOT, '999_Temporary/roadops_merge_delivery_20261120');
const OUT = path.join(ROOT, '02_outputs/ppt/RoadOps_검증_센터적용_통합_교체용_20261120');
const FINAL = path.join(OUT, 'RoadOps_구현현황과_센터적용계획_교체용_1장.pptx');
const PREVIEW = path.join(OUT, 'RoadOps_구현현황과_센터적용계획_미리보기.png');
const FONT = '프리텐다드';
const BOLD = '프리텐다드 Bold';
const C = {ink:'#231F20',green:'#679773',highlight:'#A9BDAE',muted:'#7F8B95',line:'#DDE5DF',light:'#F4F7F4',header:'#E8EFE9',white:'#FFFFFF'};

await fs.mkdir(BUILD, {recursive:true});
await fs.mkdir(OUT, {recursive:true});
const sourceHash = crypto.createHash('sha256').update(await fs.readFile(SOURCE)).digest('hex');
const p = await PresentationFile.importPptx(await FileBlob.load(SOURCE));
const query = {select:'$.slides[*]',include:['index','id','elements.id','elements.kind','elements.text','elements.position','notes.text']};
const before = (await p.inspect(query)).records;
if (before.length !== 15) throw Error('Expected the 15-slide source deck');
if (!before[12].elements.some(e => e.text === '검증 결과와 남은 한계를 구분합니다') ||
    !before[13].elements.some(e => e.text === '센터 환경에서 재현하고, 연계를 확장합니다')) {
  throw Error('The source slides differ from the requested verification/deployment pages');
}
await fs.writeFile(path.join(BUILD,'source-slides.json'), JSON.stringify(before.slice(12,14),null,2));
const sourceSlide = before[13];
const background = sourceSlide.elements.find(e => e.kind === 'image' && e.position.left === 0 && e.position.top === 0 && e.position.width === 1920 && e.position.height === 1080);
if (!background) throw Error('Original RoadOps background not found');
for (const e of sourceSlide.elements) if (e.id !== background.id) p.delete(e.id);
p.slides.delete(before.map((_,i) => i).filter(i => i !== 13));
if (p.slides.items.length !== 1) throw Error('Only one replacement slide is authorized');
const s = p.slides.getItem(0);

function text(value,x,y,width,height,size=32,color=C.ink,bold=false) {
  const shape = s.shapes.add({geometry:'textbox',name:value.split('\n')[0],position:{left:x,top:y,width,height},fill:'none',line:{fill:'none',width:0}});
  shape.text = value;
  shape.text.insets = 0;
  shape.text.style = {typeface:bold ? BOLD : FONT,fontSize:size,color,bold};
  return shape;
}
function rect(x,y,width,height,fill) {
  return s.shapes.add({geometry:'rect',position:{left:x,top:y,width,height},fill,line:{fill:'none',width:0}});
}

rect(83,115,1175,38,C.highlight);
text('구현 현황과 센터 적용 계획',96,78,1720,90,56,C.ink,true);
text('개발 환경에서 핵심 기능을 확인했으며, 센터 PC 검증과 외부 서비스 연동을 진행할 계획입니다.',100,181,1710,75,30,C.muted);

const values = [
  ['구분','핵심 내용'],
  ['현재 구현','데이터 조회, 점검 항목 제안, 방문 계획·우회경로 계산'],
  ['검증 결과','통계 재계산, 자동 테스트, 실제 화면 동작 확인'],
  ['실행 환경','Python·웹 브라우저 기반, CPU 중심 실행'],
  ['외부 의존성','저장 자료로 계산 재현 가능 / 실시간 자료·지도는 네트워크 필요\n실시간 API 인증키 필요 / LLM 연동 시 인증키·사용료 필요'],
  ['후속 계획','센터 PC 검증 후 LLM 연동, 서버 저장·기관 권한 연계']
];
const table = s.tables.add({rows:values.length,columns:2,left:110,top:296,width:1690,height:548,values,columnWidths:[300,1390]});
table.borders.assign({fill:C.line,width:1,style:'solid'});
const rowHeights = [66,91,91,91,118,91];
for (let r=0;r<values.length;r++) {
  table.rows[r].height = rowHeights[r];
  for (let c=0;c<2;c++) {
    const cell = table.getCell(r,c);
    cell.fill = r === 0 ? C.header : r%2 === 0 ? C.light : C.white;
    cell.text.insets = {top:12,right:22,bottom:12,left:22};
    cell.text.style = {typeface:r === 0 || c === 0 ? BOLD : FONT,fontSize:32,color:r === 0 ? C.green : C.ink,bold:r === 0 || c === 0,verticalAlignment:'middle'};
  }
}

text('개발 담당',114,893,220,46,32,C.green,true);
text('권유석 · 데이터 처리, Agent 도구, 운영 화면, 검증',350,893,1440,46,32);
text('검증 범위',114,955,220,46,32,C.green,true);
text('개발 환경에서 기능 확인 완료. 현장 효과와 센터 PC 성능은 추가 검증 예정.',350,955,1440,46,30);

s.speakerNotes.text = [
  '검증 결과와 센터 실행환경·개발계획 두 장을 합친 교체용 한 장이다. 현재 구현, 검증 결과, 실행 환경, 외부 의존성, 후속 계획으로 요약한다. 페이지 번호는 편집 중인 Canva 문서의 실제 순서에 맞춰 지정할 수 있도록 생략한다.',
  '현재 구현은 Python 데이터 처리·품질 검사, React/JavaScript 운영 화면, 규칙 기반 우선순위, 방문 계획 계산, 통제 링크를 제외한 대체 경로 탐색이다. 현재 범용 LLM은 미연동이다. LLM 연동은 후속 계획이며 현재 구현으로 표시하지 않는다.',
  '검증은 2026.11.20 기존 기능 검증 결과를 요약한 것이다. 원본 통계 재계산, 관련 Python·JavaScript 자동 테스트, 실제 브라우저 화면과 점검계획·확인 기록 반영을 확인했다. 상세 테스트 수와 결과는 실행환경·결과 설명자료에서 확인한다. 이번 슬라이드 편집으로 새 현장 검증을 수행했다는 의미가 아니다.',
  '센터 최소사양: Intel Core i7-8700, RAM 32GB, GTX 1060, VRAM 3072MB. 현재 계산은 CPU 중심이며 대형 로컬 모델이나 GPU 학습에 의존하지 않는다. 센터 실기기 성능, 사고 감소율, 업무시간 절감률 등 현장 효과는 아직 검증하지 않았다.',
  '저장된 CSV·JSON으로 기본 계산을 API 인증키 없이 재현할 수 있다. ITS·C-ITS·기상청 등 실시간 자료 수집에는 인증키와 네트워크가 필요하며, 지도 타일도 네트워크에 의존한다. 후속 OpenAI API 연동에는 API 키·네트워크·사용료가 필요하다. LLM 장애 시 기존 입력 화면으로 진행하는 방안을 검토한다.',
  '개발 담당 권유석: 데이터 처리, Agent 도구, 운영 UI, 검증. 센터 적용 순서는 PC 성능·재현성 검증, 외부 API·LLM 연동 검증, 서버 기록·기관 권한 연계다. 소스, 의존성, README, 설치·실행 방법, 환경변수 예시, 사용자 매뉴얼, 데이터 활용 명세와 결과·검증 자료는 별도 제출 패키지로 제공한다.',
  '출처 및 검증 근거',
  SOURCE,
  path.join(ROOT,'04_docs/deployment/20261120_roadops_jeju_inspection_evidence.md'),
  path.join(ROOT,'04_docs/deployment/20261116_roadops_center_environment_validation_v0_1.md'),
  path.join(ROOT,'02_outputs/ppt/RoadOps_제주데이터활용_15장_20261120/실제화면/capture-evidence.json'),
  path.join(ROOT,'requirements.txt')
].join('\n\n');

const after = (await p.inspect(query)).records;
if (after.length !== 1 || s.tables.items.length !== 1) throw Error('Expected one slide with one editable table');
await fs.writeFile(path.join(BUILD,'layout.json'),JSON.stringify(after,null,2));
const rendered = await p.export({slide:s,format:'png',scale:1});
await fs.writeFile(path.join(BUILD,'preview.png'),new Uint8Array(await rendered.arrayBuffer()));
const candidate = path.join(BUILD,'merged-delivery-candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
if (crypto.createHash('sha256').update(await fs.readFile(SOURCE)).digest('hex') !== sourceHash) throw Error('Reference deck changed');

if (process.argv.includes('--finalize')) {
  process.env.RUNTIME_NODE_MODULES = path.join(RUNTIME,'node/node_modules');
  const {finalizePresentation} = await import(path.join(SKILL,'container_tools/artifact_tool_utils.mjs'));
  const receipt = await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:FINAL,pythonExecutable:path.join(RUNTIME,'python/bin/python3'),integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),explicitTotalSlideCount:1,requiredNativeTableOwnerSlides:[1],requiredNativeChartOwnerSlides:[],layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-heading-fit','--require-native-table-slide','1'],fontPolicy:{basis:'reference',families:[FONT,BOLD],referencePath:SOURCE,referenceSha256:sourceHash},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
  await fs.copyFile(path.join(BUILD,'preview.png'),PREVIEW);
  console.log(JSON.stringify({finalPath:receipt.finalPath,preview:PREVIEW,slideCount:receipt.firstPartyImport.slideCount,layoutPassed:receipt.presentationLayout.findingCount===0}));
} else {
  console.log(JSON.stringify({candidate,preview:path.join(BUILD,'preview.png'),slideCount:1,sourceUnchanged:true}));
}
