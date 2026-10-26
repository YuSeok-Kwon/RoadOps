# RoadOps 실시간 링크 호환성 검증 v0.3 / Live-Link Compatibility Validation v0.3

작성일 / Date: 2026-10-26

## 결론 / Decision

제주 C-ITS·ITS 응답이 들어오면 기준 도로망과의 `link_id` 형식, 정확 조인율, 스키마, 레코드 키, 신선도를 한 번에 검증하는 재사용 가능한 품질 게이트를 구현했다. 다만 현재 환경에 `JEJU_CITS_API_KEY`와 `JEJU_ITS_API_KEY`가 없어 **최신 운영 응답의 실측 결합률은 아직 판정하지 않았다.**

A reusable gate now validates `link_id` format, exact-join coverage, schema, record keys, and freshness whenever Jeju C-ITS/ITS responses become available. The current environment has neither `JEJU_CITS_API_KEY` nor `JEJU_ITS_API_KEY`, so **no claim is made about present live-response compatibility.**

공식 문서의 예시 응답은 별도로 검증했다. 이 예시는 기준망과 조인되지 않았지만 2021년 시각이 포함된 문서용 표본이므로, 현재 API의 버전 불일치 증거가 아니라 **실시간 검증이 필요한 이유**로만 해석한다.

The official documentation examples did not join to the baseline. Because those are documentation samples containing 2021 timestamps, they are not evidence of a current production mismatch; they only demonstrate why a live check is required.

## 공식 스키마 / Official schema

| 소스 / Source | 레코드 단위 / Record grain | 핵심 필드 / Core fields | 호환성 규칙 / Compatibility rule |
|---|---|---|---|
| ITS 실시간 교통 / ITS live traffic | `link_id + prcn_dt` | `tfvl`, `sped`, `ocpy_rate`, `trvl_hh` | 유효한 10자리 ID를 기준망에 정확 조인 |
| C-ITS 도로위험 / C-ITS road event | `ocrr_id + link_id` | 위·경도, 방향, 돌발코드 | ID 정확 조인 우선, 좌표는 보조 검증 |
| C-ITS 통제·작업 / C-ITS closure and work | `ocrr_id + link_id` | 위·경도, 차로 통제, 설명 | ID 정확 조인 우선 |
| C-ITS 노면기상 / C-ITS road weather | `link_id` 스냅샷 / snapshot | 시야, 적설, 노면온도, 수막, 마찰 | ID 정확 조인 우선 |

실시간 교통 API의 `type=L`은 표준 노드링크 타입을 의미한다. 하지만 표준 체계를 사용한다는 설명만으로 버전별 ID 일치까지 보장되지는 않는다.

For live traffic, `type=L` selects standard node-link output. That declaration does not establish that the API and the 2026-10-14 baseline use the same link version.

## 사전 검증 기준 / Pre-registered quality gates

| 게이트 / Gate | 초기 기준 / Initial threshold | 실패 시 판단 / Failure meaning |
|---|---:|---|
| 소스 `link_id` 형식 유효율 | 99% 이상 | 잘못된 길이·문자·결측 ID |
| 유효 ID의 정확 조인율 | 95% 이상 | 링크 버전·범위 불일치 가능성 |
| 레코드 키 완전성 | 99% 이상 | 중복 제거와 이력 추적 불가 |
| 완전한 레코드 키의 고유율 | 100% | 중복 수집·혼합 그레인 가능성 |
| 필수 필드 채움율 | 필드별 95% 이상 | 위험·혼잡 계산 편향 |
| 시각 파싱·미래시각 정상율 | 99% 이상 | 시간대·형식·장비 시계 문제 |
| ITS 최신 레코드 연령 | 30분 이하 | 실시간 배분에 쓸 수 없는 지연 |

30분은 제공기관 SLA가 아니라 RoadOps의 **초기 운영 보수선**이다. 실제 갱신 주기를 관측한 뒤 조정한다.

The 30-minute freshness limit is an **initial RoadOps guardrail**, not a provider SLA. It must be calibrated after observing the actual update cadence.

## 공식 문서 예시 결과 / Official documentation sample results

| 예시 / Sample | 행 / Rows | 유효 ID / Valid IDs | 기준망 정확 조인 / Exact joins | 주요 실패 / Main failure |
|---|---:|---:|---:|---|
| ITS 실시간 교통 | 3 | 3 / 3 | 0 / 3 | 2021-06-16 표본, 모두 현재 기준망에 없음 |
| C-ITS 도로위험 | 2 | 1 / 2 | 0 / 1 | 9자리 ID 1건, 유효한 `407` ID도 기준망에 없음 |

기준망 37,087개의 링크 ID 접두어는 `405`와 `406`이다. C-ITS 문서 예시의 유효 ID는 `407`로 시작한다. 이는 구버전·지역 코드·문서 오타 중 하나일 수 있지만, 실시간 응답 없이 원인을 확정하지 않는다.

The 37,087-link reference uses `405` and `406` prefixes. The valid C-ITS documentation example uses `407`. This could reflect an old version, a local code system, or a documentation error; the cause remains unclassified without a live response.

## 전송 보안 게이트 / Transport-security gate

2026-10-26 점검에서 문서에 표시된 HTTP 주소는 인증키가 없으면 HTTP 400 JSON을 반환했고, 동일 호스트의 HTTPS는 15초 내 연결되지 않았다. 인증키는 전송하지 않았다.

On 2026-10-26, the documented HTTP endpoint returned an HTTP 400 JSON response when called without a key, while HTTPS on the same host timed out after 15 seconds. No credential was transmitted.

코드는 평문 HTTP 호출을 기본 차단한다. `--allow-insecure-http`를 명시하기 전에 제공기관의 HTTPS 지원 여부를 확인하고, 키의 권한·유효기간·순환 정책을 제한해야 한다. 키는 로그와 결과 JSON에 포함하지 않는다.

The code blocks plaintext HTTP by default. Before explicitly overriding that block, confirm HTTPS support with the provider and restrict the key's scope, lifetime, and rotation. The key is excluded from logs and report JSON.

## 재현 명령 / Reproduction commands

기존 JSON을 안전하게 검증하는 방법:

```bash
python 07_scripts/20261026_roadops_validate_live_link_compatibility_v0_1.py \
  --source-id jeju_its_realtime_traffic \
  --reference-links 02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv \
  --input path/to/jeju_its_response.json \
  --output 02_outputs/data/jeju_its_link_compatibility.json
```

실시간 호출 모드는 해당 소스의 키가 환경변수에 존재할 때만 동작한다. 현재 C-ITS·ITS 주소는 HTTP이므로 기본 정책에서 차단된다.

Live mode requires the source-specific environment variable. Because the currently documented C-ITS/ITS endpoints use HTTP, the default security policy blocks the call.

## 다음 작업 / Next work

1. 제주 ITS·C-ITS 활용신청으로 읽기 전용 키를 발급받는다.
2. 제공기관에 HTTPS 지원 여부와 현재 표준 노드링크 버전을 확인한다.
3. 원본 응답을 변경 불가 영역에 저장하고 시각·해시를 남긴다.
4. ITS, 위험, 통제, 작업, 노면기상 각 소스별 정확 조인율을 측정한다.
5. 실패 ID를 접두어·좌표·소스별로 분류해 버전 매핑 또는 공간 보조가 필요한지 판단한다.

1. Obtain read-only Jeju ITS and C-ITS keys through the official application process.
2. Confirm HTTPS support and the current standard node-link version with the provider.
3. Preserve raw responses immutably with timestamps and hashes.
4. Measure exact-join coverage separately for traffic, hazards, closures, works, and road weather.
5. Segment failed IDs by prefix, location, and source before deciding whether a version map or spatial fallback is justified.

## 공식 출처 / Official sources

- [제주특별자치도 실시간 교통정보](https://www.data.go.kr/data/15093660/openapi.do)
- [제주 C-ITS·ITS Open API 상세](https://jejuits.go.kr/open_api/open_apiView.do)
- [제주특별자치도 C-ITS 교통정보](https://www.data.go.kr/data/15079829/openapi.do)
