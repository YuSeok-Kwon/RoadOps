/** Rebuild 15-slide submission using the imported RoadOps deck and real UI captures.
 * Run normally to render a candidate. After visual review, run --finalize.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {FileBlob,PresentationFile} from '/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const ROOT=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const BUILD=path.join(ROOT,'999_Temporary/roadops_submission_15_20261120');
const OUT=path.join(ROOT,'02_outputs/ppt/RoadOps_제주데이터활용_15장_20261120');
const SOURCE=path.join(ROOT,'02_outputs/ppt/RoadOps_공모전_제출기획서_20261119_v0.4.1_이미지호환수정.pptx');
const MEDIA=path.join(ROOT,'999_Temporary/roadops_workflow_v04/source-media');
const HQ=path.join(ROOT,'02_outputs/RoadOps_PPT_고해상도_교체이미지_2026-11-19');
const NEW=path.join(OUT,'실제화면');
const DETOUR=path.join(ROOT,'02_outputs/ppt/RoadOps_14-15장_우회경로/스크린샷');
const SKILL='/Users/yu_seok/.codex/plugins/cache/openai-primary-runtime/presentations/26.1118.11504/skills/presentations';
const RUNTIME='/Users/yu_seok/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const C={ink:'#231F20',green:'#679773',highlight:'#A9BDAE',blue:'#1468B3',muted:'#7F8B95',line:'#DDE5DF',light:'#F4F7F4',white:'#FFFFFF',amber:'#B5701D'};
const FONT='프리텐다드',BOLD='프리텐다드 Bold';
await fs.mkdir(BUILD,{recursive:true}); await fs.mkdir(OUT,{recursive:true});
const evidence=JSON.parse(await fs.readFile(path.join(ROOT,'demo/jeju_inspection_evidence_v0_1.json'),'utf8'));
const capture=JSON.parse(await fs.readFile(path.join(NEW,'capture-evidence.json'),'utf8'));
if(evidence.surface_accidents.length!==96 || evidence.hub_accident_hotspots.length!==36 || evidence.designated_hazards.length!==58)throw Error('Unexpected data coverage');
if(!capture.confirmation?.inspectionPlans?.some(p=>p.actions.length===2 && p.statisticalEvidence.accidents===7218))throw Error('No real confirmation evidence');
const detourEvidence=JSON.parse(await fs.readFile(path.join(DETOUR,'capture-evidence.json'),'utf8'));
if(!detourEvidence.resultText.includes('총 100.6분')||!detourEvidence.resultText.includes('보류 0곳'))throw Error('Detour evidence mismatch');
const p=await PresentationFile.importPptx(await FileBlob.load(SOURCE));
const before=await p.inspect({select:'$.slides[*]',include:['id','index','elements.id']});
await fs.writeFile(path.join(BUILD,'source-layout.json'),JSON.stringify(before.records,null,2));
for(const row of before.records)for(const e of row.elements)p.delete(e.id);
p.slides.delete([15,16]);
if(p.slides.items.length!==15)throw Error('Must be exactly 15 slides');
const imageBytes=new Map();
async function bytes(file){if(!imageBytes.has(file))imageBytes.set(file,new Uint8Array(await fs.readFile(file)));return imageBytes.get(file);}
function text(s,value,x,y,w,h,size=34,color=C.ink,bold=false){const a=s.shapes.add({geometry:'textbox',name:value.split('\n')[0].slice(0,80),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});a.text=value;a.text.insets=0;a.text.style={typeface:bold?BOLD:FONT,fontSize:size,color,bold};return a;}
function rect(s,x,y,w,h,fill){return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:'none',width:0}});}
async function pic(s,file,x,y,w,h,fit='contain'){return s.images.add({blob:await bytes(file),contentType:'image/png',alt:path.basename(file),fit,position:{left:x,top:y,width:w,height:h}});}
async function head(n,title,sub){const s=p.slides.getItem(n-1);s.background.fill=C.white;await pic(s,path.join(MEDIA,'image3.png'),0,0,1920,1080,'cover');rect(s,83,115,Math.min(1710,title.length*49+48),38,C.highlight);text(s,title,96,78,1720,90,56,C.ink,true);if(sub)text(s,sub,100,181,1710,77,30,C.muted);text(s,`${String(n).padStart(2,'0')} / 15`,1750,1013,150,35,22,C.muted);return s;}
function foot(s,v){text(s,v,100,1009,1600,40,18,C.muted);}
function note(s,v,...sources){s.speakerNotes.text=v+'\n\n출처 및 검증 근거\n'+sources.join('\n');}
function table(s,values,x,y,w,h,widths,size=29){const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});t.borders.assign({fill:C.line,width:1,style:'solid'});for(let r=0;r<values.length;r++)for(let c=0;c<values[r].length;c++){const cell=t.getCell(r,c);cell.fill=r===0?'#E8EFE9':r%2===0?C.light:C.white;cell.text.style={typeface:r===0?BOLD:FONT,fontSize:size,color:r===0?C.green:C.ink,bold:r===0};}return t;}
function block(s,title,body,x,y,w=790,bodySize=32){text(s,title,x,y,w,56,37,C.green,true);text(s,body,x,y+70,w,150,bodySize);}
const hub=id=>`https://jejudatahub.net/data/view/data/${id}`;
const impl=path.join(ROOT,'04_docs/deployment/20261120_roadops_jeju_inspection_evidence.md');
const oldStamp='2026.11.19 17:40 저장 자료로 실행한 RoadOps 화면';

// 1: Original visual language, with a compact and complete submission identity.
{
 const s=p.slides.getItem(0);s.background.fill=C.white;
 text(s,'Road',100,48,390,126,106,C.ink,true);text(s,'Ops',367,48,315,126,106,C.green,true);
 text(s,'제주 데이터 기반 도로 점검 계획 Agent',880,93,920,56,35,C.ink,true);
 await pic(s,path.join(MEDIA,'image1.png'),0,205,1920,875,'cover');
 text(s,'어디부터 점검할지,\n상황이 바뀌면 어떻게 갈지.',110,328,1380,210,74,C.white,true);
 text(s,'제주데이터허브의 사고·재해 자료를\n현장 점검 항목과 실행 가능한 방문 계획으로 연결합니다.',116,615,1320,130,38,C.white);
 text(s,'AI Agent 기획서',116,874,850,48,30,'#DDE5DF');
 text(s,'권유석   ·   2026.11',116,937,900,60,37,C.white,true);
 note(s,'제주 도로관리 담당자의 점검 의사결정을 지원하는 현재 구현 및 후속 개발 계획. 배경은 기존 제안서의 AI 생성 도로 이미지로 실제 재난 사진이 아니다. 표지 포함 정확히 15장.',SOURCE,path.join(MEDIA,'image1.png'));
}
{
 const s=await head(2,'한 현장반이 오늘 점검할 도로를 정합니다','분석 주제는 제주 도로의 점검 우선순위와, 가용 인원·시간 안에서 가능한 방문 계획입니다.');
 await pic(s,path.join(MEDIA,'image2.png'),110,310,955,415,'cover');
 text(s,'용담 현장반 시연 조건',1138,302,650,65,41,C.green,true);
 text(s,'2명',1133,388,310,139,107,C.ink,true);text(s,'120분',1450,388,360,139,91,C.ink,true);
 text(s,'출동 인원',1143,540,300,52,32,C.muted);text(s,'이동 + 점검',1458,540,340,52,32,C.muted);
 text(s,'먼저 볼 도로는 어디인가?\n현장에서 무엇을 확인할 것인가?\n통제되면 남은 곳을 방문할 수 있는가?',1138,633,690,210,35);
 text(s,'목표',110,810,200,60,38,C.green,true);
 text(s,'자료 확인, 점검 항목 준비, 방문 순서 조정을 한 화면에서 지원합니다.',110,880,1680,75,43,C.ink,true);
 foot(s,'배경은 기존 제안서의 상황 설명용 이미지 · 2명·120분은 시연 입력값');
 note(s,'사용자: 제주 도로관리 담당자. 현장 문제: 여러 출처의 자료를 해석하고 자원 제약 안에서 첫 방문 계획을 세우며, 통제 후 남은 방문을 다시 조정해야 한다. 분석 목표는 사고 발생확률 예측이 아니라 설명 가능한 운영 우선순위, 점검 내용, 제약을 충족하는 경로다.',SOURCE);
}
{
 const s=await head(3,'제주데이터허브 5종을 실제 기능에 연결합니다','데이터명·활용 항목·확보 범위를 밝히고, 통계·좌표·행정지역 자료에 서로 다른 역할을 줍니다.');
 table(s,[['허브 데이터 / 원천','이번에 확보한 범위','활용 항목','기능에 반영'],
 ['891 노면 상태별 교통사고\nTAAS 원천','2005–2020년\n96행','연도, 노면 유형\n사고·사망·부상','조건별 통계 조회\n노면별 점검 항목'],
 ['863 교통사고 다발지역\nTAAS 원천','2017–2022년\n공개 CSV 36행','연도, 좌표, 지점명\n사고·사상자','TAAS 2025년 6행과\n연도별 지도 비교'],
 ['436 붕괴위험급경사지\n제주시','2026.06.30\n3개 지구','지역명, 위치, 등급\n추진 상황','사면·낙석 확인\n지역 참고자료'],
 ['435 자연재해위험개선지구\n제주시','2026.06.30\n55개 지구','유형, 위치, 등급\n완료 여부·해제 비고','침수·유실 등 확인\n해제 이력 제외'],
 ['1027 도로선형별 사고\n기존 활용','2018–2020년\n51행','도로 선형\n사고·사망·부상','선형별 조건부 심각도\n기존 구조위험 근거']],110,290,1690,590,[510,350,410,420],28);
 text(s,'허브 자료를 점검 내용으로 연결하고, ITS·기상청·도로망으로 이동 가능성을 검토합니다.',114,922,1690,62,33,C.green,true);
 foot(s,'435·436은 허브가 연결한 공공데이터포털 최신 원본 사용 · 863은 전체 API 수집 결과와 구분');
 note(s,'891은 첨부 원본 CSV 전체96행 중 불완전15행. 863공개CSV36행은2017–2022이며API총42행과다르다. 435·436은허브카탈로그를통해발견하고연결된최신공공데이터원본을수집했다. 1027기존51행과도로선형조건부심각도활용은기존소스계보에근거한다.',hub(891),hub(863),hub(436),hub(435),hub(1027),impl,path.join(ROOT,'04_docs/deployment/20261116_roadops_data_usage_lineage_v0_1.md'));
}
{
 const s=await head(4,'노면 통계가 도로별 점검 항목으로 이어집니다','젖음·결빙·적설 등 확인할 노면을 선택하고, 제안된 항목을 추천 순찰코스에 반영합니다.');
 await pic(s,path.join(NEW,'01_노면통계와_점검계획.png'),108,290,1120,638);
 text(s,'젖은 노면의 배수·미끄럼 점검',1285,282,510,58,33,C.green,true);
 await pic(s,path.join(NEW,'04_점검항목이_포함된_추천코스.png'),1290,364,500,505);
 text(s,'출처와 집계 기간도\n확인 기록에 보존',1290,897,510,85,31,C.ink,true);
 foot(s,'2026.11.20 실제 기능 화면 · 젖음/습기 2005–2020년 합계 · 현재 노면 관측이나 사고 발생확률이 아님');
 note(s,'노면선택을현재도로관측으로간주하지않는다. 젖음/습기사고7218건,사망226명,사고100건당3.13명은16개년합계. 결측제외와통행량분모부재를표시한다. 버튼클릭후추천코스에2개점검항목이표시되고브라우저확인기록에출처URL과기간이저장되는것을실제검증했다. 오른쪽경로는11/20갱신자료시연으로10~12장의11/19고정경로와별도다.',hub(891),path.join(NEW,'capture-evidence.json'),impl);
}
{
 const s=await head(5,'사고지점과 재해지구는 위치·시점을 구분합니다','TAAS와 허브 이력을 함께 살피고, 붕괴·침수·유실 지구에서 확인할 내용을 준비합니다.');
 text(s,'TAAS + 허브 사고다발지역',110,286,830,62,39,C.green,true);
 text(s,'붕괴위험·자연재해 지구',1000,286,790,62,39,C.green,true);
 await pic(s,path.join(NEW,'02_TAAS_허브_분석연도.png'),110,370,805,480);
 await pic(s,path.join(NEW,'03_붕괴_자연재해_목록.png'),1000,370,805,480);
 text(s,'선택 연도의 지점만 지도에 표시\n연도 간 사고건수는 합산하지 않음',114,882,805,105,32);
 text(s,'해제 44건은 기본 목록에서 제외\n정비 완료와 지정 해제를 구분',1004,882,805,105,32);
 foot(s,'재해 58건 중 미해제 표기 14건 · 좌표·경계 미제공으로 같은 행정지역 참고에 한정');
 note(s,'TAAS2025년6행+허브2017–2022년36행. 2022년허브6개중심좌표가실제지도에표시되는것을검증. 공개중심점만있는경우위험경계폴리곤을임의생성하지않았다. 재해58행:지정해제44,정비완료3,기타11. 광령리2023-05-10해제는점검자동제안에서제외한다. 정확한위치·경계없음으로지역일치를직접위험이나자동통제로변환하지않는다. 서귀포시자료로일반화하지않는다.',hub(863),hub(435),hub(436),'https://www.data.go.kr/data/15056032/fileData.do','https://www.data.go.kr/data/15056033/fileData.do',impl);
}
{
 const s=await head(6,'출처·기준일·결측을 확인한 뒤 결합합니다','원본 수집부터 화면 표시까지 자료의 범위와 처리 근거를 남깁니다.');
 const steps=[['01 수집','허브 CSV·연결 원본\nTAAS·ITS·기상청'],['02 정제','문자 인코딩·중복 검증\n빈칸은 결측으로 유지'],['03 결합','링크 ID·좌표·행정지역\n결합 정밀도를 구분'],['04 반영','점수·지도·점검 항목\n출처와 기준일 표시']];
 steps.forEach((a,i)=>{const x=110+i*435;rect(s,x,295,385,5,C.green);text(s,a[0],x,328,395,61,37,C.green,true);text(s,a[1],x,408,395,105,31);});
 table(s,[['이용·운영 조건','적용 방안'],['노면·재해 원천 공개자료','대응 공공데이터포털은 무료·이용허락범위 제한 없음'],['허브 API와 원본 재배포','전체 API는 프로젝트 인증키 확인 / 863·1027 재배포 조건 별도 확인'],['ITS·기상청·TAAS·지도','서비스별 인증키·호출량·출처 표시 유지 / API 키는 환경변수'],['품질과 갱신','수집일·기준일·파일 해시 보존 / 장애 시 저장 자료의 시각 명시']],110,574,1690,322,[465,1225],28);
 text(s,'통계의 빈칸을 0점으로, 행정지역 정보를 정확한 위험좌표로 바꾸지 않습니다.',113,937,1690,56,33,C.green,true);
 foot(s,'이용조건 확인: 2026.11.20 · 원본을 ZIP에 포함하기 전 자료별 재배포 범위를 최종 확인');
 note(s,'정규화함수는UTF8sig/CP949,음수건수·중복연도/노면·제주좌표범위를검증한다. 허브863공개CSV는전체API가아니다. API키는사용자가승인받은프로젝트키사용. 노면대응공공데이터포털15095728및재해15056032/15056033의메타데이터상license는이용허락범위제한없음. 기존1027과863허브원본재배포조건은확인과제로남긴다. OSM타일외부표시에는OSM기여자표시를유지한다. 자동갱신은기존ITS/KMA계층10분주기이며연간통계가10분마다갱신된다는뜻이아니다.',impl,'https://www.data.go.kr/data/15095728/openapi.do','https://www.data.go.kr/data/15056032/fileData.do','https://www.data.go.kr/data/15056033/fileData.do',hub(863),hub(1027));
}
{
 const s=await head(7,'Agent는 계산하고, 담당자는 실행을 결정합니다','입력 검증, 점검 대상 구성, 경로·배분 계산, 결과 검증을 도구 흐름으로 연결합니다.');
 const names=[['1 요청·조건 해석','팀·시간·대상 입력'],['2 자료 품질 확인','결측·시각·경로 검사'],['3 점검 작업 구성','우선순위·점검 항목'],['4 이동시간 검토','ITS 속도·도로망'],['5 방문 계획 계산','필수·제외·시간 제약'],['6 결과 재검증','중복·시간·경로 검사'],['7 근거와 결과 제시','담당자 검토·확정']];
 names.forEach((a,i)=>{const x=110+(i%4)*438,y=i<4?292:480;rect(s,x,y,382,5,C.highlight);text(s,a[0],x,y+26,405,58,32,C.ink,true);text(s,a[1],x,y+97,405,48,28,C.muted);});
 rect(s,110,695,1690,2,C.line);
 block(s,'현재 계산 도구','학습형 ML·LLM은 현재 미사용\n규칙 점수·방향성 최단경로\n제약을 만족하는 방문 조합 비교',110,737,545,28);
 block(s,'LLM 연동 계획','검토 모델: GPT-5.4 mini API\n요청을 구조화하고 도구 결과 설명\n현재 미연동 / 수치·경로는 도구 검증',700,737,545,28);
 block(s,'판단·자율 수행 범위','자동: 점검 항목·순서·우회 대안\n담당자: 현장 확인·보류·최종 확정\n실제 출동 지시는 자동 실행 안 함',1290,737,545,28);
 foot(s,'Python Tool 흐름 + 브라우저 운영 UI · 자연어 요청은 제한된 한국어 문법으로 처리');
 note(s,'현재 구현을 범용 LLM Agent로 과장하지 않는다. 실제 도구: request_interpreter, data_quality_gate, risk_task_builder, travel_time_gate, allocation_optimizer, plan_validator, result_explainer. 웹 UI는 동일 정책을 JS로 적용하며 입력 변경 시 재계산한다. 데이터 API는 Hub/TAAS/ITS/C-ITS/KMA다. 현재 규칙 점수·최단경로·제약 최적화를 사용하며 학습형 모델은 사용하지 않는다. 후속 검토 모델은 gpt-5.4-mini-2026-03-17(API)이다. 구조화 출력과 함수 호출로 요청을 도구 입력으로 변환하고, 검증된 통계·경로 결과를 설명한다. 프롬프트는 수치 생성 금지, 출처·기준일 포함, 불확실성 표시, 실제 출동 지시 금지를 요구한다. 필수 필드 누락 시 재질문하고 도구 검증 실패 시 확정하지 않는다. 모델 응답과 도구 결과 일치율·조건 누락률을 별도 검증할 계획이며 현재 미연동이다.',path.join(ROOT,'04_docs/agent/20261113_roadops_agent_flow_v0_1.md'),path.join(ROOT,'08_dashboard/roadops_map_v0_1/src/content/dashboard/priority-policy.js'),impl,'https://developers.openai.com/api/docs/models/gpt-5.4-mini');
}
{
 const s=await head(8,'판단 기준을 고르고, 기상 변화를 확인합니다','동일한 기준을 수동 검토와 자동 계획에 적용하고, 지금과 이후 예보를 함께 살핍니다.');
 text(s,'담당자가 정하는 8개 항목과 배점',110,286,840,60,37,C.green,true);
 await pic(s,path.join(HQ,'05장_점수항목과배점_전체_고해상도.png'),110,370,850,437);
 text(s,'점수 근거와 자료 부족을 함께 표시\n순위는 최종 방문 순서와 구분',114,861,820,107,33);
 text(s,'현재·1시간·3시간·6시간 후',1030,286,770,60,37,C.green,true);
 await pic(s,path.join(HQ,'11장_기상/04_PPT교체용_6시간후.png'),1030,362,770,503);
 text(s,'예보가 달라지면 계획을 다시 검토',1034,906,770,63,32);
 foot(s,oldStamp+' · 배점 예시는 운영 우선순위이며 사고확률이 아님');
 note(s,'기존원본화면은그대로사용했다. 8개가중치30/20/20/10/5/8/5/2및가용근거환산. 결측은안전한0으로치환하지않는다. 기상계층은예보시점과영상관측시각을구분한다. 새로운노면통계집계는이점수에임의가산하지않고점검항목추천에사용한다.',path.join(HQ,'05장_점수항목과배점_전체_고해상도.png'),path.join(HQ,'11장_기상/04_PPT교체용_6시간후.png'),impl);
}
{
 const s=await head(9,'출동 인원과 시간, 반드시 볼 곳을 입력합니다','현장반의 가용 자원과 도로별 조건이 달라지면 가능한 방문 계획을 다시 계산합니다.');
 text(s,'현장반의 가용 자원',110,287,1110,60,37,C.green,true);
 await pic(s,path.join(HQ,'추가_AI입력조건/02_출동인원과시간_입력부만.png'),110,365,1110,285);
 text(s,'도로별 담당팀과 방문 조건',110,699,1110,60,37,C.green,true);
 await pic(s,path.join(HQ,'추가_AI입력조건/03_도로별_배정조건_광령리.png'),110,765,1110,145);
 text(s,'계획에 반영되는 조건',1290,287,510,60,37,C.green,true);
 text(s,'01  인원과 시간',1290,393,510,56,35,C.ink,true);
 text(s,'이번 근무에 투입할 인원과\n이동·점검 가능 시간을 입력',1290,467,510,110,30);
 text(s,'02  방문 의무와 배정',1290,604,510,56,35,C.ink,true);
 text(s,'필수 점검, 담당팀 고정,\n제외 대상을 확인',1290,678,510,105,30);
 text(s,'03  점검 소요시간',1290,809,510,56,35,C.ink,true);
 text(s,'추가 점검 항목에 맞춰 조정',1290,877,510,48,30);
 text(s,'노면·재해 점검 항목이 늘어나면, 필요한 점검 시간도 함께 조정합니다.',114,955,1680,45,30,C.green,true);
 foot(s,oldStamp+' · 실제 기관의 근무 편제와 구분한 시연 조건');
 note(s,'출동인원·가용시간·필수대상·제외·담당팀고정의실제입력화면. 노면·재해항목은추가업무를정의하며현장소요시간을자동으로추정하지않는다. 담당자가서비스시간을검토한뒤계획을다시계산한다.',path.join(HQ,'추가_AI입력조건/01_출동인원과_가용시간.png'),path.join(HQ,'추가_AI입력조건/03_도로별_배정조건_광령리.png'),impl);
}
{
 const s=await head(10,'광령리·소길리·예래동 방문 계획을 제안합니다','2명·120분 조건에서 이동과 점검을 합친 예상시간, 방문 순서와 지도를 함께 확인합니다.');
 await pic(s,path.join(HQ,'06장_AI추천경로/03_추천경로_지도만.png'),110,294,935,646);
 await pic(s,path.join(HQ,'06장_AI추천경로/02_PPT교체용_추천순찰코스.png'),1105,296,690,429);
 text(s,'3곳',1110,785,270,106,81,C.green,true);text(s,'101.2분',1430,785,370,106,73,C.blue,true);
 text(s,'방문 대상',1116,909,270,48,31,C.muted);text(s,'이동 + 점검',1436,909,365,48,31,C.muted);
 foot(s,oldStamp+' · 통제 전 최초 계획 시연 · 현재 도로상황과 구분');
 note(s,'제출자료에서이미사용한고정시나리오를유지한다. 최초계획용담출발후광령리,소길리,예래동3곳101.2분. 다음두장의통제후신규경로는제한속도기반계산으로산정조건이달라효율개선실적으로비교하지않는다. 신규데이터기능의11/20확인시연과별도스냅샷임을명시한다.',path.join(HQ,'06장_AI추천경로/03_추천경로_지도만.png'),path.join(HQ,'06장_AI추천경로/02_PPT교체용_추천순찰코스.png'));
}
{
 const s=await head(11,'통제된 길을 피해 소길리로 가는 경로를 찾습니다','광령리 점검을 마친 뒤, 통제 구간을 제외하고 남은 이동 경로를 자동으로 다시 탐색합니다.');
 text(s,'실제 우회경로 제안 화면',110,280,1040,58,37,C.green,true);
 await pic(s,path.join(DETOUR,'01_우회경로_지도.png'),110,360,1080,612);
 text(s,'통제 조건과 완료 지점 입력',1250,280,555,60,35,C.green,true);
 await pic(s,path.join(DETOUR,'02_통제조건_자동계산.png'),1250,358,550,460);
 text(s,'통제 링크 제외\n완료한 광령리 기록 유지\n남은 방문 경로 재탐색',1256,857,550,131,32);
 foot(s,'11.19 17:40 저장 자료로 재현한 통제 가정 · 실제 RoadOps 계산 화면');
 note(s,'원본지도를확대왜곡하거나가상의우회선을추가하지않았다. 입력:용담팀2명120분,광령리까지완료,통제링크4050430101. 도로망에서통제링크를제외해최단경로를탐색한다. 실제현장통제가아닌재현시나리오이다.',path.join(DETOUR,'capture-evidence.json'),path.join(DETOUR,'01_우회경로_지도.png'),path.join(DETOUR,'02_통제조건_자동계산.png'));
}
{
 const s=await head(12,'완료한 점검을 보존하고, 소길리도 방문합니다','남은 두 곳을 방문할 수 있는 변경안을 제안하고, 담당자가 통행 가능 여부를 확인합니다.');
 await pic(s,path.join(DETOUR,'05_방문순서와_변경안확정.png'),110,292,800,646);
 text(s,'총 예상 소요시간',1035,291,755,60,37,C.green,true);
 text(s,'100.6분',1027,367,780,151,115,C.blue,true);
 text(s,'완료 39.8분 + 남은 60.8분',1041,539,760,63,36);
 text(s,'가용 120분 중 19.4분 여유',1041,638,760,72,44,C.green,true);
 rect(s,1040,749,750,2,C.line);
 text(s,'담당자 확인 후 변경안 확정',1041,789,760,60,39,C.ink,true);
 text(s,'통제·기상·점검 항목을 확인하고\n변경 사유와 후속 조치를 기록합니다.',1041,869,760,116,32);
 foot(s,'재현 시연: 완료 1곳·남은 방문 2곳·보류 0곳 · 신규 우회시간은 제한속도 기반 추정');
 note(s,'완료39.793+남은60.770=100.563분,여유19.437분. 광령리→소길리5.802분+점검15분,소길리→예래동24.968분+점검15분. 새우회는실시간혼잡및회전제한미반영. 조건이다른최초101.2와직접효율비교금지. 현재노면항목은브라우저확인기록에출처·기간과함께저장. 서버영구저장·전자결재는후속구현이며확정행위는실제출동명령이아니다.',path.join(DETOUR,'capture-evidence.json'),path.join(NEW,'capture-evidence.json'),impl);
}
{
 const s=await head(13,'검증 결과와 남은 한계를 구분합니다','집계 정확성·상태 처리·화면 동작·계획 보존을 검증했으며, 현장 효과는 별도 실증이 필요합니다.');
 table(s,[['검증 대상','이번 확인 결과','남은 검증'],['노면 통계','원본 96행 / 관련 Python 18개 통과\n젖음 7,218건·226명 재계산 일치','최신 연도 자료 확보\n노출량을 포함한 별도 분석'],['사고·재해 자료','2022년 6개 지점 지도 표시\n해제 제외 14건 / 포함 58건','허브 API 전체 범위 검증\n지구 경계·정확한 위치 확보'],['점검계획·확인 기록','관련 JavaScript 12개 통과\n추천 코스·로컬 기록에 항목 보존','서버 저장·기관 권한 연계\n사용자 검토 실험'],['대체 경로','통제 링크 제외, 완료 기록 보존\n고정 시연에서 소길리 포함 3곳 유지','회전제한·실제 통행 반영\n센터 PC·현장 환경 실증']],110,296,1690,556,[380,690,620],29);
 text(s,'아직 주장하지 않는 성과',113,897,650,56,36,C.green,true);
 text(s,'사고 감소율, 업무시간 절감률, 센터 PC 실측 성능',113,953,1650,46,32);
 foot(s,'자동 검증 30개는 이번 변경의 관련 테스트 범위 · 실제 사고 예측 정확도나 현장 효과를 뜻하지 않음');
 note(s,'pytest tests/test_jeju_inspection_evidence.py tests/test_map_snapshot.py tests/test_accident_hotspots.py tests/test_priority_policy.py:18pass. node--test jeju-inspection.test.mjs workflow-policy.test.mjs:12pass. 브라우저노면선택→점검계획반영→추천코스→확정레코드검증. 허브지도6중심점,재해필터14/58,모바일390px·다크모드확인,브라우저pageerror없음. 센터실기기성능미검증. 스냅샷은날짜가있는재현사례이며실시간안전보장아님.',impl,path.join(NEW,'capture-evidence.json'),path.join(DETOUR,'capture-evidence.json'));
}
{
 const s=await head(14,'센터 환경에서 재현하고, 연계를 확장합니다','권유석이 데이터 처리·Agent 도구·운영 UI·검증을 담당하고, 센터 환경에서 재현성을 확인합니다.');
 block(s,'현재 구현 범위','Python 데이터 처리·품질 검사\nReact/JavaScript 운영 화면\n규칙 점수·계획 계산·대체 경로',110,290,790,32);
 block(s,'센터 실행 환경','i7-8700 / RAM 32GB\nGTX 1060 / VRAM 3GB\nCPU 중심 실행, 대형 로컬 모델 불필요',1005,290,790,32);
 table(s,[['실행·외부 의존성','개발·탑재 계획'],['저장 자료 모드','검증 CSV·JSON과 웹 UI 제공 / API 키 없이 계산 재현'],['실시간 자료 모드','ITS·C-ITS·기상청 인증키·네트워크 필요 / 실패·갱신시각 표시'],['화면과 라이브러리','브라우저 + Python / httpx·pyproj·pyshp / 지도 타일은 외부 네트워크'],['LLM 연동 계획','OpenAI API 키·네트워크·사용료 필요 / 장애 시 기존 입력 화면 사용'],['탑재 순서','센터 PC 성능 검증 → API·LLM 연동 검증 → 서버 기록·기관 승인']],110,554,1690,334,[445,1245],27);
 text(s,'제출 패키지',114,912,330,49,34,C.green,true);
 text(s,'소스·도구/설정  /  README·설치·환경변수  /  데이터 명세  /  결과·검증 자료',114,960,1680,44,29);
 foot(s,'실제 센터 PC 테스트 전 · 현재 검증은 개발 환경에서 수행 · 대형 모델·GPU 학습 의존성 없음');
 note(s,'기술환경Python3.11+,브라우저JS/React,Python의존성httpx>=0.27<1,pyproj>=3.7<4,pyshp>=2.3<3;정확한목록requirements.txt. UI소스빌드는현재Data플러그인번들런타임을사용하므로센터에는검증된dist와소스·재현설명을함께제공한다. 기본저장자료계산은API키없이실행하지만OSM지도타일/신규기상영상/실시간수집에는네트워크필요. 인터넷불가시경로선및자료목록중심의오프라인모드를검증한다. 사용LLM모델현재없음. 범용LLM요청해석·설명연동은후속선정과제이며본제출에완료된것으로표시하지않는다. 참가자권유석역할:기획·데이터·Tool구현·UI·테스트. 센터담당자역할:실행환경·키·기관정책검토,현장담당자역할:현장확인·계획확정. ZIP은기획서와별도산출물로소스,README,환경변수예시,의존성,사용자매뉴얼,데이터출처/이용조건,분석흐름,검증/한계를포함한다.',path.join(ROOT,'requirements.txt'),path.join(ROOT,'04_docs/deployment/20261116_roadops_center_environment_validation_v0_1.md'),path.join(ROOT,'08_dashboard/roadops_map_v0_1/AGENTS.md'),impl);
}
{
 const s=p.slides.getItem(14);s.background.fill=C.white;await pic(s,path.join(MEDIA,'image1.png'),0,0,1920,1080,'cover');
 text(s,'RoadOps',110,70,700,130,99,C.white,true);
 text(s,'첫 출동의 순서부터,\n상황이 바뀐 뒤의 판단까지.',110,355,1580,250,81,C.white,true);
 rect(s,114,650,180,7,C.highlight);
 text(s,'제주 데이터를 현장의 점검 계획으로.',114,716,1350,77,43,'#DDE5DF');
 text(s,'권유석',114,933,900,72,44,C.white,true);
 text(s,'제주 도로관리 운영 보조 Agent',114,1005,1300,43,27,'#DDE5DF');
 note(s,'마무리핵심메시지보존. 보조문구는담당자검토설명의반복을제거하고데이터활용의가치한줄로정리했다. 센터활용은저장자료시나리오교육과계획비교,통제후재계획검토부터시작한다. 기존의AI생성도로배경재사용이며실제재난사진이아니다.',SOURCE,path.join(MEDIA,'image1.png'));
}

await (await PresentationFile.exportPptx(p)).save(path.join(BUILD,'candidate.pptx'));
for(let i=0;i<15;i++){const blob=await p.export({slide:p.slides.getItem(i),format:'png',scale:1});await fs.writeFile(path.join(BUILD,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));console.log(`Rendered ${i+1}/15`);}
await fs.writeFile(path.join(BUILD,'inspection.json'),JSON.stringify((await p.inspect({select:'$.slides[*]',include:['index','elements.text','elements.position']})).records,null,2));
console.log(JSON.stringify({candidate:path.join(BUILD,'candidate.pptx'),previews:BUILD}));
if(process.argv.includes('--finalize')){
 process.env.RUNTIME_NODE_MODULES=path.join(RUNTIME,'node/node_modules');
 const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
 const receipt=await finalizePresentation({workspaceDir:ROOT,candidatePath:path.join(BUILD,'candidate.pptx'),finalPath:path.join(OUT,'RoadOps_공모전_기획서_15장_20261120.pptx'),pythonExecutable:path.join(RUNTIME,'python/bin/python3'),integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),explicitTotalSlideCount:15,requiredNativeTableOwnerSlides:[3,6,13,14],requiredNativeChartOwnerSlides:[],layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-heading-fit',...([3,6,13,14].flatMap(n=>['--require-native-table-slide',String(n)]))],fontPolicy:{basis:'reference',families:[FONT,BOLD],referencePath:SOURCE,referenceSha256:crypto.createHash('sha256').update(await fs.readFile(SOURCE)).digest('hex')},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
 console.log(JSON.stringify(receipt));
}
