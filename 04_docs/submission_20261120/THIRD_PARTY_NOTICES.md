# 외부 데이터·오픈소스 고지

이 문서는 RoadOps 코드 자체에 새 공개 라이선스를 부여하는 문서가 아닙니다. 제3자 코드·데이터의 권리는 해당 제공자에게 있습니다. 제출물의 실제 라이브러리 버전은 앱 `package-lock.json`, `licenses/npm/*/package-info.json`, `evidence/python-environment.txt`로 확인합니다.

## 주요 라이브러리

| 구분 | 프로젝트 | 용도 | 라이선스 계열 |
|---|---|---|---|
| 웹 | React / React DOM | UI | MIT |
| 웹 | Vite / vite-plugin-singlefile | 소스 빌드 | MIT |
| 웹 | Recharts | 공통 UI 차트 | MIT |
| 웹 | Lexical / @lexical/* | 공통 문서·편집 기능 | MIT |
| 웹 | Radix UI | 공통 UI 컨트롤 | MIT |
| 웹 | react-markdown / html-to-image / figma-squircle | 공통 표시·내보내기 | MIT |
| Python | httpx | API 요청 | BSD-3-Clause |
| Python | pyproj | 좌표 변환 | MIT, 연결되는 PROJ의 고지는 설치 배포본 참조 |
| Python | pyshp | SHP 처리 | MIT |
| 검증 | pytest | Python 회귀 테스트 | MIT |
| 시각 검증 | Playwright | 브라우저 자동 검증 | Apache-2.0, 일반 실행에는 불필요 |
| 개발 선택 | matplotlib / NumPy / Jupyter 계열 | 노트북·분석 | 각 패키지 고지 참조, 일반 웹 실행에는 불필요 |

직접·간접 의존성의 원문 LICENSE/NOTICE가 있는 경우 `licenses/npm`과 `licenses/python`에 보존했습니다. Python·Node 실행 바이너리, 브라우저, 설치된 패키지 폴더는 ZIP에 포함하지 않습니다. 포함된 웹 실행본은 앱 코드와 필요한 JavaScript를 빌드한 결과이며 일반 실행 시 npm 다운로드가 없습니다.

2026-11-20 npm 감사 결과: 운영 의존성 보고 0건, 개발 의존성 4건(Vite·PostCSS·nanoid·source-map-js, high 3·moderate 1). 상세 영향 조건·수정 정보는 `evidence/dependency-audit.json`의 advisory URL에 있습니다. `run_web.py`는 빌드된 파일을 Python 표준 라이브러리로 로컬에 제공하며 Vite 개발 서버를 실행하지 않습니다. 이 결과는 전체 코드의 보안 보증을 뜻하지 않습니다.

## 데이터·지도·이미지

데이터별 기관·원문 링크·기준일·사용 범위·이용조건은 `DATA_USAGE.md`에 있습니다. 제주데이터허브, 제주특별자치도·제주시, 국토교통부, 기상청, TAAS, 제주 ITS/C-ITS, SGIS 및 생활안전지도 출처를 유지합니다. OpenStreetMap 기여자 출처 표시는 지도에 유지하고 타일은 ZIP에 재배포하지 않습니다.

기획서의 상황 연출 사진에는 ‘AI 생성 상황 재현 이미지’라고 표시했습니다. 앱 실행 화면 및 경로·시간 검증 화면은 실제 프로그램 출력입니다. 연출 사진을 실제 현장 증거로 사용하지 않습니다.
