# 제주 C-ITS·ITS 인증키·실시간성 감사 v0.1 / Jeju C-ITS·ITS Key and Timeliness Audit v0.1

## 결론 / Conclusion

2026-10-27 09:21:29 KST 기준 C-ITS 키와 ITS 키는 모두 유효하다. C-ITS 4개 API와 ITS 3개 API가 모두 HTTP 200, 제공자 결과 `success`, JSON 응답을 반환했고 실패 호출은 없었다.

Both credentials were valid as of 2026-10-27 09:21:29 KST. Four C-ITS endpoints and three ITS endpoints returned HTTP 200, provider result `success`, and JSON with no failed calls.

ITS 실시간 교통정보는 12,081개 레코드를 반환했다. 최신 `prcn_dt`는 09:20:00 KST로 감사 시점보다 1.498분 전이었으며, 30분 신선도 기준을 통과했다. 1시간 통계 12,081개는 요청한 08시 기준시각을, 일간 통계 12,081개는 요청한 2026-10-26 기준일을 모두 반환했다.

The ITS live feed returned 12,081 records. Its newest `prcn_dt` was 09:20:00 KST, 1.498 minutes before evaluation, and passed the 30-minute freshness gate. All 12,081 hourly rows matched the requested 08:00 period, and all 12,081 daily rows matched the requested 2026-10-26 date.

## 데이터 단위와 점검 범위 / Grain and scope

- 감사 단위: 설정된 API 엔드포인트 1개당 1개 감사 결과
- 인증: 키 값을 기록하지 않고 제공자 성공 결과만 확인
- 실시간성: 응답에 존재하는 시각 필드와 감사 시각의 차이
- 무결성: 제공 `info_cnt`와 추출 레코드 수 일치 여부
- 도로망 호환성: 유효한 10자리 `link_id`와 2026-10-14 제주 기준망 37,087개 링크의 정확 일치율

## 핵심 결과 / Key results

| 소스 / Source | 레코드 | 인증 | 시간 상태 | 정확 링크 결합률 |
| --- | ---: | --- | --- | ---: |
| C-ITS 도로위험 | 33 | 유효 | 응답에 시각 없음 | 72.73% |
| C-ITS 도로통제 | 0 | 유효 | 응답에 시각 없음 | 측정 불가 |
| C-ITS 도로작업 | 1 | 유효 | 응답에 시각 없음 | 0.00% |
| C-ITS 노면기상 | 12 | 유효 | 응답에 시각 없음 | `link_id=-1`, 측정 불가 |
| ITS 실시간 교통 | 12,081 | 유효 | 최신 지연 1.498분 | 98.55% |
| ITS 1시간 통계 | 12,081 | 유효 | 요청 시각 전량 일치 | 98.55% |
| ITS 일간 통계 | 12,081 | 유효 | 요청 일자 전량 일치 | 98.55% |

모든 응답에서 제공 `info_cnt`와 실제 추출 건수가 일치했다. ITS 세 소스는 중복 레코드 키가 없었고 스키마·신선도·정확 링크 결합률 게이트를 모두 통과했다.

## 발견된 위험 / Risks found

1. **C-ITS 신선도 측정 불가 — High, high confidence.** 도로위험·통제·작업·노면기상 레코드에 관측 또는 갱신 시각이 없다. 단일 응답만으로 현재 상황인지 오래된 잔존 레코드인지 구분할 수 없다. 수집 시각을 별도로 기록하고 연속 스냅샷 차이를 추적해야 한다.
2. **C-ITS 링크 버전 불일치 — High, high confidence.** 도로위험은 33개 중 24개만 기준망에 정확히 결합됐고, 도로작업 1개는 결합되지 않았다. 현장 자원배분 점수에 투입하기 전에 좌표 기반 보조 결합과 링크 버전 매핑이 필요하다.
3. **노면기상 링크 ID 사용 불가 — High, high confidence.** 12개 레코드 모두 `link_id=-1`이다. 노면기상은 위도·경도를 기본 키로 취급하고 최근접 링크에 공간 결합해야 한다.
4. **ITS 기준망 차이 — Medium, high confidence.** ITS 12,081개 중 11,906개가 정확히 결합돼 98.55%를 기록했다. 175개 미결합 링크는 별도 버전 매핑 또는 공간 결합이 필요하다.
5. **평문 전송 — High, high confidence.** 제공자가 HTTP만 지원하므로 키와 응답이 암호화되지 않는다. 운영 환경에서는 제공기관의 HTTPS 지원 확인 또는 교체 가능한 제한 키 정책이 필요하다.

## 자동화 규칙 / Automated checks

- 인증: 제공자 결과가 `success`가 아니면 실패
- 응답 완전성: `info_cnt == 추출 레코드 수`
- ITS 실시간성: 최신 `prcn_dt`가 수집 시점 기준 30분 이내
- 통계 기준시각: 반환 `stat_dt`가 요청 `statDt`와 전량 일치
- ITS 링크 결합률: 유효 링크 ID의 정확 결합률 95% 이상
- C-ITS: 수집 시각 기록과 스냅샷 해시·레코드 증감 추적 추가 예정

## 재현 / Reproduce

```bash
python 07_scripts/20261027_roadops_audit_jeju_live_api_v0_1.py \
  --allow-insecure-http
```

실행 결과는 `02_outputs/data/jeju_live_api_audit_v0_1/audit_report.json`에 저장된다. API 키와 키가 포함된 URL은 보고서에 저장되지 않는다.
