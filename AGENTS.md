# Repository Working Agreement / 저장소 작업 규칙

## Git commits / Git 커밋

- Commit every completed work unit that changes at least one code file.
- 코드 파일이 하나라도 변경된 완료 작업 단위는 반드시 커밋한다.
- Run the relevant checks before committing and do not commit known failing code.
- 커밋 전에 관련 검증을 실행하고, 실패가 확인된 코드는 커밋하지 않는다.
- Stage only files related to the current work; preserve unrelated user changes.
- 현재 작업과 관련된 파일만 스테이징하고 사용자의 다른 변경사항은 보존한다.
- Documentation-only edits may be grouped into the next meaningful documentation milestone.
- 문서만 수정한 경우에는 다음 의미 있는 문서 작업 단위로 묶어 커밋할 수 있다.

## Commit message format / 커밋 메시지 형식

Write both English and Korean in every commit message.

모든 커밋 메시지에 영어와 한국어를 함께 작성한다.

```text
<type>: <English summary> / <한글 요약>

English details, validation, or important context.
한글 상세 내용, 검증 결과 또는 중요한 맥락.
```

Example / 예시:

```text
feat: add road risk scoring / 도로 위험도 산정 기능 추가

Calculate reproducible risk scores from traffic, weather, and incident inputs.
교통량, 기상, 돌발상황 입력으로 재현 가능한 위험점수를 계산한다.
```

Use one of `feat`, `fix`, `test`, `refactor`, `docs`, `chore`, or `build` as the commit type when applicable.

가능한 경우 커밋 유형으로 `feat`, `fix`, `test`, `refactor`, `docs`, `chore`, `build` 중 하나를 사용한다.
