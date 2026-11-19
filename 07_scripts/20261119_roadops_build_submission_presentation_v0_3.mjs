/** RoadOps 17-slide implementation-aligned revision.
 * Shared callback for live Artifact Sessions and an imported PPTX fallback.
 * input: {slides, assetDir, evidence, captures?: {[slideNumber]: absolutePath}}
 * Captures are deliberately supplied by the user. No UI screenshots are fabricated.
 */
const C={black:'#231F20',blue:'#1468B3',green:'#8CC63F',gray:'#88929C',muted:'#9DA6AE',foot:'#AFB6BD',pale:'#F7F9FB',header:'#E8F2FA',line:'#DEE7EE',white:'#FFFFFF'};
const ROOT='08_dashboard/roadops_map_v0_1/src/content/dashboard/';
const EVIDENCE='04_docs/presentation/assets/roadops_submission_20261119/implementation_evidence.json';
let imageSources={};
function imageSource(path){return imageSources[path]?{dataUrl:imageSources[path]}:{path};}
function txt(s,v,x,y,w,h,z=25,c=C.black,b=false,f='Pretendard'){
 const q=s.shapes.add({geometry:'textbox',name:v.slice(0,50),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 q.text=v;q.text.insets=0;q.text.style={typeface:f,fontSize:z,color:c,bold:b};return q;
}
function scene(s,path,alt,position){s.images.add({...imageSource(path),alt,fit:'cover',position});}
function pic(s,path,x,y,w,h){s.images.add({...imageSource(path),alt:path.split('/').pop(),fit:'contain',position:{left:x,top:y,width:w,height:h}});}
// Native PPT image cropping keeps the original screenshot pixels embedded and editable.
function cropPic(s,path,source,box){
 const [sw,sh,x,y,w,h]=source;
 s.images.add({...imageSource(path),alt:path.split('/').pop()+' · 원본 화면 일부 확대',fit:'cover',position:{left:box[0],top:box[1],width:box[2],height:box[3]},crop:{left:x/sw,top:y/sh,right:(sw-x-w)/sw,bottom:(sh-y-h)/sh}});
}
function page(p,a,n,t,sub='',dark=false){
 const s=p.slides.getItem(n-1);s.background.fill=dark?C.black:C.white;
 if(!dark&&n!==1)scene(s,a+'/14_roadops_route_background_v2.png','공통 장식: 옅은 회색 도로선, 파랑·초록 점. 실제 도로망이나 운영 데이터가 아닙니다.',{left:0,top:0,width:1280,height:720});
 if(t)txt(s,t,64,52,1148,99,42,dark?C.white:C.black,true);
 if(sub)txt(s,sub,66,153,1145,54,21,dark?'#CCD9E5':C.gray);
 if(t)number(s,n,dark);return s;
}
function number(s,n,dark=false){txt(s,String(n).padStart(2,'0')+' / 17',1105,674,112,22,12,dark?'#BFCAD4':C.foot,false,'Poppins');}
function src(s,v,dark=false){txt(s,v,66,673,1015,26,11,dark?'#B7C1CB':C.foot);}
function note(s,v,...refs){s.speakerNotes.text=v+'\n\n근거 자료\n'+refs.join('\n');}
function rect(s,x,y,w,h,fill,line=C.line){s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:line,width:1}});}
function capture(s,input,n,title,detail,x=66,y=218,w=1148,h=354){
 if(input.captures?.[n])return pic(s,input.captures[n],x,y,w,h);
 rect(s,x,y,w,h,C.pale);
 txt(s,'새 화면 삽입 · '+String(n).padStart(2,'0'),x+26,y+25,w-52,34,19,C.blue,true);
 txt(s,title,x+26,y+Math.max(78,h*.32),w-52,90,w<450?25:31,C.black,true);
 txt(s,detail,x+26,y+h-82,w-52,65,w<450?17:21,C.gray);
}
function pair(s,left,right,y=598){txt(s,left,74,y,542,62,23,C.black,true);txt(s,right,658,y,548,62,23,C.blue,true);}
function tab(s,values,x,y,w,h,widths,z=23){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
 t.borders.assign({fill:C.line,width:.7,style:'solid'});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[r].length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?C.header:r%2===0?C.pale:C.white;
  cell.text.style={typeface:'Pretendard',fontSize:z,color:r===0?C.blue:C.black,bold:r===0};
 }return t;
}
function capturedSlide(p,a,n,input){
 const q=input.captures;let s;
 const ref='04_docs/presentation/assets/roadops_submission_20261119/captures/';
 const stamp='운영 자료 2026.11.19 17:40 KST 고정 · 사용자 제공 실제 화면';
 switch(n){
 case 4:
  s=page(p,a,n,'거점 주변의 우선 검토 도로를 고릅니다','용담 거점의 주변 상황을 확인하고, 도로별 ‘점수 근거’를 눌러 판단 근거로 들어갑니다.');
  cropPic(s,q[4],[3200,2400,1658,445,1456,580],[66,214,1148,457]);
  src(s,stamp+' · 주변 상황·우선 검토 도로 영역 확대');
  note(s,'전체 캡처의 오른쪽 주변 상황/우선 검토 도로 영역을 원본 픽셀 변경 없이 확대했다. 첫 후보 평화로46.1점과 점수 근거+ 진입이 보인다. 펼친 상세 기여는7장에서 네이티브 막대로 보여준다. 거점은 용담이며 지도 전체를 축소해서 넣지 않았다.',ref+'01_거점_주변현황_전체.png',ROOT+'DashboardContent.jsx');return true;
 case 5:{
  s=page(p,a,n,'어떤 근거를 얼마나 볼지는 담당자가 정합니다','8개 항목의 포함 여부·배점·자료 부족 처리 방식을 직접 설정합니다.');
  const cells=[[40,238],[818,238],[1596,238],[2372,238],[40,495],[818,495],[1596,495],[2372,495]];
  cells.forEach(([x,y],i)=>cropPic(s,q[5],[3170,1124,x,y,756,112],[74+(i%2)*584,220+Math.floor(i/2)*88,548,81]));
  cropPic(s,q[5],[3170,1124,40,766,620,80],[74,580,520,67]);
  txt(s,'수동·AI 공통 기준\n초기 배점은 직접 바꿀 수 있습니다.',660,582,548,72,24,C.blue,true);
  src(s,stamp+' · 같은 설정 패널의 조작부를 확대 배치 · 배점 합계 100');
  note(s,'원본 설정 패널의8개 항목 제목/포함 체크/배점 입력 및계산방식 선택 부분을 각각네이티브이미지crop으로확대했다. 화면의값은편집하지않았다. 실제UI전체배치와는다른발표용확대배치다.30/20/20/10/5/8/5/2는이번예시의설정이며고정공식/항목별최대점수가아니다. AI는배점을바꾸지않는다.',ref+'02_점수_항목과_배점_설정.png',ROOT+'priority-policy.js');return true;}
 case 6:
  s=page(p,a,n,'가용 자원을 입력하면 방문 계획을 제안합니다','담당자가 정한 기준에 현장반·가용시간과 도로별 배정 조건을 더합니다.');
  txt(s,'용담 거점 시연',75,225,355,43,28,C.blue,true);
  txt(s,'2명 · 120분',75,279,355,68,41,C.black,true);
  txt(s,'3곳 점검',75,384,355,63,40,C.blue,true);
  txt(s,'이동 56.2분\n이동 + 점검 101.2분',78,467,350,100,29);
  cropPic(s,q[6],[3170,1936,2182,32,932,580],[497,214,716,445]);
  src(s,stamp+' · 선택한 한 현장반의 제안 결과 · 전체 3팀 비교실험과 별도 입력');
  note(s,'사용자캡처11의추천안에서3곳,이동56.2분,총101.2분을확인했다. 방문순서는제주시애월읍광령리평화로인근→소길리평화로인근→서귀포시예래동1100로1555. 입력조건은별도캡처09의2명120분,캡처10의도로별담당팀/확인순서/고정/제외조작이다. 수치는기존93.3분을대체한다. 원본추천순찰코스패널을확대했으며전체도로망의새경로탐색이나실제출동효과를주장하지않는다.',ref+'09_AI_출동인원과_가용시간.png',ref+'10_AI_도로별_배정조건.png',ref+'11_AI_추천경로와_방문순서.png',ROOT+'web-optimizer.js');return true;
 case 7:{
  s=page(p,a,n,'설정한 배점이 실제 도로에서 어떻게 쓰였는지 봅니다','담당자는 평화로의 산정 근거를 펼쳐, 설정 배점과 실제 기여점수를 비교합니다.');
  txt(s,'담당자의 설정',75,225,347,40,27,C.blue,true);
  cropPic(s,q[7],[3170,1124,40,238,756,112],[74,284,354,53]);
  cropPic(s,q[7],[3170,1124,1596,495,756,112],[74,383,354,53]);
  txt(s,'8개 항목 합계 100\n확인된 근거로 환산',78,475,346,77,25);
  txt(s,'평화로 · 화면에 표시된 실제 기여점수',472,222,735,39,25,C.blue,true);
  const rows=[['현재 도로 위험',22.6],['사고·도로 구조',6],['기상·노면',8.6],['실시간 교통',3.8],['사고다발지역',0],['과거 유사상황',5.2]];
  s.charts.add('bar',{position:{left:452,top:263,width:758,height:269},categories:rows.map(r=>r[0]),series:[{name:'화면 기여점수(반올림)',values:rows.map(r=>r[1]),fill:C.blue,points:rows.map((r,i)=>({idx:i,fill:i===5?C.green:C.blue}))}],barOptions:{direction:'bar',gapWidth:65},hasLegend:false,dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.0',textStyle:{typeface:'Poppins',fontSize:18}},xAxis:{textStyle:{typeface:'Pretendard',fontSize:20}},yAxis:{textStyle:{typeface:'Poppins',fontSize:15},majorGridlines:{fill:C.line,width:1}},chartFill:C.white,plotAreaFill:C.white});
  txt(s,'화면의 최종 점수 46.1점 · 근거 반영률 93%',474,542,731,41,26,C.blue,true);
  txt(s,'확인된 근거로 환산하므로 설정 배점은 항목별 최대 점수가 아닙니다.',75,592,1130,39,24,C.black,true);
  txt(s,'공항 유입·생활안전: 자료 없음  /  사고다발지역: 확인된 0  /  막대는 반올림된 표시값',75,634,1130,31,19,C.gray);
  src(s,stamp+' · 표시값의 합과 원계산값을 반올림한 최종 점수에는 차이가 있을 수 있음');
  note(s,'원본03의화면표시값을네이티브차트로옮겼다. 항목표시합계는46.2이나원계산합계의반올림표시는46.1로,반올림오차를보정한다고어떤항목도변경하지않았다. 자료없는공항/생활안전은0으로그리지않았다. 왼쪽은같은설정패널의현재도로위험30/과거유사상황5를확대한원본조작부다. 중앙로25.191은별도검산부록에만남긴다.',ref+'02_점수_항목과_배점_설정.png',ref+'03_도로별_점수_산정근거.png','04_docs/presentation/assets/roadops_submission_20261119/capture_usage.json');return true;}
 case 8:
  s=page(p,a,n,'과거 자료가 오늘의 점검에 주는 단서를 확인합니다','제주데이터허브 도로 선형별 사고 자료를 구조 지수에 반영하고, 주변·유사상황을 함께 봅니다.');
  pic(s,q[8],66,218,1148,366);
  pair(s,'주변 1km 사고다발지역\n구조 지수와 겹치는 부분은 차감','같은 도로·유사도·시점 조건 적용\n표시된 모든 기록을 점수로 쓰지는 않음',597);
  src(s,stamp+' · 화면에 보이는 최근 기록 전체가 점수에 들어가지는 않습니다.');
  note(s,'실제과거유사상황화면.24시간이전~90일이내,유사도80%이상,근거반영률0.6이상,같은도로의유효사건자료를하루한번센다. 화면의최근수집기록이모두반영되는것은아니다. 사고다발자료는1km내거리감쇠×사고건수/40이며구조지수와중복차감. 필수제주데이터허브ID1027의51행/37,087링크상세는부록에보존했다.',ref+'05_과거_유사상황_사건장소.png',ref+'04_교통사고다발지역_상세.png','05_src/roadops/context_priority.py');return true;
 case 9:
  s=page(p,a,n,'범죄주의 지도와 생활안전 점수는 따로 읽습니다','담당자는 제주시 도심의 과거 분포를 참고하고, 시 단위 순찰 수요를 구분해 봅니다.');
  cropPic(s,q[9],[1858,1284,0,244,1858,1040],[66,229,760,425]);
  txt(s,'지도 · 2025년 자료',872,227,341,43,27,C.blue,true);
  txt(s,'도로 구간별 주의등급\n노랑 → 빨강일수록 주의',874,283,337,95,25);
  txt(s,'점수 · 별도 시 통계',872,429,341,43,27,C.blue,true);
  txt(s,'강력·절도·폭력 건수 비중\n지도 색상을 점수로\n변환하지 않습니다.',874,486,337,132,24);
  src(s,'생활안전지도·경찰청 범죄주의구간(전체), 2025 · 지도 재조회 2026.11.19 17:48:55 KST · © OpenStreetMap contributors');
  note(s,'사용자제공범죄주의지도는별도캡처용사본에서재조회성공한자료이며운영data.json덮어쓰기가아니다. 지도범례와OSM출처를포함해원본을확대했다. 지도색상은과거분포에따른주의등급이며미래발생확률이아니다. 점수는별도시단위강력/절도/폭력건수비중으로동일시도로에동일적용한다. 도로별위험이나인구당발생률이아니다.',ref+'07_제주시_범죄주의_상세지도.png',ref+'06_생활안전_자료설명.png',EVIDENCE);return true;
 case 10:
  s=page(p,a,n,'근거가 부족할 때의 계산 방식도 담당자가 정합니다','같은 도로·같은 배점에서도 자료 부족 처리 방식에 따라 점수 제공 여부가 달라집니다.');
  txt(s,'확인된 근거로 100점 환산',76,226,539,51,31,C.blue,true);
  txt(s,'근거 반영률 60% 이상이면 산정\n도로 관련 근거가 필요합니다.',78,289,530,81,24);
  txt(s,'캡처의 평화로 46.1점',78,386,540,65,39,C.blue,true);
  txt(s,'선택한 근거가 모두 있어야 산정',656,226,550,51,30,C.blue,true);
  txt(s,'계산 대상 근거가 모두 있어야 산정\n하나라도 부족하면 점수를 보류합니다.',658,289,548,81,24);
  txt(s,'이 조건에서는 산정 보류',658,386,548,65,37,C.black,true);
  tab(s,[['자료 없음','확인된 0','설정에서 제외','해당 없음'],['미확인 근거\n확인된 0과 구분','확인된 자료에\n따른 결과 0','담당자가\n선택하지 않은 항목','그 도로의 유형에\n적용되지 않는 항목']],74,485,1132,119,[283,283,283,283],22);
  txt(s,'캡처의 공항 유입·생활안전은 자료 없음입니다. 사고다발지역 0점은 확인된 근거입니다.',77,619,1128,44,23,C.black,true);
  src(s,stamp+' · 화면의 근거 반영률 93% · 완전 근거 방식의 판정은 현재 계산 규칙에 따른 설명');
  note(s,'같은평화로화면에공항/생활안전미확인,사고다발0,근거93%가표시된다. complete는100%를요구하므로이입력을보류한다는코드기반해석이다. complete화면을별도로촬영한것처럼표현하지않는다. 별도중앙로고정입력으로두구현의계산일치도검산해부록에보존했다.',ref+'03_도로별_점수_산정근거.png',ROOT+'priority-policy.js',EVIDENCE);return true;
 case 11:
  s=page(p,a,n,'지금과 1·3·6시간 뒤의 기상을 비교합니다','담당자는 시점을 전환해 첫 점검과 후속 점검에서 다시 볼 구간을 살핍니다.');
  pic(s,q[11],66,205,520,468);
  txt(s,'6시간 후 · 23시 예보 화면',636,220,574,44,29,C.blue,true);
  txt(s,'기온 1–9°C\n시간당 예상 강수량 0–1mm',639,284,566,89,29);
  txt(s,'현재 · 1시간 · 3시간 · 6시간',638,408,570,43,27,C.blue,true);
  txt(s,'오른쪽 시점 목록에서\n기상과 후보 도로를 함께 전환합니다.',641,461,565,83,25);
  txt(s,'현재 점수 버전의 후행 표본\n1시간 0건 · 3시간 0건 · 6시간 0건',641,567,565,76,25,C.black,true);
  src(s,'2026.11.19 17:40 KST 고정 검증 · 예측 정확도 판단 보류 · 기상청 API허브 · 원본 예보/강수 영상의 시각은 별도 표시');
  note(s,'6시간후기상화면08d를대표로사용했다. 현재/1h/3h원본도캡처자료에보존. 상단기상예보유효시각23:00,강수영상표제23:10,앱뱃지23:15는서로다른표시이므로동일시각이라주장하지않는다. 기상자료와점수검증은별도이다. 현재점수버전df2eb24e3aa2만필터한후행표본0/0/0이며정확도판단보류다.',ref+'08d_기상_6시간후.png',EVIDENCE);return true;
 case 15:
  s=page(p,a,n,'변경한 조건과 방문 순서를 검토한 뒤 확정합니다','별도 웹 시연: 담당자가 미배정 3곳을 이번 계획에서 제외하고, 확인 절차를 거쳐 확정했습니다.');
  cropPic(s,q[15],[1776,994,0,0,1776,125],[66,216,1148,81]);
  txt(s,'검토한 방문 순서: 광령리 → 소길리 → 예래동 1100로',75,316,1130,43,26,C.blue,true);
  cropPic(s,q[15],[1776,994,0,574,1776,420],[66,376,1148,271]);
  src(s,'2026.11.19 별도 웹 시연 · 승인 기록 17:51:44 KST · 실제 출동 지시 아님 · 저장 통제 What-if와 동일 실행이 아닙니다.');
  note(s,'실제확정완료캡처13의상태와확인자/메모/승인기록을원본값변경없이확대했다. 방문순서는캡처11의3개목록을본문으로옮겼다. 메모는미배정3곳제외/가용시간내3곳선택/실제출동아님을명시한다. 캡처14에서자원변경0/업무변경3및검증처리기록도확인된다. 이는앞장의통제시뮬레이션과별도웹실행이다. 브라우저로컬기록이며서버전자결재와구분한다.',ref+'11_AI_추천경로와_방문순서.png',ref+'13_담당자_확정완료_시연.png',ref+'14_계획변경_처리기록.png');return true;
 default:return false;
 }
}
export async function writeRoadOpsStory({presentation:p,input}){
 if(p.slides.items.length!==17)throw new Error('The source must have exactly 17 slides.');
 const a=input.assetDir,e=input.evidence;
 const shots=input.captures||{};
 const closure=e.replanning.scenarios.find(r=>r.scenario.scenario_type==='road_closure');
 const forecast=e.forecast_validation_current_version.metrics.filter(r=>r.horizon_hours>0);
 // Several captions describe this exact frozen case. Never silently mix fresh data with them.
 if(e.snapshot_at!=='2026-11-19T17:40:14.240939+09:00'
   ||e.score_version!=='roadops-operator-priority-v0.2:df2eb24e3aa2'
   ||e.selected_road_result.score!==25.191||e.selected_road_complete_result.score!==null
   ||forecast.length!==3||forecast.some(r=>r.matched_points!==0)
   ||JSON.stringify(closure?.affected_team_ids)!=='["team-east"]'){
  throw new Error('Evidence changed: update the linked captions, validation figures and replan narrative together.');
 }
 imageSources=input.imageSources||{};
 const existing=(await p.inspect({kind:'textbox,shape,image,table,chart',maxChars:250000})).records;
 const selected=new Set(input.slides.map(n=>n-1));
 const ids=existing.filter(r=>selected.has(r.slideIndex)).map(r=>r.id);
 if(ids.length)p.delete(ids);
 const time='2026.11.19 17:40 KST';
 for(const n of input.slides){let s;
 if([4,5,6,7,8,9,11,15].every(k=>shots[k])&&capturedSlide(p,a,n,input))continue;
 switch(n){
 case 1:
  s=page(p,a,n,'');
  txt(s,'RoadOps',64,69,640,141,102,C.black,true,'Poppins');
  txt(s,'담당자의 판단 기준으로\n제안하는 현장계획',720,102,500,111,34,C.black,true);
  scene(s,a+'/09_jeju_road_original_cover_v1.png','AI 생성 상황 재현 이미지. 실제 제주 장소·사건을 촬영한 사진이 아닙니다.',{left:0,top:278,width:1280,height:372});
  txt(s,'기준은 담당자가 정하고,\nAI는 실행 가능한 계획을 제안합니다',68,359,850,126,35,C.white,true);
  src(s,'제출 기획서 · 2026.11.19 v0.3 · AI 생성 상황 재현 이미지');number(s,n);
  note(s,'17장 개정본. 담당자가 항목 포함 여부·배점·자료 부족 처리 방식을 정한다. 수동·AI 모드에 동일하게 적용되며 AI가 기준을 임의로 바꾸지 않는다. 사진은 실제 운영 실적이 아닌 생성 이미지다. 표지에는 공통 도로 장식을 적용하지 않았다.',ROOT+'priority-policy.js','04_docs/presentation/assets/roadops_submission_20261118/generated_visuals.json');break;
 case 2:
  s=page(p,a,n,'비가 쏟아지면, 무엇을 기준으로 판단할까요?');
  scene(s,a+'/12_roadops_control_room_v1.png','가상의 도로관리 상황실 담당자. AI 생성 장면으로 실제 기관·인물·RoadOps 화면이 아닙니다.',{left:64,top:215,width:565,height:414});
  txt(s,'같은 상황에서도\n업무의 기준은 다릅니다.',682,252,527,133,39,C.black,true);
  txt(s,'담당자가 중요하게 볼 근거를 정하면,\nRoadOps가 점검 우선순위와\n현장계획으로 연결합니다.',684,455,523,146,27,C.blue,true);
  src(s,'AI 생성 · 상황 재현 이미지 · 실제 기관·인물·운영 화면이 아닙니다.');
  note(s,'현장 업무를 시작하는 담당자 중심 장면. 기준 설정의 주체는 사람이며 AI는 입력 기준과 가용 자원에 따라 작업안을 제안한다. 기준을 자동 학습하거나 자동 변경한다고 주장하지 않는다.',ROOT+'ScoringPolicyPanel.jsx');break;
 case 3:
  s=page(p,a,n,'담당자는 기준과 자원을 정하고 계획을 검토합니다','폭우가 예보된 날의 점검 계획을 따라가는 운영 시뮬레이션입니다.');
  txt(s,'판단 기준 설정 → 근거 확인\nAI 계획 제안 → 담당자 확정',76,234,665,114,34,C.black,true);
  txt(s,'시연 가정',80,384,460,40,24,C.blue,true);
  [['3','개 현장반',76],['3','대 차량',295],['2','시간',514]].forEach(([v,l,x])=>{txt(s,v,x,425,174,100,80,C.blue,true,'Poppins');txt(s,l,x+3,530,180,43,25,C.black,true);});
  pic(s,a+'/15_roadops_planning_illustration_v1.png',748,233,460,350);
  txt(s,'실제 기관 편제·출동 실적이 아닌 가정 자원으로 계획을 검토합니다.',78,610,1120,49,26,C.black);
  src(s,'AI 생성 개념도 · 실제 제주 도로 경로·팀별 배분 결과가 아닙니다.');
  note(s,'3반·3대·2시간은 시연 가정. 실제 기관 자원·승인 규정과 현장 실증은 별도 확인이 필요하다. 12장의 과거 비교실험, 13–14장의 저장 What-if, 15장의 웹 시연은 각각 입력과 실행이 다르다.','PROJECT_BRIEF.md');break;
 case 4:
  s=page(p,a,n,'우선 검토 도로를 눌러 점수의 근거를 펼칩니다','담당자는 출발 거점과 주변 상황을 살핀 뒤, 점수가 어떤 근거에서 나왔는지 확인합니다.');
  capture(s,input,n,'거점 선택 → 우선 검토 도로 → 점수 근거 펼침','도로명·관측 시각·항목별 기여점수가 함께 보이는 실제 화면');
  pair(s,'도로의 위치와 현재 상황을 함께 확인','점수만 보지 않고 항목별 근거를 펼쳐 확인');
  src(s,'화면 캡처 교체 예정 · 캡처 기준 시각과 자료 상태는 화면 원문을 유지');
  note(s,'새 캡처: 거점 선택 후 우선 검토 도로 하나를 클릭하고 PriorityScoreDetail을 펼친다. 지도 전체보다 도로명·근거 행을 읽을 수 있도록 해당 영역을 크게 자른다. 가능하면 7장과 같은 중앙로 4050005521을 사용한다. 현재의 17:40 고정 수치와 나중 캡처의 숫자는 다를 수 있다.',ROOT+'DashboardContent.jsx');break;
 case 5:
  s=page(p,a,n,'어떤 근거를 얼마나 볼지는 담당자가 정합니다','8개 항목의 포함 여부·배점·자료 부족 처리 방식을 직접 설정합니다.');
  capture(s,input,n,'점수에 넣을 항목과 배점 · 8개 항목 전체','포함 여부·배점 합계·두 계산 방식이 보이는 설정 패널',66,218,1148,372);
  pair(s,'설정한 기준을 수동·AI 모드가 함께 사용','AI는 담당자가 정한 배점을 임의로 바꾸지 않음',605);
  src(s,'현재 구현: priority-policy.js · ScoringPolicyPanel.jsx · 초기 배점은 편집 가능한 설정 예시');
  note(s,'8개 항목: 현재 도로 위험상황, 과거 사고·도로 구조, 기상·노면 상태, 실시간 교통, 공항 유입, 주변 사고다발지역, 과거 유사상황, 생활안전 순찰 수요. 선택 항목 배점 합계는 100이며 도로 관련 항목이 하나 이상 필요하다. 30/20/20/10/5/8/5/2는 이번 고정 예시에 사용한 초기 설정이며 고정 공식이나 항목별 최대 기여점수가 아니다.',ROOT+'priority-policy.js',ROOT+'ScoringPolicyPanel.jsx');break;
 case 6:
  s=page(p,a,n,'가용 자원을 입력하면 방문 계획을 제안합니다','담당자가 정한 기준에 현장반·차량·시간과 작업 조건을 더합니다.');
  capture(s,input,n,'자원 입력 후 AI 계획 제안 결과','방문 순서·이동 및 점검 시간·가용 자원·제약 검사 결과가 보이는 화면');
  pair(s,'가용시간 안에 가능한 작업과 순서를 검토','최신 시연 결과의 장소 수·시간을 화면으로 확인');
  src(s,'작업 생성 → 저장 경로 후보 확인 → 배분 → 제약 검사 → 설명 · 새 도로 경로 탐색은 후속 범위');
  note(s,'기존 3곳·93.3분 수치는 삭제했다. 캡처 결과가 없는 상태에서 새 수치를 추정하지 않는다. 웹 최적화기는 저장된 경로 후보에 자원·고정·제외·우선순위·기관 제약을 적용하는 브라우저 계산이다. 범용 LLM이나 실시간 전체 도로망 탐색을 수행한다고 설명하지 않는다.',ROOT+'web-optimizer.js',ROOT+'DashboardContent.jsx');break;
 case 7:{
  s=page(p,a,n,'설정한 배점이 실제 도로에서 어떻게 쓰였는지 봅니다','담당자는 추천 후보의 항목별 기여점수를 확인합니다. 설정 배점과 결과 점수는 다릅니다.');
  capture(s,input,n,'같은 배점 설정 화면','30·20·20·10·5·8·5·2\n이번 예시의 편집 가능한 설정',70,226,352,307);
  txt(s,'중앙로 · 실제 항목별 기여점수',472,222,735,39,25,C.blue,true);
  const label={structural:'사고·도로 구조',weather_road:'기상·노면',traffic:'실시간 교통',accident_hotspot:'사고다발지역',similar_history:'과거 유사상황',city_safety:'생활안전 수요'};
  const rows=e.selected_road_result.factors.filter(r=>r.contribution!==null);
  s.charts.add('bar',{position:{left:452,top:263,width:758,height:269},categories:rows.map(r=>label[r.key]),series:[{name:'실제 기여점수',values:rows.map(r=>r.contribution),fill:C.blue,points:rows.map((r,i)=>({idx:i,fill:r.key==='city_safety'?C.green:C.blue}))}],barOptions:{direction:'bar',gapWidth:65},hasLegend:false,dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.000',textStyle:{typeface:'Poppins',fontSize:18}},xAxis:{textStyle:{typeface:'Pretendard',fontSize:20}},yAxis:{textStyle:{typeface:'Poppins',fontSize:15},majorGridlines:{fill:C.line,width:1}},chartFill:C.white,plotAreaFill:C.white});
  txt(s,'합계 '+e.selected_road_result.score.toFixed(3)+'점 · 근거 반영률 92.9%',474,542,731,41,26,C.blue,true);
  txt(s,'확인된 근거로 환산하므로 설정 배점은 항목별 최대 점수가 아닙니다.',75,592,1130,39,24,C.black,true);
  txt(s,'도로 위험상황: 해당 없음  /  공항 유입: 자료 없음  /  사고다발·유사상황: 확인된 0',75,634,1130,31,19,C.gray);
  src(s,time+' 고정 예시 · 현재 시점 · link 4050005521 · 점수는 사고 발생확률이 아닙니다.');
  note(s,'수치 근거: '+EVIDENCE+'. 생성 시각 '+e.selected_road.generated_at+', 목표 시각 '+e.selected_road.target_at+', 버전 '+e.score_version+'. 실제 기여점수는 구조 2.153846, 기상 12.307692, 교통 8.461538, 사고다발 0, 유사상황 0, 생활안전 2.267998. 적용 대상 배점 70 중 관측 가중치 65이므로 65/70=92.8571%. 해당 없음(도로 위험상황 30)은 분모 제외, 자료 없음(공항 5)은 미확인이다. 막대에는 자료 없음/해당 없음을 0으로 그리지 않았다. 생활안전 설정 2와 기여 2.268의 차이는 환산 때문이다. 캡처가 다른 시점이면 이 고정 예시와 구분해서 표시하거나 근거 JSON을 다시 동결해 모든 수치를 함께 갱신해야 한다.',EVIDENCE,ROOT+'priority-policy.js');break;}
 case 8:
  s=page(p,a,n,'과거 자료가 오늘의 점검에 주는 단서를 확인합니다','제주데이터허브 도로 선형별 사고 자료를 구조 지수에 반영하고, 주변·유사상황을 함께 봅니다.');
  capture(s,input,n,'과거 유사상황 · 사건 장소와 조건 설명','과거 자료의 기준일·유사도·기록 장소가 보이는 화면',66,218,1148,325);
  txt(s,'사고다발지역',75,565,535,37,25,C.blue,true);
  txt(s,'주변 1km의 사고 자료를 확인하고\n과거 사고·도로 구조와 겹치는 지수는 차감',75,608,535,58,21);
  txt(s,'과거 유사상황',658,565,548,37,25,C.blue,true);
  txt(s,'같은 도로·유사도·기록 시점 조건을 충족한 자료만 반영\n지도에 보이는 모든 기록이 점수에 들어가지는 않음',658,608,548,58,20);
  src(s,'제주데이터허브 도로 선형 자료는 과거 사고·도로 구조의 근거로 사용 · 원천 집계·결합 상세는 별도 근거 문서');
  note(s,'사고다발지역은 1km 이내 거리감쇠×사고건수/40(최대1)이며 구조 지수와 겹친 부분을 차감한다. 유사상황은 24시간 이전~90일 이내, 같은 도로, 유사도80% 이상, 근거 반영률0.6 이상, 유효한 과거 사건 자료를 하루 한 번만 센다. 생활안전 자료 사용은 다음 장에서 지도와 시 단위 점수를 분리해 설명한다. 제주데이터허브 ID1027 원천51행과 링크37,087개는 별도 근거 문서에 이동했다. 구조위험 상한25점이라는 옛 표현은 제거했다.','05_src/roadops/context_priority.py',ROOT+'priority-policy.js');break;
 case 9:
  s=page(p,a,n,'범죄주의 지도와 생활안전 점수는 따로 읽습니다','담당자는 제주시 도심의 과거 범죄 분포를 참고하면서, 시 단위 순찰 수요를 구분해 봅니다.');
  capture(s,input,n,'제주시 도심 확대 · 범죄주의 지도','노랑→빨강 10단계 범례·2025년 기준·출처가 보이도록 캡처',66,218,1148,337);
  txt(s,'지도: 도로 구간별 주의등급',75,574,542,39,25,C.blue,true);
  txt(s,'2025년 과거 범죄 분포에 따른 참고 정보',75,619,542,43,22);
  txt(s,'점수: 별도의 시 단위 범죄 통계',658,574,548,39,25,C.blue,true);
  txt(s,'지도 색상을 점수로 변환하지 않습니다.',658,619,548,43,22);
  src(s,'지도: 생활안전지도·경찰청 범죄주의구간(전체), 2025 · 점수: 경찰청 행정시별 강력·절도·폭력 통계');
  note(s,'범죄주의 지도는 도로 구간별 과거 범죄 분포에 따른 주의등급이며 미래 범죄 발생확률이 아니다. 점수 생활안전 순찰 수요는 별도의 제주시/서귀포시 강력·절도·폭력 건수 비중으로 계산한다. 같은 시의 도로에 동일 적용하며 도로별 위험이나 인구당 발생률이 아니다. 고정 자료: 제주시5128건/두 행정시6957건=73.7099%. 원래 지도 범례·연도·출처를 포함해 캡처한다. 제공 자료의 사용 조건을 보존한다.',EVIDENCE,'05_src/roadops/context_priority.py',ROOT+'DashboardContent.jsx');break;
 case 10:
  s=page(p,a,n,'근거가 부족할 때의 계산 방식도 담당자가 정합니다','같은 도로·같은 배점에서도 자료 부족 처리 방식에 따라 점수 제공 여부가 달라집니다.');
  txt(s,'확인된 근거로 100점 환산',76,226,539,51,31,C.blue,true);
  txt(s,'근거 반영률 60% 이상이면 산정\n도로 관련 근거가 필요합니다.',78,289,530,81,24);
  txt(s,'중앙로 25.191점',78,386,540,65,41,C.blue,true);
  txt(s,'선택한 근거가 모두 있어야 산정',656,226,550,51,30,C.blue,true);
  txt(s,'계산 대상 근거가 모두 있어야 산정\n하나라도 부족하면 점수를 보류합니다.',658,289,548,81,24);
  txt(s,'같은 도로: 산정 보류',658,386,548,65,39,C.black,true);
  tab(s,[['자료 없음','확인된 0','설정에서 제외','해당 없음'],['미확인 근거\n확인된 0과 구분','확인된 자료에\n따른 결과 0','담당자가\n선택하지 않은 항목','그 도로의 유형에\n적용되지 않는 항목']],74,485,1132,119,[283,283,283,283],22);
  txt(s,'이 예시는 공항 유입 자료가 없어 보류됩니다. ‘확인된 0’은 유효한 근거입니다.',77,619,1128,44,24,C.black,true);
  src(s,time+' 고정 예시 · 확인된 근거의 가중치 65 / 적용 대상 배점 70 · 입력 차단 상태는 환산으로 해제하지 않음');
  note(s,'중앙로 예시 available점수25.191, coverage0.928571; complete점수null. 도로 위험상황은 not_applicable이므로 분모 제외, 공항 유입은 unavailable이므로 부족한 근거다. 사고다발지역/유사상황은 유효한 확인값0. 설정에서 제외(weight0)는 별도 상태이다. 점수 제공에는 최소 도로 근거, 가중 근거 반영률 기준, 원천 차단 상태가 함께 적용된다.',EVIDENCE,ROOT+'priority-policy.js');break;
 case 11:
  s=page(p,a,n,'지금과 1·3·6시간 뒤의 기상을 비교합니다','담당자는 시점을 전환해 첫 점검과 후속 점검에서 다시 볼 구간을 살핍니다.');
  capture(s,input,n,'기상·노면 화면과 시점 전환','현재 / 1시간 / 3시간 / 6시간 · 예보 발표·유효 시각 포함',66,218,1148,326);
  txt(s,'기능: 시점을 바꿔 기상과 후보 도로 검토',75,564,1126,41,27,C.blue,true);
  txt(s,'현재 점수 버전의 후행 비교 표본: 1시간 0건 · 3시간 0건 · 6시간 0건',75,611,1126,40,24,C.black,true);
  src(s,time+' 고정 집계 · 후행 관측 대기, 예측 정확도 판단 보류 · 버전: roadops-operator-priority-v0.2:df2eb24e3aa2');
  note(s,'예측 기능과 예측 정확도를 구분한다. 현재 점수 버전만 필터한 검증은1·3·6시간 모두 matched_points0, 누수0. 과거 점수 버전과 섞인16/4/0을 현재 성능으로 소개하지 않는다. 미래 교통값은 미확인이고 이벤트 지속은 시나리오 가정이다. 자료 수신 기준시각과 예보 유효시각을 캡처에 남긴다.',EVIDENCE,'05_src/roadops/forecast_validation.py');break;
 case 12:
  s=page(p,a,n,'대안을 검토한 담당자가 첫 점검 계획을 확정합니다','수행 가능한 계획을 선택하면, 현장반이 점검을 시작하는 시연으로 이어집니다.');
  txt(s,'기존 고정 시나리오 실험 · 2026.11.13',76,219,1126,43,27,C.blue,true);
  txt(s,'총 이동시간(분)',76,262,700,28,19,C.gray);
  s.charts.add('bar',{position:{left:65,top:296,width:744,height:272},categories:['위험순','최근접','안전 우선','업무 균형'],series:[{name:'총 도로망 이동시간(분)',values:[166.941,164.253,90.167,99.999],fill:C.blue,points:[{idx:0,fill:'#A0A6AA'},{idx:1,fill:'#A0A6AA'},{idx:2,fill:C.blue},{idx:3,fill:C.green}]}],barOptions:{direction:'bar',gapWidth:70},hasLegend:false,dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.0',textStyle:{typeface:'Poppins',fontSize:20}},xAxis:{textStyle:{typeface:'Pretendard',fontSize:21}},yAxis:{textStyle:{typeface:'Poppins',fontSize:17},majorGridlines:{fill:C.line,width:1}},chartFill:C.white,plotAreaFill:C.white});
  txt(s,'45.1%',866,295,339,94,66,C.blue,true,'Poppins');
  txt(s,'당시 최근접 대비\n총 이동시간 감소',868,400,338,83,27,C.black,true);
  txt(s,'3팀 · 3대 · 2시간 · 9작업',870,506,337,55,22,C.gray);
  txt(s,'현재 배점의 성능 검증은 별도입니다. 위 수치는 과거 실험의 제한속도 기반 추정입니다.',76,603,1124,62,25,C.black,true);
  src(s,'2026-11-13 저장 입력 · 당시 위험가중 커버리지 100%, 근무시간 위반 1→0건 · 실제 출동 성과가 아닙니다.');
  note(s,'45.1%=(164.253−90.167)/164.253. 원래 고정 시나리오 결과로서 새8항목배점의 성능이나 최신웹실행결과가 아니다. 이동시간은 제한속도 기반 자유흐름 추정이며 최신 실시간ITS ETA가 아니다. 화면시연·저장What-if와 입력이 다르다.',EVIDENCE,'04_docs/evaluation/20261113_roadops_allocation_evaluation_v0_1.md');break;
 case 13:
  s=page(p,a,n,'','',true);
  scene(s,a+'/13_jeju_road_closure_v1.png','AI 생성 가상 도로 통제 장면. 실제 통제 발생 또는 현장 출동 기록이 아닙니다.',{left:0,top:0,width:1280,height:720});
  txt(s,'첫 계획을 확정하고 점검을 시작한 뒤,',76,111,1048,66,31,'#E4E8EB');
  txt(s,'남은 이동 경로에\n도로 통제가 발생합니다',73,247,1000,164,56,C.white,true);
  txt(s,'완료한 업무를 지키며\n남은 점검을 다시 계획합니다.',78,493,1023,113,32,C.white,true);
  txt(s,'저장 입력에 통제를 주입한 What-if 시뮬레이션',78,623,1025,35,22,'#E4E8EB');
  src(s,'AI 생성 상황 재현 이미지 · 실제 사건·현장 출동 기록이 아닙니다.',true);number(s,n,true);
  note(s,'점검 시작 후 일부 업무 완료 상태에서 통제를 주입한다. 12장의2026-11-13비교실험과는 다른2026-11-19저장입력이다. 사진은 실제해당링크 촬영이아니다. 이번고정예시에서는동부팀만통제영향을받는다.',EVIDENCE,'04_docs/presentation/assets/roadops_submission_20261118/generated_visuals.json');break;
 case 14:
  s=page(p,a,n,'완료 업무를 보존하고, 영향을 받은 팀만 다시 계획합니다','저장된 통제 시뮬레이션에서 Agent는 변경 범위를 좁히고 제약을 다시 검사했습니다.');
  txt(s,'1',74,227,180,149,113,C.blue,true,'Poppins');txt(s,'개 팀 재계획',227,285,355,59,35,C.blue,true);
  txt(s,'동부팀 · 교래 장비고',80,391,507,48,30,C.black,true);
  txt(s,'통제 영향을 받은 중앙로 이동 경로 변경\n이번 예시의 방문 순서는 유지',80,453,510,92,24);
  txt(s,'2',686,227,180,149,113,C.black,true,'Poppins');txt(s,'개 팀 유지',841,285,360,59,35,C.black,true);
  txt(s,'북부팀 · 서부팀',692,391,510,48,30,C.black,true);
  txt(s,'영향이 없는 팀의 계획 유지\n완료 1개·고정 1개 업무 보존',692,453,510,92,24);
  txt(s,'재계획 전·후 제약 위반 0건  ·  적용하려면 담당자 검토·확정 필요',78,591,1125,55,28,C.blue,true);
  src(s,time+' 저장 What-if 결과 · 다음 장의 웹 확정 시연과 별도 실행');
  note(s,'고정시각17:40:13.444640. road_closure affected_team_ids=[team-east], unchanged=[team-north,team-west], task_sequence_changed=false, route_changed_task_ids=[link:4050005521:h0]. 완료4060438807,고정4050418600보존,전후제약0,manual_approval_required=true. 따라서방문순서가반드시바뀐다고하지않는다. 별도폭우시뮬레이션은북부팀영향,방문순서변경. 이번자료는점수버전'+e.score_version+'과같은자동생성주기의저장입력이며브라우저수동변경설정실행결과가아니다.',EVIDENCE);break;
 case 15:
  s=page(p,a,n,'담당자가 방문 순서와 변경 내용을 보고 재확정합니다','별도 웹 시연: 변경안을 검토하고 실행할 계획을 직접 결정합니다.');
  capture(s,input,n,'변경안 검토 → 계획 확정 결과','방문 순서·변경 내용·확정 완료가 실제로 드러나는 화면',66,218,1148,354);
  pair(s,'방문 순서·이동 경로·수행 조건을 확인','담당자가 검토한 계획을 확정');
  src(s,'저장 What-if 결과와 별도 웹 시연 · 모든 확정 경로의 승인 기록 통합·서버 영속 저장은 후속 범위');
  note(s,'거점선택지도만있는옛캡처는삭제. 상세변경안과방문목록,확정상태가보이는화면으로교체한다. UI에서확정후변경내용이사라지면변경안본문과실제확정알림이동시에보이는시점을사용하되서로다른실행을합성하지않는다. 조건이충족되지않으면현재구현가능범위를기록하고제목/캡션도그범위로정정한다. WorkflowPanel의상세승인경로와DashboardContent의간소확정경로는별개이며모든경로가동일한감사기록을만든다고주장하지않는다.',ROOT+'WorkflowPanel.jsx',ROOT+'workflow-policy.js',ROOT+'DashboardContent.jsx');break;
 case 16:
  s=page(p,a,n,'검증 범위와 적용 기준을 남겨 다시 확인합니다','담당자는 자료 상태와 변경 근거를 확인하고, 같은 입력과 기준으로 계산을 재현합니다.');
  txt(s,'기존 장애 주입 실험',77,223,535,42,29,C.blue,true);
  txt(s,'53',76,273,265,104,80,C.blue,true,'Poppins');txt(s,'개 검사 통과',294,309,309,50,29,C.black,true);
  txt(s,'6개 장애 시나리오\n2026.11.16 12:00 KST',80,400,529,81,26);
  txt(s,'캐시 확인·보류·제외·수동 개입\n새 배점 기능 전체의 검증 결과는 아닙니다.',80,509,530,84,23,C.gray);
  txt(s,'현재 기준을 함께 기록',657,223,550,42,29,C.blue,true);
  txt(s,'적용 항목 · 배점 · 계산 방식\n입력 시각 · 계획 · 변경 근거',659,284,548,99,30,C.black,true);
  txt(s,'상세 승인 경로: 설정·계획 지문을\n브라우저 기록에 포함',660,412,546,80,25);
  txt(s,'동일 입력 + 동일 기준으로 재계산\n코드·캐시 데모·실행 매뉴얼 제공',660,515,546,76,24);
  txt(s,'승인 경로 통합·서버 영속 저장·실제 기관 운영 검증은 후속 범위입니다.',78,618,1125,44,24,C.black,true);
  src(s,'현재 구현: 제한 한국어 문법·결정적 도구 체인 · 범용 LLM·전자결재 연계·현장 반복 실증은 후속 범위');
  note(s,'기존6시나리오53검사는2026-11-16저장입력기준. API실패+유효캐시,무캐시,121분stale,잘못된링크,배분불가,설명생성실패를포함한다. 신규점수설정UI전체에대한검증범위를뜻하지않는다. workflowFingerprint/createApprovalRecord에는scoringPolicy가포함되며WorkflowPanel은브라우저localStorage에감사로그/승인기록을저장한다. 간소거점확정과상세승인경로는동일하지않다. 발표용근거JSON에는설정·시각·버전·원천해시를저장해수치검산가능하다.',EVIDENCE,'04_docs/evaluation/20261116_roadops_resilience_evaluation_v0_1.md',ROOT+'workflow-policy.js',ROOT+'WorkflowPanel.jsx','04_docs/deployment/20261116_roadops_execution_user_manual_v0_1.md');break;
 case 17:
  s=page(p,a,n,'RoadOps','',true);s.background.fill=C.blue;
  txt(s,'담당자가 기준을 정하고,\n근거를 확인하며,\n실행할 계획을 결정합니다.',76,216,1124,252,59,C.white,true);
  txt(s,'AI는 그 기준으로 현장계획을 제안하고,\n상황이 바뀌면 필요한 부분을 다시 계획합니다.',80,520,1100,99,31,'#E4F0FA');
  src(s,'제주 도로관리 담당자를 위한 승인형 운영 보조 Agent',true);
  note(s,'핵심은사람의기준설정·근거확인·최종판단이다. 항목/배점/자료부족처리설정은수동·AI공통. 실제기관자동지휘,현장도입완료,예측우월성을주장하지않는다.',ROOT+'priority-policy.js','PROJECT_BRIEF.md');break;
 default:throw new Error('Unsupported slide '+n);
 }
 }
 return {slideCount:p.slides.items.length,written:input.slides,awaitingCaptures:[4,5,6,7,8,9,11,15].filter(n=>!input.captures?.[n])};
}
