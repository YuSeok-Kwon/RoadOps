/** Local PPTX fallback for environments without Artifact Session edit tools.
 * Usage: node this.mjs source.pptx final.pptx runtime-node-modules skill-dir [captures.json]
 * The source is preserved. The optional capture map contains absolute image paths by slide number.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL, fileURLToPath} from 'node:url';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {writeRoadOpsStory} from './20261119_roadops_build_submission_presentation_v0_3.mjs';

const [source,finalPath,modulesDir,skillDir,captureFile]=process.argv.slice(2);
if(!source||!finalPath||!modulesDir||!skillDir)throw new Error('Expected source, finalPath, runtime node_modules and skill directory.');
if(path.resolve(source)===path.resolve(finalPath))throw new Error('Write a revision file; preserve the source.');
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const build=path.join(root,'999_Temporary','roadops_presentation_v03');
await fs.mkdir(build,{recursive:true});await fs.mkdir(path.dirname(finalPath),{recursive:true});
const require=createRequire(path.join(modulesDir,'_roadops_loader.cjs'));
const {FileBlob,PresentationFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const p=await PresentationFile.importPptx(await FileBlob.load(source));
const before=await p.inspect({kind:'slide,textbox,shape,image,table,chart',maxChars:250000});
await fs.writeFile(path.join(build,'source-inspection.json'),JSON.stringify(before,null,2));
// Source renders preserve a visual record of the reference before replacement.
for(const idx of [0,2,6,7,16]){
 const png=await p.export({slide:p.slides.getItem(idx),format:'png',scale:1});
 await fs.writeFile(path.join(build,`source-${idx+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
const evidence=JSON.parse(await fs.readFile(path.join(root,'04_docs/presentation/assets/roadops_submission_20261119/implementation_evidence.json'),'utf8'));
const captureConfig=captureFile?JSON.parse(await fs.readFile(captureFile,'utf8')):{};
const captures=captureConfig.captures?Object.fromEntries(Object.entries(captureConfig.captures).map(([key,name])=>[key,path.resolve(path.dirname(captureFile),'captures',name)])):captureConfig;
const assetDir=path.join(root,'04_docs/presentation/assets/roadops_submission_20261118');
const controlRoomImage=path.join(root,'04_docs/presentation/assets/roadops_submission_20261119/16_roadops_control_room_team_v2.png');
const imagePaths=[...['09_jeju_road_original_cover_v1.png','13_jeju_road_closure_v1.png','14_roadops_route_background_v2.png','15_roadops_planning_illustration_v1.png'].map(name=>path.join(assetDir,name)),controlRoomImage,...Object.values(captures)];
const imageSources={};
for(const imagePath of new Set(imagePaths)){
 const type=/\.jpe?g$/i.test(imagePath)?'image/jpeg':/\.webp$/i.test(imagePath)?'image/webp':'image/png';
 imageSources[imagePath]=`data:${type};base64,${(await fs.readFile(imagePath)).toString('base64')}`;
}
const result=await writeRoadOpsStory({presentation:p,input:{slides:Array.from({length:17},(_,i)=>i+1),assetDir,controlRoomImage,evidence,captures,imageSources}});
console.log(JSON.stringify(result));
const after=await p.inspect({kind:'slide,textbox,shape,image,table,chart,notes',maxChars:400000});
await fs.writeFile(path.join(build,'final-inspection.json'),JSON.stringify(after,null,2));
for(const [idx,slide] of p.slides.items.entries()){
 const png=await p.export({slide,format:'png',scale:1});
 await fs.writeFile(path.join(build,`slide-${idx+1}.png`),new Uint8Array(await png.arrayBuffer()));
 console.log('Rendered',idx+1);
}
const candidate=path.join(build,'candidate.pptx');
await(await PresentationFile.exportPptx(p)).save(candidate);
const {finalizePresentation}=await import(pathToFileURL(path.join(skillDir,'container_tools/artifact_tool_utils.mjs')).href);
const referenceSha256=crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex');
process.env.RUNTIME_NODE_MODULES=modulesDir;
const finalized=await finalizePresentation({
 workspaceDir:root,candidatePath:candidate,finalPath,
 pythonExecutable:'/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',
 integrityValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_layout_geometry.py'),
 explicitTotalSlideCount:17,
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','10'],
 requiredNativeTableOwnerSlides:[10],requiredNativeChartOwnerSlides:[7,12],
 materializeLiteralChartWorkbooks:true,
 fontPolicy:{basis:'reference',families:['Poppins','Pretendard'],referencePath:source,referenceSha256},
 verifyArtifactToolImport:true,receiptPath:path.join(build,path.basename(finalPath)+'.validation.json'),
});
console.log(JSON.stringify(finalized));
