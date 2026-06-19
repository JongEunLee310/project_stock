# Codex Handoff Task

## Source Issue

Issue #48 (제목 Issue 28): `[BE] 프론트엔드 연동용 API 명세 정리`

## Task Summary

프론트엔드 주요 화면별로 사용할 API 목록과 request/response 구조를 `docs/api/frontend-api-spec.md`로 정리하고, 엔드포인트의 OpenAPI summary/description를 보완한다. 응답 예시는 Issue #46/#47에서 확정된 envelope 형식을 따른다.

## Goal

- 화면별(대시보드/관심종목/종목상세/리서치요약/알림후보/포트폴리오요약/설정) API 목록이 정리된다.
- 각 API의 method/path/request/response(envelope)가 문서에서 확인 가능하다.
- 프론트 작업자가 명세만으로 화면 개발을 시작할 수 있다.
- Swagger/OpenAPI의 summary/description가 보완된다.

## Background

- 선행 의존: **Issue #46(응답 envelope), #47(에러 코드) 머지 후.** 응답/에러 예시는 확정된 envelope를 그대로 사용.
- 현행 엔드포인트는 `app/api/v1/endpoints/*.py`, 라우터 prefix는 `app/api/v1/router.py` 참조.
- 화면↔도메인 매핑 참고:
  - 대시보드: signals(알림 후보 요약), portfolios summary, watchlists
  - 관심종목: watchlists CRUD
  - 종목상세: assets, theses, reports, signals
  - 리서치요약: reports, theses(conflict 포함)
  - 알림후보: signals, alerts
  - 포트폴리오요약: portfolios summary/check
  - 설정: auth(me), 향후 알림설정 후보(현재 미구현은 "후보"로 표기)
- v0.2 후속 이슈(#50~)에서 일부 API가 추가/개선될 수 있으므로, 현재 미구현 항목은 "후보/예정"으로 명시하고 추측 구현하지 않는다.

## Implementation Scope

- `docs/api/frontend-api-spec.md` (신규) — 화면별 섹션, 각 API method/path/auth/request/response 예시(envelope).
- `app/api/v1/endpoints/*.py` — 라우트 데코레이터에 `summary=`/`description=`/`tags` 보완(동작 변경 없음, 문서 메타데이터만).

## Out of Scope

- 신규 엔드포인트/도메인/로직 추가.
- 응답 포맷/에러 구조 변경 (Issue #46/#47에서 완료).
- 미구현 화면용 API의 추측 구현 — "후보"로만 문서화.
- DB 스키마 변경.

## Protected Files

변경하지 않는다:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- 문서는 화면 단위로 구성하고, 각 API에 대해: HTTP method, 경로, 인증 필요 여부, 요청 스키마/예시, 응답 envelope 예시(성공 1건 + 대표 에러 1건)를 포함.
- 응답 예시는 `{data, message, error, meta}` 형식 준수(#46/#47과 불일치 금지).
- OpenAPI 보완은 메타데이터(summary/description/tags)만 — 시그니처·response_model·동작 불변.
- 현재 구현된 엔드포인트와 문서가 1:1 일치(미구현은 "후보"로 분리 표기).

## Test Requirements

- 코드 동작 변경이 없으므로 신규 테스트 불필요. 단, OpenAPI 메타 추가 후 `uv run pytest` 전체 통과 유지.
- 가능하면 문서의 경로/메서드가 실제 라우터와 일치하는지 수기 대조(체크리스트).

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/api/frontend-api-spec.md` 신규.
- README에 API 명세 링크 추가 검토(있을 때만, 최소 변경).
- 본 이슈는 순수 문서/메타 → 설계기록(`docs/designs/`) 생략(design-record-policy "문서 변경" 예외).

## ADR Need

없음.

## Failure Record Need

없음.

## Risk Level

Low — 문서 + OpenAPI 메타데이터 한정. 동작·스키마 불변. Human Gate 불필요.

## Expected Output

- `docs/api/frontend-api-spec.md` 신규 + 엔드포인트 OpenAPI 메타 보완.
- `uv run pytest` 통과, lint/typecheck 통과.
- PR body에 `Closes #48`.

## Rules

- Issue #46/#47 머지 후 시작. 미머지 시 중단·보고.
- 미구현 API 추측 구현 금지("후보" 표기).
- 동작/스키마/보호 파일 변경 금지.
- 가정과 검증 결과 보고.
