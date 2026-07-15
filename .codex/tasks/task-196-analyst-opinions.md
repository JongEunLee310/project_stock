# Codex Handoff Task

## Source Issue

이슈 #318 — 기관별 목표주가·투자의견 계약. 설계:
`docs/designs/318-analyst-opinions.md` (먼저 전체를 읽는다 — 데이터
소스 조사 결과와 계약 표가 확정 스펙이다).

## Task Summary

yfinance `Ticker.upgrades_downgrades`를 소스로
`GET /assets/{asset_id}/analyst-opinions`를 신설한다. 기관명·의견
변경·기관별 목표가·발표 시각을 최근순으로 반환한다.

## Goal

- 미국 종목에서 기관별 의견·목표가 목록이 반환된다 (limit 기본 20,
  1–50).
- 미제공 종목(국내 등)은 `opinions: []`로 응답한다.
- 0.0 목표가·빈 grade가 null로 정규화된다.
- 기존 계약·수집 경로 회귀 없음.

## Implementation Scope

설계 §4 스켈레톤 그대로:

- `app/adapters/market/base.py` — `AnalystOpinionResult` +
  `get_analyst_opinions` 기본 구현.
- `app/adapters/market/yfinance.py` — 수집·정규화 (NaN·0.0 방어,
  limit 절단, 발표순 정렬).
- `app/adapters/market/cache.py` — 1시간 TTL 캐시.
- `app/adapters/market/mock.py` — 결정적 mock (설계 §4).
- endpoint·projection·service — 기존 asset 파생 엔드포인트 관례를
  따르고 자산 없음 404 처리.
- `docs/api/frontend-api-spec.md` — 계약 추가.
- 테스트 — 설계 §5.

## Out of Scope

- FE 수정 (별도 repo)
- 국내 기관 리포트 소스
- DB 영속화·마이그레이션 (없어야 정상)

## Protected Files

없음.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Constraints

- 현재 브랜치(`feat/318-analyst-opinions`)에서 그대로 작업한다.
  새 브랜치 생성·checkout 금지.
- 커밋은 한국어 `type: 본문` 형식으로 작성한다.
- 설계 문서·이 태스크 문서·구현이 같은 PR에 함께 실린다.
