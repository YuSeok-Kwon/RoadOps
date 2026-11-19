/** Rebuild the latest Canva export around the operator workflow.
 * Usage: node this.mjs frozen-snapshot.json [--finalize]
 * Slides 1 and 2 are restored byte-for-byte by the companion package helper.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import crypto from 'node:crypto';
import {FileBlob,PresentationFile} from '/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';

const ROOT=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const BUILD=path.join(ROOT,'999_Temporary/roadops_workflow_v04');
const PY='/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const SKILL='/Users/yu_seok/.codex/plugins/cache/openai-primary-runtime/presentations/26.1118.11504/skills/presentations';
const SUPPORT=path.join(ROOT,'07_scripts/20261119_roadops_workflow_deck_support_v0_4.py');
const source=path.join(ROOT,'02_outputs/ppt',(await fs.readdir(path.join(ROOT,'02_outputs/ppt'))).find(n=>n.normalize('NFC')==='RoadOps 공모전 제출 기획서.pptx'));
const snapshot=process.argv[2];
if(!snapshot)throw new Error('A frozen dashboard snapshot is required.');
await fs.mkdir(BUILD,{recursive:true});
console.log(execFileSync(PY,[SUPPORT,'prepare',source,snapshot,BUILD],{encoding:'utf8'}));
const evidence=JSON.parse(await fs.readFile(path.join(BUILD,'continuous-replan.json'),'utf8'));
const p=await PresentationFile.importPptx(await FileBlob.load(source));
if(p.slides.items.length!==17)throw new Error('Expected 17 source slides.');
const before=await p.inspect({select:'$.slides[*]',include:['id','index','elements.id','elements.kind','elements.text']});
for(const r of before.records.filter(r=>r.index>=2))for(const e of r.elements)p.delete(e.id);

const C={ink:'#231F20',green:'#679773',highlight:'#A9BDAE',blue:'#1468B3',muted:'#7F8B95',light:'#F4F7F4',line:'#DDE5DF',white:'#FFFFFF',amber:'#B5701D'};
const FONT='프리텐다드', BOLD='프리텐다드 Bold';
const HQ=path.join(ROOT,'02_outputs/RoadOps_PPT_고해상도_교체이미지_2026-11-19');
const media=path.join(BUILD,'source-media');
const images=new Map();
async function load(file){if(!images.has(file))images.set(file,new Uint8Array(await fs.readFile(file)));return images.get(file);}
const bg=await load(path.join(media,'image3.png'));
const stamp='2026.11.19 17:40 저장 자료 · 실제 RoadOps 화면';
function text(s,value,x,y,w,h,size=36,color=C.ink,bold=false,font){
 const a=s.shapes.add({geometry:'textbox',name:value.split('\n')[0].slice(0,60),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 a.text=value;a.text.insets=0;a.text.style={typeface:font||(bold?BOLD:FONT),fontSize:size,color,bold};return a;
}
function rect(s,x,y,w,h,fill){return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:'none',width:0}});}
async function pic(s,file,x,y,w,h,fit='contain',crop){return s.images.add({blob:await load(file),contentType:'image/png',alt:path.basename(file),fit,position:{left:x,top:y,width:w,height:h},...(crop?{crop}:{} )});}
function head(n,title,sub){
 const s=p.slides.getItem(n-1);s.background.fill=C.white;
 s.images.add({blob:bg,contentType:'image/png',position:{left:0,top:0,width:1920,height:1080},fit:'cover',alt:'원본 슬라이드의 공통 도로선 배경'});
 rect(s,83,115,Math.min(1720,title.length*57+30),38,C.highlight);
 text(s,title,96,77,1722,91,61,C.ink,true);
 if(sub)text(s,sub,99,178,1717,74,31,C.muted);
 text(s,String(n).padStart(2,'0')+' / 17',1750,1010,162,36,22,C.muted,false,FONT);
 return s;
}
function foot(s,value){text(s,value,99,1007,1630,39,18,C.muted);}
function note(s,value,...refs){s.speakerNotes.text=value+'\n\n출처\n'+refs.join('\n');}
function table(s,values,x,y,w,h,widths,size=33){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
 t.borders.assign({fill:C.line,width:1,style:'solid'});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[r].length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?'#E8EFE9':r%2===0?C.light:C.white;
  cell.text.style={typeface:r===0?BOLD:FONT,fontSize:size,color:r===0?C.green:C.ink,bold:r===0};
 }
 return t;
}
function summary(s,value,y=931){text(s,value,110,y,1690,59,34,C.green,true);}

// 1–2 remain untouched. The source package is restored after export as well.
{
 const s=head(3,'오늘의 임무, 2명이 120분 안에 도로를 점검합니다','용담 거점의 담당자가 한 현장반의 점검 계획을 세우는 과정을 따라갑니다.');
 text(s,'용담 제설전진기지',112,310,970,74,53,C.green,true);
 text(s,'2명',113,420,380,170,126,C.ink,true);
 text(s,'120분',530,420,590,170,126,C.ink,true);
 text(s,'출동 가능한 인원',118,608,400,56,34,C.muted);
 text(s,'이동과 점검에 쓸 시간',540,608,620,56,34,C.muted);
 text(s,'먼저 확인할 도로를 고르고,\n이 시간 안에 가능한 방문 순서를 정합니다.',115,745,1120,150,45,C.ink,true);
 await pic(s,path.join(media,'image4.png'),1230,305,575,435);
 text(s,'거점 선택부터 계획 확정까지\n한 담당자의 판단을 따라갑니다.',1240,789,560,115,32,C.muted);
 foot(s,'용담팀 2명·120분 시연 조건 · 지도는 AI 생성 개념도 · 실제 기관의 근무 편제와 구분');
 note(s,'전체 3팀 실험 수치 대신 이후 화면과 같은 용담 현장반 2명/120분으로 시연 범위를 통일했다. 앞의 1·2장은 사용자가 확정한 원본 그대로 보존했다. 우천 사진은 이야기 도입이며 저장 시점의 폭우 관측을 주장하지 않는다.',source,path.join(HQ,'추가_AI입력조건/01_출동인원과_가용시간.png'));
}
{
 const s=head(4,'거점 주변에서 우선 검토 도로를 찾습니다','주변 기상과 후보 도로를 살핀 뒤, 궁금한 도로의 ‘점수 근거’를 펼칩니다.');
 await pic(s,path.join(HQ,'04장_용담_주변상황_우선검토도로_고해상도.png'),100,292,1710,676);
 foot(s,stamp+' · 목록의 순위는 검토의 출발점이며, 최종 방문 순서는 출동 조건과 함께 결정');
 note(s,'평화로 46.1점과 광령리 평화로 44점이 보이는 실제 주변 상황 화면. 여기서는 계획을 아직 제시하지 않는다.',path.join(HQ,'04장_용담_주변상황_우선검토도로_고해상도.png'));
}
{
 const s=head(5,'오늘 점검에 적용할 판단 기준을 정합니다','담당자가 포함할 항목과 배점을 선택합니다. AI도 이 기준을 그대로 사용합니다.');
 const names=['01_현재도로위험상황.png','02_과거사고_도로구조.png','03_기상_노면상태.png','04_실시간교통.png','05_공항유입.png','06_주변사고다발지역.png','07_과거유사상황.png','08_생활안전순찰수요.png'];
 for(let i=0;i<8;i++)await pic(s,path.join(HQ,'05장_항목별',names[i]),110+i%2*875,294+Math.floor(i/2)*139,825,119);
 text(s,'예시 배점 합계 100',113,885,710,60,41,C.green,true);
 text(s,'수동 모드와 AI 모드에 동일하게 적용',905,884,886,65,36,C.ink,true);
 foot(s,stamp+' · 배점은 담당자가 바꾸는 설정값이며, 사고 발생 확률을 뜻하지 않음');
 note(s,'8개 배점 30/20/20/10/5/8/5/2의 실제 조작부를 고해상도로 배치했다. 전체 원본 UI와 배열은 다르지만 각 캡처의 픽셀/값은 수정하지 않았다. 자료 부족 처리는 6장의 짧은 설명과 발표자 노트로 옮겼다.',path.join(HQ,'05장_점수항목과배점_전체_고해상도.png'),'08_dashboard/roadops_map_v0_1/src/content/dashboard/priority-policy.js');
}
{
 const s=head(6,'평화로 46.1점, 무엇이 점수를 높였을까요?','설정한 기준이 이 도로에 어떻게 적용됐는지, 실제 기여점수로 확인합니다.');
 text(s,'평화로',114,310,460,65,48,C.ink,true);
 text(s,'46.1',110,398,520,170,143,C.blue,true,FONT);
 text(s,'점',500,469,70,70,50,C.blue,true);
 text(s,'현재 도로 위험과\n기상·노면 상태의 기여가 큽니다.',117,618,534,155,38,C.ink,true);
 text(s,'근거 반영률 93%',117,825,530,58,36,C.green,true);
 const data=[['현재 도로 위험',22.6],['기상·노면',8.6],['사고·도로 구조',6],['과거 유사상황',5.2],['실시간 교통',3.8],['사고다발지역',0]].reverse();
 s.charts.add('bar',{position:{left:675,top:300,width:1125,height:575},categories:data.map(r=>r[0]),series:[{name:'기여점수',values:data.map(r=>r[1]),fill:C.blue}],barOptions:{direction:'bar',gapWidth:75},hasLegend:false,dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.0',textStyle:{typeface:FONT,fontSize:29}},xAxis:{textStyle:{typeface:FONT,fontSize:32}},yAxis:{textStyle:{typeface:FONT,fontSize:25},majorGridlines:{fill:C.line,width:1}},chartFill:C.white,plotAreaFill:C.white});
 text(s,'자료가 없는 항목은 ‘안전해서 0점’으로 해석하지 않습니다.',116,928,1660,55,34,C.green,true);
 foot(s,'공항 유입·생활안전은 자료 없음 · 확인된 근거로 환산한 예시 · 항목별 반올림 합계와 최종값은 차이 가능');
 note(s,'원본 화면의 실제 기여 22.6/6.0/8.6/3.8/0/5.2. 표시 합계46.2와 원계산값46.149의 반올림46.1은 구분했다. 자료 없음은0으로 차트에 넣지 않았다. available 방식은 근거 반영률60% 이상 등 조건 충족 시 확인된 항목으로 환산한다. complete 방식은 필요한 근거가 모두 있어야 산정하므로 이 예시를 보류한다. 0/제외/해당없음의 상세 구분은 본문을 분리하지 않고 이 노트에 보존한다.',path.join(HQ,'07장_점수근거/01_평화로_46.1점_산정근거.png'));
}
{
 const s=head(7,'같은 도로의 과거 기록까지 확인합니다','비슷했던 날의 사건 장소를 펼쳐, 이번에 확인할 위치와 주변 위험을 함께 살핍니다.');
 await pic(s,path.join(HQ,'08장_과거자료/01_비슷했던날의_사건장소.png'),110,302,1690,539);
 text(s,'주변 사고다발지역',115,875,800,56,36,C.green,true);
 text(s,'반복해서 문제가 있었던 위치를 함께 확인',115,930,830,48,29,C.ink);
 text(s,'생활안전 참고자료',1015,875,780,56,36,C.green,true);
 text(s,'지도는 참고 분포이며, 색을 점수로 바꾸지 않음',1015,930,780,48,28,C.ink);
 foot(s,stamp+' · 표시된 최근 기록 전체가 점수에 반영되는 것은 아님');
 note(s,'현재 후보인 광령리 평화로 인근과 연결된 사건 기록을 확인하는 장면. 점수 반영은 같은 도로/유사도/수집 시점 등의 조건을 따르며 화면에 보이는 기록 전체가 아니다. 생활안전지도는2025년 과거 도로별 주의등급이며 미래 발생확률이 아니다. 점수의 생활안전 항목은별도 시 단위 통계다. 범죄주의 지도 단독 장을 없애고 담당자가 참고하는 자료로 묶었다.',path.join(HQ,'08장_과거자료/01_비슷했던날의_사건장소.png'),path.join(HQ,'09장_생활안전지도/03_생활안전_자료설명.png'));
}
{
 const s=head(8,'점검하는 동안의 날씨도 함께 살핍니다','현재 상황뿐 아니라 이후 예보를 확인하고, 다시 살펴볼 도로와 시점을 판단합니다.');
 await pic(s,path.join(HQ,'11장_기상/04_PPT교체용_6시간후.png'),100,275,790,710);
 text(s,'시점을 바꾸며 기상과 도로를 함께 확인',963,310,830,120,44,C.green,true);
 table(s,[['시점','기온','시간당 강수량'],['현재','1–7°C','0–1mm'],['1시간 후','0–7°C','0–1mm'],['3시간 후','1–9°C','0–1mm'],['6시간 후','1–9°C','0–1mm']],963,453,825,320,[275,230,320],30);
 text(s,'예보가 달라지면\n점검 대상과 출발 시점을 다시 검토합니다.',970,830,815,125,35,C.ink,true);
 foot(s,'기상청 저장 예보 · 왼쪽은 6시간 후 화면 · 예보와 실제 관측, 사고 예측 성능은 구분');
 note(s,'4개의 고해상도 기상 화면에 표시된 값을 그대로 요약했다. 이후 시간별 위험도 정확도를 주장하지 않는다. 기존 점수 버전의 후행 검증0/0/0은 본문에서 빼고 이 노트로 이동했다. 예보 유효시각과 강수 영상 시각은 별도 표시다.',...['01_현재관측.png','02_1시간후.png','03_3시간후.png','04_PPT교체용_6시간후.png'].map(n=>path.join(HQ,'11장_기상',n)));
}
{
 const s=head(9,'움직일 수 있는 인원과 시간을 입력합니다','AI 자동선택으로 넘어가 출동 가능 여부와 이번 근무의 가용 자원을 확인합니다.');
 await pic(s,path.join(HQ,'추가_AI입력조건/01_출동인원과_가용시간.png'),110,303,1690,297);
 text(s,'2명',119,674,480,161,123,C.ink,true);
 text(s,'120분',790,674,860,161,123,C.ink,true);
 text(s,'용담 현장반의 출동 인원',125,845,620,63,35,C.muted);
 text(s,'이동과 점검을 합친 가용 시간',800,845,910,63,35,C.muted);
 summary(s,'자원 조건을 바꾸면 가능한 방문 계획도 다시 계산됩니다.');
 foot(s,stamp+' · 출동 인원·차량 정원·시간 조건을 확인하는 실제 입력 화면');
 note(s,'3장에서 제시한 용담2명/120분이 실제출동팀 입력부에 적용되는 장면이다. 인원과시간을바꾸면최적화와지도배분이갱신되는구현을 확인했다.',path.join(HQ,'추가_AI입력조건/01_출동인원과_가용시간.png'),'08_dashboard/roadops_map_v0_1/src/content/dashboard/WorkflowPanel.jsx');
}
{
 const s=head(10,'반드시 볼 곳과 이번에 제외할 곳을 정합니다','도로별 담당팀과 확인 순서를 조정하고, 현장 상황에 따라 고정·제외 조건을 반영합니다.');
 await pic(s,path.join(HQ,'추가_AI입력조건/04_도로별_배정조건_전체.png'),110,285,1690,430,'cover',{left:0,top:0,right:0,bottom:.27});
 text(s,'확인 순서·팀 고정',117,766,790,60,39,C.green,true);
 text(s,'현장 제보나 이미 정해진 담당팀을 반영',117,829,820,55,30,C.ink);
 text(s,'점검 제외',1000,766,790,60,39,C.green,true);
 text(s,'미배정 사유를 확인하고 이번 계획에서 조정',1000,829,790,55,30,C.ink);
 summary(s,'자동 제안을 검토한 뒤, 필요한 도로는 담당자가 직접 조정합니다.',913);
 foot(s,stamp+' · 도로별 입력 화면 · 확인 순서를 직접 바꾸면 조정 이유도 기록');
 note(s,'기존10장의결측처리설명대신실제업무의도로배정단계를배치했다. 캡처는입력단계를보여주며3곳확정전의화면이다. 첫확정시연에서는미배정3곳을이번계획에서제외했다. 필수점검은제외할수없으며현장조정은이유와함께기록된다.',path.join(HQ,'추가_AI입력조건/04_도로별_배정조건_전체.png'),'08_dashboard/roadops_map_v0_1/src/content/dashboard/WorkflowPanel.jsx');
}
{
 const s=head(11,'조건에 맞는 방문 순서가 나옵니다','용담에서 출발해 광령리·소길리·예래동을 확인하는 계획을 검토합니다.');
 await pic(s,path.join(HQ,'06장_AI추천경로/03_추천경로_지도만.png'),105,300,920,650);
 await pic(s,path.join(HQ,'06장_AI추천경로/02_PPT교체용_추천순찰코스.png'),1070,293,725,450);
 text(s,'3곳',1083,791,300,112,77,C.green,true);
 text(s,'101.2분',1410,791,400,112,77,C.blue,true);
 text(s,'점검 대상',1089,908,300,50,31,C.muted);
 text(s,'이동 56.2 + 점검 45분',1408,908,400,70,29,C.muted);
 foot(s,stamp+' · 이동시간은 추정치 · 120분 안에서 18.8분의 여유가 있는 제안');
 note(s,'고해상도 실제추천순찰코스/지도와같은세작업. 원값56.182+45=101.182. 위험점수순정렬과방문순서는다르며권한/필수/시간/이동경로를함께검토한다. 14장부터는동일팀과3개작업을입력으로연결한별도통제시뮬레이션이다.',path.join(HQ,'06장_AI추천경로/02_PPT교체용_추천순찰코스.png'),path.join(BUILD,'continuous-replan.json'));
}
{
 const s=head(12,'담당자가 확인한 계획으로 출발합니다','데이터 상태와 예상시간, 현장 상황을 확인한 뒤 첫 방문 계획을 확정합니다.');
 await pic(s,path.join(HQ,'15장_계획확정/04_출동전_검토항목.png'),110,300,1690,185);
 text(s,'광령리 · 소길리 · 예래동 1100로',120,520,1650,65,46,C.green,true);
 await pic(s,path.join(HQ,'15장_계획확정/03_PPT교체용_확인자와_승인기록.png'),110,590,1690,400);
 foot(s,'웹 확정 시연 2026.11.19 19:27:16 KST · 시연 담당자 확인 기록 · 실제 출동 지시 아님');
 note(s,'실제확정기록을첫출동시점에옮겼다. 기존배점성능45.1%과거실험은이흐름에섞지않는다. 이번로컬웹시연은3미배정제외/3방문/101.2분의계획지문wf-0f242036이다.',path.join(HQ,'15장_계획확정/03_PPT교체용_확인자와_승인기록.png'));
}
{
 const s=p.slides.getItem(12);s.background.fill=C.white;
 rect(s,83,115.5,1250,37.5,C.highlight);
 text(s,'출발한 뒤에도, 상황은 바뀝니다',96,77,1722,90,66,C.ink,true);
 await pic(s,path.join(media,'image15.png'),0,285,1920,720,'cover');
 text(s,'첫 점검을 마친 뒤,\n다음 도로로 이동하던 중입니다.',96,356,837,110,39,C.white);
 text(s,'그런데 남은 이동 경로에\n도로 통제 정보가 들어옵니다.',96,515,837,110,39,C.white);
 text(s,'담당자는 남은 계획을 다시 확인합니다.',96,690.5,950,70,37.5,'#D3DCE4');
 text(s,'“끝낸 업무는 두고,\n남은 경로를 다시 보죠.”',96,791,1100,170,55,C.white,true);
 text(s,'통제 상황을 가정한 시뮬레이션 · AI 생성 상황 재현 이미지',0,985,1522.5,23,16.5,'#AFB6BD');
 note(s,'사용자가요청한1·2장의흰상단/초록밑줄/하단사진띠/왼쪽흰문구를같은좌표로재사용했다. 사진은원본13장의생성배경이다. 다음장에서는같은용담3작업중첫광령리완료를가정하고저장경로의4050430101링크통제를주입한다. 실제발생통제나관측사진이아니다.',source,path.join(BUILD,'continuous-replan.json'));
}
{
 const s=head(14,'끝낸 점검은 유지하고, 남은 방문만 다시 검토합니다','같은 용담팀 계획에서 광령리 점검을 마쳤다고 가정하고, 이후 경로의 통제를 반영했습니다.');
 table(s,[['점검 대상','처음 계획','통제 반영 후'],['광령리 평화로','첫 번째 방문','완료한 점검 유지'],['소길리 평화로','두 번째 방문','이용 가능한 저장 경로 없음 · 보류'],['예래동 1100로','세 번째 방문 · 필수 점검','남은 점검으로 유지']],111,320,1685,400,[480,475,730],36);
 text(s,'완료 1곳 유지',119,776,530,70,43,C.green,true);
 text(s,'남은 점검 1곳',723,776,530,70,43,C.blue,true);
 text(s,'보류 1곳 확인',1320,776,500,70,43,C.amber,true);
 text(s,'통제 구간을 지나는 저장 경로를 제외하고, 가능한 계획을 다시 계산합니다.',119,905,1680,80,35,C.ink,true);
 foot(s,'동일 입력의 별도 통제 시뮬레이션 · 새 우회 경로 탐색 없이 저장 경로로 검토 · 실제 통제 아님');
 note(s,'1개팀/3곳/120분의동일입력에서첫작업완료를보존한다. 4050430101를포함하는저장routeoption을사용불가로처리하고build_partial_replan을실행했다. report pass/위반0. 소길리는no_team_with_available_road_route로미배정,예래필수유지. 기존다른3팀실험의1팀변경/2팀유지수치를삭제했다. 84.9분은완료한광령리까지포함한총예상시간이며,한곳보류로감소한것이라효율개선으로주장하지않는다.',path.join(BUILD,'continuous-replan.json'),'05_src/roadops/replanning.py');
}
{
 const s=head(15,'보류된 도로까지 확인한 뒤, 변경안을 결정합니다','자동으로 제안된 변경안을 그대로 출동 지시로 쓰지 않고, 담당자가 검토합니다.');
 text(s,'소길리 평화로',115,302,900,90,60,C.amber,true);
 text(s,'이번 변경안에서는 보류',115,405,900,70,43,C.ink,true);
 text(s,'통제 구간을 피하는 저장 경로가 없어\n현장 확인이나 추가 경로 검토가 필요합니다.',117,520,920,151,38,C.ink);
 text(s,'담당자가 다시 확인할 내용',1090,307,710,75,45,C.green,true);
 text(s,'완료한 광령리 점검이 유지됐는가\n\n필수인 예래동 점검을 수행할 수 있는가\n\n보류한 소길리의 후속 조치는 무엇인가',1090,428,710,330,34,C.ink);
 text(s,'84.9분',120,761,670,128,91,C.blue,true,FONT);
 text(s,'완료한 점검을 포함한 변경안의 총 예상시간',123,892,960,55,31,C.muted);
 text(s,'검토 후 변경안 확정',1090,856,710,80,45,C.green,true);
 foot(s,'통제 시뮬레이션의 검토 대상 · 한 곳 보류로 시간이 줄었으며 효율 개선 실적이 아님 · 웹 자동 승인과 미연동');
 note(s,'재계획결과의manual_approval_required=true를업무언어로설명한다. 아직실행하지않은웹승인을완료한기록처럼붙이지않았다. 기술검증pass와현장판단/승인은구분된다. 소길리후속조치는담당자가결정해야한다. 실제전자결재나현장지시연계는후속범위다.',path.join(BUILD,'continuous-replan.json'));
}
{
 const s=head(16,'어떤 기준으로 무엇을 바꿨는지 기록으로 남습니다','다음 담당자도 처음 계획과 변경 이유를 이어서 확인할 수 있도록 근거를 남깁니다.');
 table(s,[['단계','남겨야 할 판단과 근거'],['판단 기준','선택한 8개 항목 · 배점 · 자료 부족 처리 방식'],['첫 계획','용담팀 2명 · 120분 · 3곳 방문 · 예상 101.2분'],['통제 반영','광령리 완료 유지 · 예래동 점검 유지 · 소길리 보류'],['확인 기록','확인자 · 시각 · 현장 메모 · 계획 식별값']],110,295,1690,416,[390,1300],34);
 text(s,'첫 계획의 실제 확인 기록',119,766,1660,63,37,C.green,true);
 await pic(s,path.join(HQ,'15장_계획확정/03_PPT교체용_확인자와_승인기록.png'),115,843,1680,125,'cover',{left:0,top:.63,right:0,bottom:0});
 foot(s,'첫 계획은 브라우저 확인 기록 · 통제 변경안은 별도 실행 결과 · 서버 영속 저장·전자결재 연계는 후속 범위');
 note(s,'첫계획웹기록19:27:16/wf-0f242036과후속통제결과JSON을구분해제시했다. 둘을하나의자동서버감사기록처럼표현하지않는다. 기존53개검사/6장애시나리오는2026.11.16실험이며새배점전체검증이아니므로본문에서제외했다. 입력/기준/계획/변경이유의재현자료는함께보존한다.',path.join(HQ,'15장_계획확정/03_PPT교체용_확인자와_승인기록.png'),path.join(BUILD,'continuous-replan.json'));
}
{
 const s=p.slides.getItem(16);s.background.fill=C.white;
 const logo=text(s,'RoadOps',96,74,660,150,110,C.ink,true,'Poppins Bold');
 logo.text.getRange(4,3).color=C.green;
 rect(s,94,439,1570,45,C.highlight);
 text(s,'첫 출동의 순서부터,',96,350,1720,134,92,C.ink,true);
 text(s,'상황이 바뀐 뒤의 판단까지.',96,505,1720,134,92,C.ink,true);
 text(s,'담당자가 기준을 정하고, 근거를 확인하며,\n실행할 계획을 결정합니다.',104,748,1680,155,45,C.ink);
 text(s,'제주 도로관리 담당자를 위한 운영 보조 Agent',106,994,1670,54,29,C.muted);
 note(s,'이야기는상황확인/판단기준/근거검토/출동조건/방문계획/확정/통제/변경검토/기록으로마무리한다. 범용LLM이나실제기관운영완료로과장하지않는다. 사진1·2는원본보존,13은같은디자인으로장면전환했다.');
}

await fs.writeFile(path.join(BUILD,'final-inspection.json'),JSON.stringify((await p.inspect({select:'$.slides[*]',include:['id','index','elements.id','elements.kind','elements.text','elements.position','notes.text']})).records,null,2));
for(let i=0;i<17;i++){
 const b=await p.export({slide:p.slides.getItem(i),format:'png',scale:.65});
 await fs.writeFile(path.join(BUILD,`slide-${i+1}.png`),new Uint8Array(await b.arrayBuffer()));
 console.log('Rendered',i+1);
}
const raw=path.join(BUILD,'candidate-generated.pptx'),stitched=path.join(BUILD,'candidate-preserved.pptx');
await(await PresentationFile.exportPptx(p)).save(raw);
console.log(execFileSync(PY,[SUPPORT,'merge',source,raw,stitched],{encoding:'utf8'}));
if(process.argv.includes('--finalize')){
 const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
 const finalPath=path.join(ROOT,'02_outputs/ppt/RoadOps_공모전_제출기획서_20261119_v0.4_업무흐름.pptx');
 process.env.RUNTIME_NODE_MODULES='/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
 const receipt=await finalizePresentation({workspaceDir:ROOT,candidatePath:stitched,finalPath,pythonExecutable:PY,
  integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
  explicitTotalSlideCount:17,requiredNativeTableOwnerSlides:[8,14,16],requiredNativeChartOwnerSlides:[6],materializeLiteralChartWorkbooks:true,
  layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-heading-fit',...[8,14,16].flatMap(n=>['--require-native-table-slide',String(n)])],
  fontPolicy:{basis:'reference',families:[FONT,BOLD,'Poppins Bold'],referencePath:source,referenceSha256:crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex')},
  verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
 console.log(JSON.stringify(receipt));
}
console.log(JSON.stringify({candidate:stitched,evidence:path.join(BUILD,'continuous-replan.json')}));
