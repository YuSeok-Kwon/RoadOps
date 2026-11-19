/** Replace only the slide-2 photograph in the reviewed PPTX.
 * Usage: node script.mjs source.pptx new.pptx runtime-node-modules skill-dir
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
const [source,finalPath,modulesDir,skillDir]=process.argv.slice(2);
if(!source||!finalPath||!modulesDir||!skillDir)throw new Error('Expected source, output, node_modules, and skill directory.');
if(path.resolve(source)===path.resolve(finalPath))throw new Error('Use a new output filename.');
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const build=path.join(root,'999_Temporary','roadops_presentation_v031');
await fs.mkdir(build,{recursive:true});await fs.mkdir(path.dirname(finalPath),{recursive:true});
const require=createRequire(path.join(modulesDir,'_roadops_loader.cjs'));
const {FileBlob,PresentationFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const p=await PresentationFile.importPptx(await FileBlob.load(source));
if(p.slides.items.length!==17)throw new Error('Expected 17 slides.');
const found=(await p.inspect({kind:'image',maxChars:250000})).records.filter(r=>r.slideIndex===1&&r.position.left===64&&r.position.top===215&&r.position.width===565&&r.position.height===414);
if(found.length!==1)throw new Error('The original slide-2 photo could not be identified uniquely.');
const photo=p.resolve(found[0].id);
const frame=photo.frame,crop=photo.crop,fit=photo.fit;
const bytes=await fs.readFile(path.join(root,'04_docs/presentation/assets/roadops_submission_20261119/16_roadops_control_room_team_v2.png'));
photo.replace({blob:new Uint8Array(bytes),contentType:'image/png',alt:'얼굴 없이 뒷모습으로 대형 관제 화면을 바라보는 여섯 담당자. AI 생성 가상 재난안전 상황실이며 실제 기관이나 운영 기록이 아닙니다.'});
photo.frame=frame;photo.crop=crop;photo.fit=fit;
p.slides.getItem(1).speakerNotes.text='여러 담당자가 대형 관제 화면을 바라보는 가상의 재난안전 상황실이다. 얼굴이 보이지 않는 뒷모습으로 구성했다. 기준 설정의 주체는 사람이며 AI는 입력 기준과 가용 자원에 따라 작업안을 제안한다. 실제 기관이나 운영 실적을 촬영한 사진이 아니다.\n\n근거 자료\n08_dashboard/roadops_map_v0_1/src/content/dashboard/ScoringPolicyPanel.jsx\n04_docs/presentation/assets/roadops_submission_20261119/control_room_team_generation.json';
for(const [i,slide] of p.slides.items.entries()){
 const png=await p.export({slide,format:'png',scale:1});
 await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
const edited=path.join(build,'artifact-edited.pptx');
await(await PresentationFile.exportPptx(p)).save(edited);
// Retain original package parts: the runtime round trip drops embedded chart
// workbooks. Transfer only the edited photo and notes back into the source ZIP.
const candidate=path.join(build,'candidate.pptx');
const pythonExecutable=path.resolve(modulesDir,'../../python/bin/python3');
const preservation=spawnSync(pythonExecutable,[path.join(root,'07_scripts/20261119_roadops_preserve_unchanged_pptx_parts.py'),source,edited,candidate],{encoding:'utf8'});
if(preservation.status!==0)throw new Error(preservation.stderr||preservation.stdout);
await fs.writeFile(path.join(build,'preservation.json'),preservation.stdout);
const {finalizePresentation}=await import(pathToFileURL(path.join(skillDir,'container_tools/artifact_tool_utils.mjs')).href);
process.env.RUNTIME_NODE_MODULES=modulesDir;
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath,
 pythonExecutable,
 integrityValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_layout_geometry.py'),
 explicitTotalSlideCount:17,layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','10'],
 requiredNativeTableOwnerSlides:[10],requiredNativeChartOwnerSlides:[7,12],materializeLiteralChartWorkbooks:true,
 fontPolicy:{basis:'reference',families:['Poppins','Pretendard'],referencePath:source,referenceSha256:crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex')},
 verifyArtifactToolImport:true,receiptPath:path.join(build,path.basename(finalPath)+'.validation.json')});
console.log(JSON.stringify({finalPath:result.finalPath,sha256:result.finalSha256,slideCount:result.packageIntegrity.slide_count,integrity:result.packageIntegrity.status,layoutFindings:result.presentationLayout.findingCount,importPassed:result.firstPartyImport.passed}));
