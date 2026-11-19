/** Create only the replacement second slide, preserving the source deck.
 * Usage: node this.mjs <runtime-node-modules> <presentations-skill-dir>
 * Native text remains editable; the screenshot uses native PowerPoint cropping.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import crypto from 'node:crypto';

const [modulesDir, skillDir] = process.argv.slice(2);
if (!modulesDir || !skillDir) throw new Error('Expected runtime node_modules and presentations skill directory.');
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const build = path.join(root, '999_Temporary/roadops_slide2_story');
const source = path.join(root, '04_docs/presentation/output/RoadOps_제출기획서_20261119_v0.3.1_상황실수정.pptx');
const finalPath = path.join(root, '04_docs/presentation/output/RoadOps_02_담당자의출동계획_v0.1.pptx');
const capture = path.join(root, '04_docs/presentation/assets/roadops_submission_20261119/captures/11_AI_추천경로와_방문순서.png');
const background = path.join(root, '04_docs/presentation/assets/roadops_submission_20261118/14_roadops_route_background_v2.png');
await fs.mkdir(build, {recursive: true});
const require = createRequire(path.join(modulesDir, '_roadops_slide2_loader.cjs'));
const {FileBlob, Presentation, PresentationFile} = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const saveBlob = async (target, blob) => fs.writeFile(target, new Uint8Array(await blob.arrayBuffer()));

// Inspect the relevant source page before authoring the standalone replacement.
const reference = await PresentationFile.importPptx(await FileBlob.load(source));
await saveBlob(path.join(build, 'reference-slide2.png'), await reference.export({slide: reference.slides.getItem(1), format: 'png', scale: 1}));

const p = Presentation.create({slideSize: {width: 1280, height: 720}});
const s = p.slides.add();
s.background.fill = '#FFFFFF';
const C = {black: '#231F20', blue: '#1468B3', gray: '#77838D', foot: '#AFB6BD'};
function text(value, x, y, width, height, size, color = C.black, bold = false, font = 'Pretendard') {
  const shape = s.shapes.add({geometry: 'textbox', name: value.slice(0, 60), position: {left: x, top: y, width, height}, fill: 'none', line: {fill: 'none', width: 0}});
  shape.text = value;
  shape.text.insets = 0;
  shape.text.style = {typeface: font, fontSize: size, color, bold};
  return shape;
}
const imageData = async file => `data:image/png;base64,${(await fs.readFile(file)).toString('base64')}`;
s.images.add({dataUrl: await imageData(background), alt: '기존 기획서의 옅은 도로 모티프 배경. 실제 운영 데이터가 아닌 장식입니다.', fit: 'cover', position: {left: 0, top: 0, width: 1280, height: 720}});

text('하지만 담당자는 당황하지 않습니다', 64, 52, 1148, 76, 44, C.black, true);
text('RoadOps를 켜고, 오늘의 출동계획을 세웁니다.', 66, 140, 1148, 42, 23, C.gray);

const steps = [
  ['위험 상황을 확인합니다', '주의할 도로와 취약지역을 살핍니다.'],
  ['출동 조건을 입력합니다', '오늘 움직일 팀과 가용 시간을 정합니다.'],
  ['AI가 경로를 제안합니다', '담당자가 정한 기준으로 방문 순서를 만듭니다.'],
  ['담당자가 계획을 확정합니다', '추천 근거를 확인하고 출동계획을 결정합니다.'],
];
steps.forEach(([title, detail], i) => {
  const y = 215 + i * 91;
  text(String(i + 1).padStart(2, '0'), 66, y + 1, 40, 40, 24, C.blue, true, 'Poppins');
  text(title, 116, y, 412, 39, 26, C.black, true);
  text(detail, 116, y + 39, 412, 40, 18, C.gray);
});

text('RoadOps가 제안한 점검 경로', 564, 211, 650, 36, 22, C.blue, true);
// The screenshot is 3170 x 1936. Keep the depot, all three stops and map attribution.
s.images.add({
  dataUrl: await imageData(capture),
  alt: '실제 시연의 추천 경로. 용담 거점을 출발해 광령리, 소길리, 1100로의 세 도로를 점검하는 방문 순서입니다.',
  fit: 'cover',
  position: {left: 564, top: 256, width: 650, height: 317},
  crop: {left: 56 / 3170, top: 760 / 1936, right: (3170 - 56 - 2096) / 3170, bottom: (1936 - 760 - 1022) / 1936},
});
text('몇 번의 확인으로, 첫 출동계획이 준비됩니다.', 66, 607, 1148, 54, 34, C.blue, true);
text('RoadOps 시연 화면 · 2026.11.19 · © OpenStreetMap contributors', 66, 673, 1015, 26, 11, C.foot);
text('02 / 17', 1105, 674, 112, 22, 12, C.foot, false, 'Poppins');
s.speakerNotes.text = [
  '기존 기획서의 두 번째 장을 대체하기 위한 한 장짜리 슬라이드입니다.',
  '첫 장의 “출동에는 순서가 필요합니다”를 이어, 담당자가 RoadOps로 위험 상황을 확인하고 팀과 시간을 입력한 뒤 AI 제안의 근거를 검토하여 출동계획을 확정하는 흐름을 보여줍니다.',
  '사진 대신 실제 캡처를 사용했습니다. 지도는 원본 픽셀 변경 없이 네이티브 crop으로 확대했습니다. 원본과 동일한 가로세로 비율을 유지합니다.',
  '시연의 인원은 2명, 가용 시간은 120분이며 추천은 3곳입니다. 101.2분은 이동과 점검의 예상 합계이며 계획 생성 소요 시간이 아닙니다.',
  '계획 작성 시간을 측정한 근거가 없으므로 “단 1분” 또는 실제 배치 완료라는 문구는 사용하지 않았습니다. 담당자 확정은 시연 기능 흐름입니다.',
  '', '근거 자료',
  capture,
  path.join(root, '04_docs/presentation/assets/roadops_submission_20261119/captures/09_AI_출동인원과_가용시간.png'),
  path.join(root, '04_docs/presentation/assets/roadops_submission_20261119/captures/13_담당자_확정완료_시연.png'),
  source, background,
].join('\n');

await saveBlob(path.join(build, 'slide2-preview.png'), await p.export({slide: s, format: 'png', scale: 2}));
const candidatePath = path.join(build, 'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidatePath);
const {finalizePresentation} = await import(pathToFileURL(path.join(skillDir, 'container_tools/artifact_tool_utils.mjs')).href);
process.env.RUNTIME_NODE_MODULES = modulesDir;
const result = await finalizePresentation({
  workspaceDir: root, candidatePath, finalPath,
  pythonExecutable: '/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',
  integrityValidatorPath: path.join(skillDir, 'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath: path.join(skillDir, 'container_tools/inspect_presentation_layout_geometry.py'),
  explicitTotalSlideCount: 1,
  layoutArgs: ['--expected-slide-size-emu', '12192000,6858000', '--validate-bullet-geometry', '--validate-heading-fit'],
  requiredNativeTableOwnerSlides: [], requiredNativeChartOwnerSlides: [],
  fontPolicy: {basis: 'reference', families: ['Poppins', 'Pretendard'], referencePath: source, referenceSha256: crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex')},
  verifyArtifactToolImport: true,
  receiptPath: path.join(build, 'validation.json'),
});
const reopened = await PresentationFile.importPptx(await FileBlob.load(finalPath));
await saveBlob(path.join(build, 'slide2-final-preview.png'), await reopened.export({slide: reopened.slides.getItem(0), format: 'png', scale: 2}));
console.log(JSON.stringify(result));
