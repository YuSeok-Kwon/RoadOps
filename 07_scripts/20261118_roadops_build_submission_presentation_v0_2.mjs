/** Story-led RoadOps submission deck, 17 slides including cover and closing.
 * Artifact Session callback input: {slides, assetDir, evidence}.
 * Existing slides are edited in place; IDs of the slides are preserved.
 */
const C={black:'#231F20',blue:'#1468B3',green:'#8CC63F',cyan:'#00AEEF',gray:'#626262',pale:'#F3F5F5',line:'#D9DEDF',white:'#FFFFFF'};
function txt(s,v,x,y,w,h,z=25,c=C.black,b=false,f='Pretendard'){
 const q=s.shapes.add({geometry:'textbox',name:v.slice(0,45),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 q.text=v;q.text.insets=0;q.text.style={typeface:f,fontSize:z,color:c,bold:b};return q;
}
function page(p,n,t,sub='',dark=false){
 const s=n<=p.slides.items.length?p.slides.getItem(n-1):p.slides.add({width:1280,height:720});
 s.background.fill=dark?C.black:C.white;
 if(t)txt(s,t,64,54,1148,100,43,dark?C.white:C.black,true);
 if(sub)txt(s,sub,66,153,1145,62,24,dark?'#CECECE':C.gray);
 if(t)number(s,n,dark);return s;
}
function number(s,n,dark=false){txt(s,String(n).padStart(2,'0')+' / 17',1105,674,112,25,16,dark?'#CECECE':C.gray,false,'Poppins');}
function src(s,v,dark=false){txt(s,v,66,668,1015,34,14,dark?'#BFBFBF':C.gray);}
function note(s,v,...refs){s.speakerNotes.text=v+'\n\n근거 자료\n'+refs.join('\n');}
function pic(s,path,x,y,w,h,crop){s.images.add({path,alt:path.split('/').pop(),fit:'contain',position:{left:x,top:y,width:w,height:h},...(crop?{crop}:{})});}
function photo(s,path,alt,x,y,w,h){s.images.add({path,alt,fit:'contain',position:{left:x,top:y,width:w,height:h}});}
function block(s,label,body,x,y,w=400){txt(s,label,x,y,w,50,30,C.blue,true);txt(s,body,x,y+62,w,128,25);}
function tab(s,values,x,y,w,h,widths,z=23){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
 t.borders.assign({fill:C.line,width:0.7,style:'solid'});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[r].length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?C.black:r%2===0?C.pale:C.white;
  cell.text.style={typeface:'Pretendard',fontSize:z,color:r===0?C.white:C.black,bold:r===0};
 }
 return t;
}
export async function writeRoadOpsStory({presentation:p,input}){
 const a=input.assetDir,e=input.evidence;
 const existing=(await p.inspect({kind:'textbox,shape,image,table,chart',maxChars:250000})).records;
 const selected=new Set(input.slides.map(n=>n-1));
 const ids=existing.filter(r=>selected.has(r.slideIndex)).map(r=>r.id);
 if(ids.length)p.delete(ids);
 for(const n of input.slides){let s;
 switch(n){
 case 1:
  s=page(p,n,'','',true);
  txt(s,'RoadOps',64,58,1120,129,98,C.white,true,'Poppins');
  txt(s,'제주 도로관리\n담당자의\n현장계획 Agent',66,237,422,188,40,C.white,true);
  photo(s,a+'/06_jeju_rain_road_20250718.jpg','2025년 7월 18일 제주시 용강동 제주마 방목지 인근 도로의 호우. 뉴시스 우장호 기자 촬영.',520,161,720,435);
  txt(s,'어디를 먼저 확인하고,\n누구를 보낼 것인가',68,488,425,98,31,C.green,true);
  txt(s,'2025.07.18 제주시 용강동 도로 · 사진: 뉴시스 우장호 기자\n원문: newsis.com/view/NISX20250718_0003257794',521,610,694,45,15,'#CECECE');
  src(s,'제주 AI·빅데이터 Agent Challenge 제출 기획서 · 2026.11.18',true);
  number(s,n,true);
  note(s,'RoadOps는 도로관리 담당자의 현장 작업계획과 변경 검토를 보조한다. 자동 출동을 수행하지 않는다. 실제 호우 사진은 문제의 배경이며 RoadOps 현장 운영 사례가 아니다. 사진 원본 비율과 워터마크를 보존했다. 3장부터 저장 입력·가정 자원·What-if 시뮬레이션으로 전환한다.','https://www.newsis.com/view/NISX20250718_0003257794','https://img1.newsis.com/2025/07/18/NISI20250718_0020894669_web.jpg?rnd=20250718135606','PROJECT_BRIEF.md');break;
 case 2:
  s=page(p,n,'');
  txt(s,'비가 쏟아지면,\n어느 도로부터\n확인해야 할까요?',64,133,370,230,47,C.black,true);
  photo(s,a+'/08_jeju_flood_road_20250422.jpg','2025년 4월 22일 서귀포시 성산읍의 침수 도로와 배수 지원 현장. 제주소방안전본부 제공, 뉴시스 보도.',450,80,766,575);
  txt(s,'점검할 곳은 여러 곳.\n움직일 수 있는 자원은\n한정돼 있습니다.',67,467,354,140,28,C.blue,true);
  src(s,'2025.04.22 서귀포시 성산읍 · 제주소방안전본부 제공 / 뉴시스 보도 · 실제 사례 사진, 시연과 별개\n원문: newsis.com/view/NISI20250422_0001824158');
  number(s,n);
  note(s,'제주소방안전본부 제공 사진에 서귀포시 성산읍 도로 침수와 배수 지원 현장이 담겨 있다. 실제 피해 현장을 문제 배경으로만 사용하며 이후 시연과 같은 사건으로 연결하지 않는다. 원본 비율과 워터마크를 보존했다. 출처 URL을 화면과 발표자 노트에 표시한다.','https://www.newsis.com/view/NISI20250422_0001824158','https://img1.newsis.com/2025/04/22/NISI20250422_0001824158_web.jpg?rnd=20250422121050');break;
 case 3:
  s=page(p,n,'오늘의 점검 계획은 담당자가 정해야 합니다','이제 도로관리 담당자의 판단 과정을 따라가는 운영 시뮬레이션을 시작합니다.');
  txt(s,'폭우가 예보된 날, 업무를 인계받았습니다.\n위험정보를 오늘 수행할 점검 계획으로 바꿔야 합니다.',74,242,1120,118,38,C.black,true);
  [['3','개 현장반',76],['3','대 차량',450],['2','시간',824]].forEach(([v,l,x])=>{txt(s,v,x,397,210,118,91,C.blue,true,'Poppins');txt(s,l,x,510,310,45,30,C.black,true);});
  txt(s,'어느 팀이, 어느 도로부터, 가용시간 안에 확인할 수 있을까요?',76,599,1120,51,30,C.black,true);
  src(s,'시연 자원 3반·3대·2시간은 가정입니다. 앞의 실제 피해 사진과 별개의 시나리오이며 실제 제주 편제를 뜻하지 않습니다.');
  note(s,'호우 예보와 경로 통제라는 가정 아래 점검 계획을 만드는 시연이다. 기존 제주 사업에도 탐지·관제·현장조치 연계가 포함된다. 그 기능의 부재를 주장하지 않으며 RoadOps는 정보와 행정·자원 제약을 통합한 작업안을 제안한다.','PROJECT_BRIEF.md','https://www.muhanit.kr/sub/sub03_01.php?boardid=notice&idx=132&mode=view','04_docs/research/20261117_jeju_road_administration_field_response_v0_1.md');break;
 case 4:
  s=page(p,n,'담당자는 출발 거점과 주변 상황부터 확인합니다','용담 거점을 선택한 담당자는 기상·도로 위험·사고다발·유사 과거 상황을 함께 검토합니다.');
  pic(s,a+'/01_depot_review.jpg',60,226,850,409,{left:0,top:0.14,right:0,bottom:0.02});
  block(s,'거점 선택','어디에서 출발할지\n먼저 정합니다.',939,245,275);
  block(s,'상황 검토','점수와 함께\n위험의 근거를 봅니다.',939,431,275);
  src(s,'2026-11-18 실제 웹 캡처 · 21:01 자료 기준 · 거점의 실제 편제와 출동 절차는 운영기관 확인 필요');
  note(s,'웹에서 용담 제설전진기지를 선택한 상태다. 전체 자원 시나리오 중 하나의 거점 검토 화면이다. 화면 데이터는 캡처 당시 스냅샷이며 현재 도로 현황 보장이 아니다.','04_docs/presentation/assets/roadops_submission_20261118/01_depot_review.jpg');break;
 case 5:
  s=page(p,n,'오늘 움직일 수 있는 현장반 조건을 입력합니다','담당자가 출동 가능 여부·인원·가용시간을 수정하면 가능한 계획을 다시 비교합니다.');
  pic(s,a+'/02_resource_reallocation.jpg',63,230,762,403,{left:0.01,top:0.27,right:0.01,bottom:0.06});
  block(s,'가용 자원 확인','현장반·차량·인원\n이동 + 점검 가능 시간',861,244,353);
  block(s,'조건에 맞는 배분','고정·제외·우선순위 반영\n기관·관할·필수 장비 검사',861,431,353);
  src(s,'실제 웹 재배분 기능 · 저장된 경로 후보를 사용하는 브라우저 최적화기이며 새 도로 경로 탐색은 후속 범위');
  note(s,'웹 최적화는 Python 서버 직접 호출이 아니다. 검토된 경로 후보와 자원·작업 조건으로 브라우저에서 제약 배분을 다시 계산한다. 실행 불가능 조건을 표시하고 계획 유효성을 검사한다.','08_dashboard/roadops_map_v0_1/src/content/dashboard/web-optimizer.js','04_docs/presentation/assets/roadops_submission_20261118/02_resource_reallocation.jpg');break;
 case 6:
  s=page(p,n,'점검할 곳과 방문 순서가 제안됩니다','담당자는 작업안을 받았습니다. 이제 추천 이유와 수행 가능성을 차례로 검토합니다.');
  pic(s,a+'/03_recommended_route.jpg',60,223,822,426,{left:0.01,top:0.28,right:0.01,bottom:0.03});
  txt(s,'용담 거점 선택 예시',922,242,290,47,27,C.blue,true);
  txt(s,'3',923,314,285,95,74,C.black,true,'Poppins');txt(s,'곳 점검',925,403,280,44,29,C.black,true);
  txt(s,'93.3',923,485,290,88,64,C.blue,true,'Poppins');txt(s,'분 예상 · 이동 + 점검',925,574,280,48,24,C.black);
  src(s,'2026-11-18 실제 웹 캡처 · 선택한 한 거점의 화면 예시. 이후 비교실험의 3팀·9작업 고정 벤치마크와는 다른 입력');
  note(s,'용담 거점 추천안 화면에는 3곳 점검, 이동 48.3분, 총 예상 93.3분이 표시된다. 이는 전체 3팀의 성과가 아니라 선택 거점 시연 결과다. 도로 링크 단위로 작업을 구분하므로 동일 주소에 여러 작업이 나타날 수 있다.','04_docs/presentation/assets/roadops_submission_20261118/03_recommended_route.jpg');break;
 case 7:
  s=page(p,n,'담당자는 첫 점검 후보의 추천 이유를 확인합니다','추천 근거를 열어, 현재 신호와 과거 특성이 우선순위에 어떻게 반영됐는지 살펴봅니다.');
  const score=[['현재 이벤트','35','통제·사고·작업 신호'],['구조위험','25','과거 사고와 도로 선형'],['기상·노면','25','강수·바람·시정·노면'],['교통 노출','15','교통량·속도·혼잡']];
  score.forEach((r,i)=>{const y=239+i*83;txt(s,r[1],74,y,110,70,49,C.blue,true,'Poppins');txt(s,r[0],210,y+9,285,48,29,C.black,true);txt(s,r[2],550,y+13,650,45,25,C.gray);});
  txt(s,'점수를 구성한 요인을 확인한 뒤, 과거 자료의 출처를 살펴봅니다.',76,590,1120,55,29,C.blue,true);
  src(s,'위험점수 v0.1 · 구성별 상한 합계 100점 · 커버리지 60% 미만 보류 · 현장 점검 우선순위이며 사고확률이 아닙니다.');
  note(s,'각 숫자는 구성 점수의 상한이다. 결과는 추정치와 하한·상한, 근거 커버리지를 함께 제공한다. 결측을 0으로 대체하지 않는다.','04_docs/model/20261112_roadops_explainable_risk_score_v0_1.md');break;
 case 8:
  s=page(p,n,'과거 사고 자료로 도로 유형의 위험 특성을 확인합니다','담당자는 제주데이터허브 ID 1027 「제주 도로 선형별 교통사고 현황」의 사용 방식을 확인합니다.');
  txt(s,'51',75,241,325,120,86,C.blue,true,'Poppins');txt(s,'개 원천 행',80,351,340,47,30,C.black,true);
  txt(s,'37,087',560,241,640,120,86,C.blue,true,'Poppins');txt(s,'개 링크에 선형 프록시 연결',565,351,630,47,30,C.black,true);
  txt(s,'2018–2020년 집계\n상·하위 합계 검증 9/9\n중복·결측·음수 0건',80,425,430,137,26);
  txt(s,'구조위험 내 제주 데이터 비중 30%\nTAAS 70%와 함께 상한 25점 안에서 반영\n사고가 났을 때의 조건부 심각도 사용',565,425,641,137,25);
  txt(s,'과거 집계의 의미를 확인한 뒤, 현재 정보의 상태를 점검합니다.',80,599,1120,47,28,C.blue,true);
  src(s,'출처: jejudatahub.net/data/view/data/1027 · 2026-11-12 명세 · 통행량 분모가 없어 사고 발생확률로 해석하지 않음');
  note(s,'51행은 개별 사고가 아니라 연도×선형별 집계다. 도로 링크 매핑은 형상 굴곡도 휴리스틱이므로 원천이 37,087링크를 직접 관측했다는 뜻이 아니다. 30%는 전체 점수가 아닌 구조위험 내부 비중이다.','https://www.jejudatahub.net/data/view/data/1027','04_docs/data_quality/20261112_roadops_jeju_datahub_geometry_prior_audit_v0_1.md','04_docs/model/20261112_roadops_explainable_risk_score_v0_1.md');break;
 case 9:
  s=page(p,n,'오래되거나 부족한 근거는 따로 확인합니다','담당자는 출처·관측시각·도로 연결을 살펴, 사용할 근거와 추가 확인이 필요한 정보를 구분합니다.');
  tab(s,[['담당자의 확인','RoadOps의 검사와 처리'],['같은 도로를 가리키는가','링크 ID 일치 / 좌표 보조 결합 / 제외를 구분'],['현재 실황인가, 예보인가','관측·발표·유효·수집시각을 각각 보존'],['빠진 정보는 무엇인가','미수신·결측을 정상값이나 0으로 채우지 않음'],['계산에 어떻게 쓰였는가','원천 → 파생 데이터 → Agent·지도까지 계보 추적']],70,238,1138,303,[400,738],24);
  txt(s,'근거가 부족한 후보는 보류하고, 이후 시점도 살펴봅니다.',76,588,1120,51,31,C.blue,true);
  src(s,'2026-11-16 계보 감사: 19원천·9파생, 592/592 연결, 검사 10/10. 후보·미수신 포함, 이후 기능 전체의 최신 총계는 아님');
  note(s,'당시 등록 19원천이 모두 운영 API 정상 수신 상태라는 뜻은 아니다. exact_link_id, spatial_fallback, excluded, unavailable을 구분한다. 계보 수치는 2026-11-16 고정 평가 범위다.','04_docs/deployment/20261116_roadops_data_usage_lineage_v0_1.md');break;
 case 10:
  s=page(p,n,'1·3·6시간 뒤를 보며 계획을 다시 검토합니다','담당자는 현재와 이후 시점을 비교해, 첫 점검과 후속 점검에서 다시 볼 구간을 검토합니다.');
  txt(s,'지금',76,241,250,83,58,C.black,true);txt(s,'현재 관측과 도로 사건',78,335,320,70,25);
  txt(s,'1h · 3h · 6h',463,241,730,83,58,C.blue,true,'Poppins');txt(s,'기상예보 + 진행 중 이벤트의 지속 가정',468,335,730,70,25);
  const metrics=e.forecast.metrics.filter(v=>v.horizon_hours>0);
  tab(s,[['시점','후행 검증 표본','현재 판정'],...metrics.map(v=>[v.horizon_hours+'시간',v.matched_points+'건',v.matched_points?'표본 부족 · 성능 판단 보류':'후행 표본 대기'])],74,429,1130,166,[220,330,580],23);
  txt(s,'이후 상황까지 살핀 뒤, 이동시간과 수행 가능성을 비교합니다.',77,616,1110,42,27,C.blue,true);
  src(s,'검증: '+e.forecast.generated_at.slice(0,19).replace('T',' ')+' KST · 미래정보 누수 0건 · 운영 시나리오이며 표본 부족으로 예측 성능 판단 보류');
  note(s,'기준선은 예측 생성시점의 현재 점수를 유지한다. 최소 근거 20건 이상·3개 목표시각 이상 조건을 현재 충족하지 못했다. 시점 변경 기능과 예측 정확도 검증은 구분한다.','04_docs/presentation/assets/roadops_submission_20261118/evaluation_snapshot.json','05_src/roadops/forecast_validation.py');break;
 case 11:
  s=page(p,n,'대안을 비교하고 첫 점검 계획을 확정합니다','담당자는 이동시간·위험 커버리지·근무시간 제약을 비교하고, 수행할 계획을 선택합니다.');
  txt(s,'별도 저장 시나리오의 비교 결과 · 총 이동시간(분)',73,222,740,41,23,C.gray);
  s.charts.add('bar',{position:{left:65,top:266,width:748,height:297},categories:['위험순','최근접','안전 우선','업무 균형'],series:[{name:'총 도로망 이동시간(분)',values:[166.941,164.253,90.167,99.999],fill:C.blue,points:[{idx:0,fill:'#A0A6AA'},{idx:1,fill:'#A0A6AA'},{idx:2,fill:C.blue},{idx:3,fill:C.green}]}],barOptions:{direction:'bar',gapWidth:70},hasLegend:false,dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.0',textStyle:{typeface:'Poppins',fontSize:20}},xAxis:{textStyle:{typeface:'Pretendard',fontSize:21}},yAxis:{textStyle:{typeface:'Poppins',fontSize:17},majorGridlines:{fill:C.line,width:1}},chartFill:C.white,plotAreaFill:C.white});
  txt(s,'45.1%',866,265,340,94,66,C.blue,true,'Poppins');txt(s,'최근접 대비 이동시간 감소',869,367,340,72,25,C.black,true);
  txt(s,'100%',869,452,340,72,48,C.black,true,'Poppins');txt(s,'위험가중 커버리지 유지',869,528,340,57,24);
  txt(s,'담당자가 첫 계획을 확정하면, 현장반은 점검을 시작합니다.',76,612,1120,44,29,C.blue,true);
  src(s,'2026-11-13 고정 평가 · 3팀·3대·2시간·9작업 · 근무시간 위반 1건에서 0건 · 제한속도 추정이며 화면 예시·현장 성과와 구분');
  note(s,'서사상 담당자가 첫 계획을 확정한 뒤 점검을 시작한다. 이는 운영 시뮬레이션이며 실제 출동 실적이 아니다. 차트는 6장의 단일 거점 화면과 다른 고정 입력의 검증이다. 45.1%=(164.253−90.167)/164.253. 위험순과 최근접은 최대 팀 소요시간 120분을 넘겼으며 두 최적화안은 위반 0건이다. 단일 시나리오 결과를 일반 효과로 확대하지 않는다.','04_docs/evaluation/20261113_roadops_allocation_evaluation_v0_1.md','04_docs/presentation/assets/roadops_submission_20261118/evaluation_snapshot.json');break;
 case 12:
  s=page(p,n,'','',true);
  txt(s,'첫 계획을 확정하고 점검을 시작한 뒤,',78,127,1100,74,38,'#D1D1D1');
  txt(s,'북부팀의 이동 경로에\n도로 통제가 발생합니다',75,254,1120,180,64,C.white,true);
  txt(s,'완료한 업무는 유지하면서,\n남은 점검을 어떻게 이어갈까요?',81,498,1100,118,36,C.green,true);
  src(s,'점검 진행 중을 가정한 통제 주입 What-if · 실제 발생 사건이나 RoadOps의 현장 출동 기록이 아닙니다.',true);
  number(s,n,true);
  note(s,'첫 계획을 확정하고 현장반이 점검을 시작한 뒤 일부 업무가 완료된 시점에 통제를 주입하는 운영 시뮬레이션이다. road_closure는 기존 경로의 통제 링크에 영향을 주입한다. 변경 영향이 없는 팀과 완료·고정 업무를 보존하는지 검사한다.','04_docs/presentation/assets/roadops_submission_20261118/evaluation_snapshot.json');break;
 case 13:
  s=page(p,n,'완료한 업무는 남기고, 북부팀만 다시 계획합니다','Agent는 통제 영향을 확인한 뒤 남은 업무만 조정하고, 변경 이유와 제약을 재검사합니다.');
  tab(s,[['현장반','통제 전 계획','통제 후 처리'],['북부팀','통제 링크를 포함한 경로','남은 방문 순서·경로 재계획'],['동부팀','통제 영향 없음','기존 계획 유지'],['서부팀','통제 영향 없음','기존 계획 유지']],70,239,1138,262,[236,422,480],26);
  txt(s,'보존',78,545,225,53,34,C.blue,true);txt(s,'완료 업무 · 고정 업무 · 비영향팀',273,551,925,51,30,C.black,true);
  txt(s,'폭우 주입 시에는 북부·서부팀만 재계획. 두 시나리오 모두 제약 위반 0건',78,615,1115,48,25,C.gray);
  src(s,'부분 재계획 검증 스냅샷: '+e.replanning_generated_at.slice(0,19).replace('T',' ')+' KST · What-if 정책 검사');
  note(s,'고정 평가 스냅샷의 affected_team_ids와 unchanged_team_ids, preserved_completed_task_ids, preserved_fixed_task_ids를 확인했다. 통제는 북부1팀, 폭우는 북부·서부2팀 재계획이다. 두 결과 모두 constraint_violation_count=0.','04_docs/presentation/assets/roadops_submission_20261118/evaluation_snapshot.json','04_docs/agent/20261113_roadops_partial_replanning_v0_1.md');break;
 case 14:
  s=page(p,n,'담당자는 변경 사항을 확인하고 계획을 재확정합니다','통제 이후 달라진 방문 순서와 권한을 확인하고, 남은 업무의 변경안을 검토·확정합니다.');
  pic(s,a+'/04_operator_confirmation.jpg',62,247,805,355,{left:0.005,top:0.22,right:0.005,bottom:0.34});
  block(s,'권한 확인','관리기관·도로 관할\n담당자·협조기관 검토',909,245,300);
  block(s,'기록과 확인','변경 근거·계획 지문\n현재 브라우저 기록 범위',909,430,300);
  txt(s,'경찰·소방 자동 지휘 없이, 도로관리 작업과 기관 인계를 구분합니다.',74,615,1130,42,27,C.blue,true);
  src(s,'웹 확정 기능의 별도 시연 · 2026-11-18. 승인 경로 통합·서버 영속 저장·전자결재 연계는 후속 범위');
  note(s,'이미지는 거점별 추천안의 확정 완료 메시지다. 이전 장의 통제 What-if를 실제로 이 화면에서 승인한 동일 실행 기록은 아니다. 최신 거점별 확정과 기존 상세 승인 패널은 다른 UI 경로이며 모든 경로에서 동일한 3종 안전확인이 강제된다고 주장하지 않는다.','04_docs/presentation/assets/roadops_submission_20261118/04_operator_confirmation.jpg','04_docs/model/20261117_roadops_institution_aware_operations_v0_1.md','08_dashboard/roadops_map_v0_1/src/content/dashboard/DashboardContent.jsx');break;
 case 15:
  s=page(p,n,'정보 수신이 끊겨도 다음 행동을 확인할 수 있습니다','운영 중 API가 실패하면, 담당자는 자료 상태와 보류·갱신·수동 개입 여부를 확인합니다.');
  tab(s,[['주입한 실패','담당자가 보게 되는 처리'],['API 실패 + 유효 캐시','출처·나이를 표시하고 캐시 재생'],['캐시 없음 / 121분 경과','보류 · 자료 갱신 또는 담당자 확인'],['잘못된 링크','제외 · 원본과 제외 이유 보존'],['실행 가능한 배분 없음','하드 제약 유지 · 수동 개입 요청'],['설명 생성 실패','검증된 결과만 결정적 설명으로 대체']],72,237,1135,317,[460,675],24);
  txt(s,'6개 실패 시나리오  ·  53개 자동 검사 통과',78,595,1120,54,34,C.blue,true);
  src(s,'2026-11-16 저장 입력 기반 장애 주입 평가 · 운영 SLA·실제 복구시간·현장 안전성 실증을 뜻하지 않습니다.');
  note(s,'API 무캐시 실패와 stale은 별도 시나리오로 총6개다. 설명 실패는 LLM 서비스 장애가 아닌 결과 생성기 실패 가정이다. 다중 장애와 장시간 운영 장애는 후속 검증이다.','04_docs/evaluation/20261116_roadops_resilience_evaluation_v0_1.md');break;
 case 16:
  s=page(p,n,'오늘의 계획과 변경 과정을 다시 확인할 수 있습니다','업무를 돌아보며 7개 도구의 입력·출력·검증 기록을 확인하고, 같은 입력으로 과정을 재현합니다.');
  const f=[['01','요청 해석','팀·차량·시간·시점'],['02','품질 검사','원천·자원 입력'],['03','현장 작업 생성','도로별 업무 통합'],['04','경로 확인','이동시간·접근 가능성'],['05','배분 최적화','복수 대안 계산'],['06','독립 검증','중복·시간·권한 검사'],['07','결과 설명','근거·변경 이유·한계']];
  f.forEach((r,i)=>{const y=229+i*52;txt(s,r[0],74,y,73,42,26,C.blue,true,'Poppins');txt(s,r[1],163,y,310,42,26,C.black,true);txt(s,r[2],484,y,355,42,24,C.gray);});
  txt(s,'같은 입력으로\n다시 실행',892,242,310,114,38,C.blue,true);
  txt(s,'API 키 없는 캐시 데모\n실행기·의존성·매뉴얼\n도구별 추적 로그',896,387,313,160,25);
  src(s,'현재: 제한 한국어 문법·결정적 도구 체인. 범용 LLM 연결, 실제 기관 자원·승인 규정, 현장 반복 실증은 후속 범위');
  note(s,'request_interpreter는 deterministic_korean_demo_grammar_not_general_llm이다. result_explainer는 검증 결과 기반 설명이다. run_demo.sh/run_demo.ps1, requirements.txt, config/.env.example, 실행 매뉴얼로 재현 경로를 제공한다. 실제 센터PC·현장 조직 연계 검증은 후속 범위다.','05_src/roadops/agent_flow.py','04_docs/agent/20261113_roadops_agent_flow_v0_1.md','04_docs/deployment/20261116_roadops_execution_user_manual_v0_1.md');break;
 case 17:
  s=page(p,n,'RoadOps','',true);
  txt(s,'담당자에게 남는 것은\n근거 있는 현장계획입니다',76,229,1124,180,54,C.white,true);
  txt(s,'어디를 먼저 확인할지, 누가 갈 수 있는지,\n상황이 바뀌면 무엇을 바꿔야 하는지.',80,463,1100,113,33,'#D1D1D1');
  txt(s,'근거를 설명하고, 필요한 부분만 다시 계획하고, 사람이 결정합니다.',80,613,1100,42,26,C.green,true);
  src(s,'제주 도로관리 담당자를 위한 승인형 운영 보조 Agent',true);
  note(s,'제안 가치는 위험정보를 관할·자원 제약에 맞는 작업안으로 연결하고 최소 변경 재계획과 검토 근거를 제공하는 것이다. 현장 운영 도입 완료·자동 지휘·예측 우월성을 주장하지 않는다.','PROJECT_BRIEF.md');break;
 default:throw new Error('Unsupported slide '+n);
 }
 }
 return {slideCount:p.slides.items.length,written:input.slides};
}
