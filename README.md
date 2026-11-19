# RoadOps — 제주 데이터 기반 도로 점검 계획 Agent

**2026 제주 AI Agent 공모전 최종 결과물 · 권유석 · 2026-11-20**

제주데이터허브의 사고 통계·위험지구 자료를 바탕으로 현장 점검 항목을 제안합니다. 도로·기상·교통 정보와 투입 가능한 인력·시간을 반영해 방문 계획을 계산합니다. 통제가 발생하면 완료한 점검 기록을 유지한 채 남은 경로를 다시 계산하고, 예상 소요시간이 가용 시간을 넘는지 보여줍니다.

현재는 규칙 기반 점수 산정, 경로 탐색, 인력·시간 등 운영 조건 검증을 구현했습니다. **학습형 AI 모델과 외부 LLM은 현재 실행에 사용하지 않습니다.** 정해진 형식의 요청을 처리하는 7단계 도구 실행 흐름과 웹 UI를 구현했으며, 자유로운 자연어 요청 해석과 결과 설명을 위한 LLM 연동은 후속 계획입니다.

## 가장 빠른 실행

설치 없이 확인: **[RoadOps 웹 시연](https://yuseok-kwon.github.io/RoadOps/)** · **[GitHub 소스 코드](https://github.com/YuSeok-Kwon/RoadOps)** · **[기획서 PDF](https://yuseok-kwon.github.io/RoadOps/proposal.pdf)**

웹 시연은 로그인 없이 열 수 있는 GitHub Pages 정적 실행본입니다. 아래 절차는 ZIP을 내려받아 PC에서 실행할 때 사용합니다.

1. ZIP 전체를 압축 해제합니다. ZIP 내부에서 바로 실행하지 마세요.
2. Python 3.11 이상이 설치된 PC에서 `START_WEB.cmd`(Windows) 또는 `START_WEB.command`(macOS)를 실행합니다. 이 실행본은 **pip·npm을 통한 추가 패키지 설치, API 키, GPU, Codex 계정이 필요 없습니다.**
3. 열린 시작 화면에서 **발표 사례 실행** 또는 **최종 기능 실행**을 선택합니다.
4. 종료하려면 실행한 터미널에서 `Ctrl+C`를 누릅니다.

더블클릭 실행이 제한되면 압축을 푼 `RoadOps` 폴더에서 직접 실행합니다.

```sh
# Windows
py -3 run_web.py
# macOS / Linux
python3 run_web.py
```

주소는 `http://127.0.0.1:8765/`입니다. 포트가 사용 중이면 `python run_web.py --port 8766`을 사용합니다. 서버는 이 PC에서만 접근할 수 있습니다. 앱은 저장 데이터를 사용하며 **배경 지도 타일은 인터넷 연결이 필요**합니다. 인터넷이 없어도 포함된 도로망·점검·시간 계산은 사용할 수 있습니다.

## 실행본과 기준시점

| 실행본 | 포함 자료 | 확인할 내용 |
|---|---|---|
| 발표 사례 | 2026-11-19 17:40 저장 자료 | 기획서 8~13장, 통제 전후 실제 경로 변화, 100.6 → 125.6분 |
| 최종 기능 | 2026-11-20 저장 자료(시각은 화면에 표시) | 거점별 기상, 노면별 통계, 사고다발지역·위험지구, 점검 항목 반영 |
| Python CLI | `demo/cached_inputs_v0_1`의 초기 고정 자료 | 팀 3개·차량 3대의 7단계 Tool 실행과 재검증 |

세 실행본은 사용하는 자료의 시점과 범위가 달라 점수와 방문 계획이 다를 수 있습니다. 수치를 비교할 때는 같은 자료와 조건을 사용해야 합니다. 최종 웹 실행본도 미리 저장한 자료로 동작하며, 화면에 자료 기준시점을 표시합니다.

## 발표 사례 재현 — 약 3분

**발표 사례 실행 → 용담 제설전진기지 → AI 자동선택 → 추천 경로 만들기**로 이동합니다. 필요하면 사용자 매뉴얼의 단계별 설명을 확인합니다.

통제 입력란에 아래 조건을 입력합니다.

| 항목 | 값 |
|---|---|
| 출동 조건 | 용담, 2명, 120분 |
| 통제 구간 번호 | `4050000302` — 1100로 방향 링크 약 398m |
| 완료한 점검 | 1번째 광령리까지 완료 |
| 이미 사용한 시간 | `39.8`분 — 두 안에 동일하게 적용한 시연 가정값이며 실측값이 아님 |
| 비교 옵션 | `방문 대상·순서를 유지하고 통제 전후 필요 시간 비교` 선택 |

`대체 경로 자동 계산`을 누릅니다. 통제 전·후 보기에서 소길리→예래동 이동 경로가 달라지고, **총 125.6분 / 5.6분 초과 / 출동 조건 검토 필요**가 표시됩니다. 가용 시간을 초과한 계획은 확정할 수 없으며, 담당자가 시간 연장·지원 투입 또는 계획 변경을 검토해야 합니다.

## 제출 요구사항별 위치

| 요구사항 | 파일·폴더 |
|---|---|
| 기획서 1부, 15페이지 이내 | `RoadOps_기획서_권유석.pdf` — 15페이지 |
| PDF 미리보기 호환본 | `web/proposal.pdf` — 동일한 15페이지를 RGB 이미지로 변환, 텍스트 선택·문서 내 링크 미지원 |
| 실행 소스·데이터 처리 | `05_src/roadops`, `07_scripts`, `08_dashboard/roadops_map_v0_1` |
| Prompt·Tool/API·모델 정보 | `config/agent/roadops_agent_contract_v0_1.json`, `config/data_sources.json`, `04_docs/submission_20261120/MODELS_TOOLS_PROMPTS.md` |
| 설치·실행·사용자 매뉴얼·제약 | 이 README, `04_docs/submission_20261120/USER_MANUAL.md`, `requirements.txt`, `config/.env.example` |
| 데이터 활용 명세·이용조건·전처리 | `04_docs/submission_20261120/DATA_USAGE.md`, `demo/jeju_inspection_evidence_v0_1.json` |
| 문제·구조·기능·결과·검증·센터 활용 | `04_docs/submission_20261120/RESULTS.md`, `evidence/` |
| 오픈소스 목록·고지 | `04_docs/submission_20261120/THIRD_PARTY_NOTICES.md`, `licenses/`, 앱 `package-lock.json` |
| 파일 무결성·출처 버전 | `MANIFEST.json`, `evidence/package-provenance.json`, `verify_package.py` |

`04_docs/deployment`의 11월 16일 문서는 초기 개발 기록입니다. **최종 제출본의 실행 절차·시나리오·제약사항은 이 README와 `04_docs/submission_20261120` 문서를 기준으로 확인하세요.**

## 개발자 실행 및 재검증

웹 실행본을 보기만 할 때 아래 설치는 필요 없습니다. 소스를 수정하거나 Python 검증을 실행할 때 사용합니다.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r 04_docs/submission_20261120/requirements-runtime.txt
python 07_scripts/20261113_roadops_run_agent_flow_v0_1.py --strict
python -m pytest
```

CLI 결과는 `02_outputs/data/agent_flow_v0_1`에 생성됩니다. 노트북·차트까지 개발하려면 루트의 `requirements.txt`를 추가로 설치합니다. Windows에는 IANA 시간대 데이터가 필요하므로 위 런타임 의존성에 `tzdata`를 포함했습니다.

```sh
# Node.js 22.12 이상 필요. 아래 명령은 RoadOps 루트에서 실행
node --test 08_dashboard/roadops_map_v0_1/tests/*.test.mjs
python verify_detour.py
python verify_package.py

# 웹 소스 재빌드: 최신 기능 자료를 사용
cd 08_dashboard/roadops_map_v0_1
npm ci
npm run build
python -m http.server 8766 --bind 127.0.0.1 --directory dist
```

소스 재빌드는 `src/data.json`의 최종 기능 자료를 사용합니다. 발표 자료를 재빌드하려면 작업용 사본에서 `demo/presentation_20261119/data.json`을 앱의 `src/data.json`으로 복사한 뒤 같은 명령을 실행합니다. 수정·재빌드 후에는 원본 파일 해시 검사에 차이가 나므로 배포 원본과 작업용 사본을 구분하세요.

## 검증 범위

제출 전 macOS의 격리된 폴더에서 Python·웹 테스트, 패키지 실행, 통제 전후 경로 및 시간, 소스 빌드와 파일 무결성을 확인했습니다. 상세 기록은 `evidence/validation.json`에 있습니다. **센터 운영 PC 및 Windows에서의 실제 실행·성능은 아직 검증하지 않았습니다.** 센터 최소사양에 맞춰 CPU 중심으로 구성했으며, 현장 통행 가능 여부와 업무 적용 효과는 별도 검증 대상입니다.

라이브러리 취약점 점검에서 실행용 패키지(`npm audit --omit=dev`)는 0건, Vite·PostCSS 계열 개발용 패키지는 4건이 보고됐습니다. 포함된 실행본은 Vite 개발 서버를 사용하지 않습니다. 개발 환경을 외부에 공개하기 전에는 해당 패키지를 업데이트하고 다시 검증해야 합니다. 원문 보고서는 `evidence/dependency-audit.json`에 보관했습니다.
