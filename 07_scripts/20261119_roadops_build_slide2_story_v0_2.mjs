/** Standalone narrative replacement for slide two.
 * Usage: node this.mjs <runtime-node-modules> <presentations-skill-dir>
 * Editable narration over a fictional AI-generated situation photograph.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import crypto from 'node:crypto';

const [modulesDir, skillDir] = process.argv.slice(2);
if (!modulesDir || !skillDir) throw new Error('Expected runtime node_modules and presentations skill directory.');
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const build = path.join(root, '999_Temporary/roadops_slide2_narrative_v02');
const source = path.join(root, '04_docs/presentation/output/RoadOps_제출기획서_20261119_v0.3.1_상황실수정.pptx');
const finalPath = path.join(root, '04_docs/presentation/output/RoadOps_02_스토리텔링_v0.2.pptx');
const assetDir = path.join(root, '04_docs/presentation/assets/roadops_submission_20261119');
const scene = path.join(assetDir, '17_roadops_first_dispatch_story_v1.png');
const provenance = JSON.parse(await fs.readFile(path.join(assetDir, '17_roadops_first_dispatch_story_v1.provenance.json'), 'utf8'));
await fs.mkdir(build, {recursive: true});
const require = createRequire(path.join(modulesDir, '_roadops_narrative_loader.cjs'));
const {FileBlob, Presentation, PresentationFile} = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const saveBlob = async (target, blob) => fs.writeFile(target, new Uint8Array(await blob.arrayBuffer()));
const p = Presentation.create({slideSize: {width: 1280, height: 720}});
const s = p.slides.add();
s.background.fill = '#FFFFFF';
function text(value, x, y, width, height, size, color = '#231F20', bold = false, font = 'Pretendard') {
  const shape = s.shapes.add({geometry: 'textbox', name: value.slice(0, 60), position: {left: x, top: y, width, height}, fill: 'none', line: {fill: 'none', width: 0}});
  shape.text = value;
  shape.text.insets = 0;
  shape.text.style = {typeface: font, fontSize: size, color, bold};
  return shape;
}

// Same white masthead, dark rainy scene and typography as the revised cover.
text('하지만 담당자는 당황하지 않습니다', 64, 65, 1148, 79, 44, '#231F20', true);
s.images.add({
  dataUrl: `data:image/png;base64,${(await fs.readFile(scene)).toString('base64')}`,
  alt: 'AI 생성 상황 재현. 비 내리는 사무실에서 담당자가 차분히 노트북으로 계획을 확인하고, 동료들은 우의를 입고 출동을 준비합니다.',
  fit: 'contain', position: {left: 0, top: 190, width: 1280, height: 480},
});
text('RoadOps를 켜고,\n위험 상황과 취약지역을 살펴봅니다.', 64, 238, 558, 82, 26, '#FFFFFF');
text('오늘 움직일 팀과 시간을 입력하자,\n먼저 갈 도로와 방문 순서가 나타납니다.', 64, 344, 558, 82, 26, '#FFFFFF');
text('계획을 확인한 담당자가 말합니다.', 64, 461, 558, 47, 25, '#D3DCE4');
text('“이 순서대로 출발하죠.”', 64, 531, 558, 77, 40, '#FFFFFF', true);
text('AI 생성 상황 재현 이미지', 64, 689, 1015, 22, 11, '#AFB6BD');
text('02 / 17', 1105, 687, 112, 24, 12, '#AFB6BD', false, 'Poppins');
s.speakerNotes.text = [
  '비는 한꺼번에 쏟아지고, 현장반은 모든 도로로 동시에 갈 수 없습니다. 담당자는 RoadOps로 위험 상황과 취약지역을 살피고 오늘 움직일 팀과 시간을 입력합니다. 담당자가 정한 기준에 맞춰 제안된 방문 계획을 확인한 뒤, 첫 출동을 준비합니다.',
  '장면과 대사는 서비스 이용 흐름을 설명하는 가상 시나리오입니다. 특정 기관이나 인물의 실제 업무 장면, 실제 출동 실적, 실측 소요 시간을 나타내지 않습니다.',
  '', '이미지 출처', scene,
  '제작 방식: built-in image_gen. 생성한 상황 재현 이미지이며 실제 제품 화면이 아닙니다.',
  '생성 프롬프트: ' + provenance.prompt,
  '수정 프롬프트: ' + provenance.editPrompt,
  '', '기능 근거',
  path.join(root, '04_docs/presentation/assets/roadops_submission_20261119/implementation_evidence.json'),
  path.join(root, '08_dashboard/roadops_map_v0_1/src/content/dashboard/WorkflowPanel.jsx'),
].join('\n');

await saveBlob(path.join(build, 'draft-preview.png'), await p.export({slide: s, format: 'png', scale: 2}));
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
  verifyArtifactToolImport: true, receiptPath: path.join(build, 'validation.json'),
});
const reopened = await PresentationFile.importPptx(await FileBlob.load(finalPath));
if (reopened.slides.items.length !== 1) throw new Error('The replacement must contain exactly one slide.');
await saveBlob(path.join(build, 'final-preview.png'), await reopened.export({slide: reopened.slides.getItem(0), format: 'png', scale: 2}));
console.log(JSON.stringify(result));
