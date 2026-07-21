# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#368 — BE: 투자자 동향 계약 (에픽 #307 2차).
설계문서: `docs/designs/307-news-intelligence-phase2.md` §3.2.

## Task Summary

`news_insights` 도메인에 `GET /api/v1/news-insights/investor-flows`를 구현한다. 투자자 유형별
순매수/순매도와 뉴스 내러티브 대비 수급 방향 정렬 여부를 반환한다. 2차 골격의 `investor_flows`
테이블(seed) 위에서 계약을 고정한다.

## Goal

- `GET /investor-flows`가 market·window·topic_id 기준 투자자 유형별 수급과 정렬 신호를 반환한다.
- 데이터 미제공 시장은 빈 값을 추정하지 않고 availability로 명시한다.
- 기존 계약을 변경하지 않는다.

## Background

- `investor_flows` 테이블·`InvestorType`·`FlowDirection` enum·seed가 이미 존재한다(2차 골격,
  이 브랜치 하위 스택). `app/domains/news_insights/`의 model·types·seed 참고.
- 와이어 컨벤션: snake_case, `ApiResponse`/`success`, 인증 `get_current_user`. **금액(net_value)은
  Decimal을 문자열로 직렬화**(1차 점수 float와 구분). 기존 도메인의 Decimal→문자열 직렬화 패턴을
  따른다(예: 다른 금액 필드의 schema serializer).

## Implementation Scope

- `app/domains/news_insights/schema.py` — investor-flows 요청/응답 projection.
- `app/domains/news_insights/repository.py` — investor_flows 조회(집계).
- `app/domains/news_insights/service.py` — 유형별 수급 조립, 내러티브 정렬 판단.
- `app/api/v1/endpoints/news_insights.py` — `GET /investor-flows` 라우트 추가.

## Out of Scope

- 종목 민감도·키워드 관계망(#369)·캘린더·처리 현황(#370). 신규 테이블·마이그레이션 불요(골격 재사용).
- 1차·#306 로직 변경. 실수급 데이터 연동(1차 seed 계약 고정).

## Protected Files

없음.

## Requirements

- `GET /investor-flows`: query `market`·`window`·`topic_id`(optional).
- 응답: `as_of`, `by_investor_type`[{`investor_type`·`net_value`(문자열)·`direction`·`change`}],
  `narrative_alignment`{`aligned`(bool)·`note`}(뉴스 감성 vs 수급 방향 일치/불일치),
  `availability`{`available`(bool)·`fallback`(미제공 시장의 대체 지표 설명)}. (설계 §3.2)
- 수급 숫자는 집계 — LLM은 정렬 여부 해석 문장만(숫자 생성 금지).
- 데이터 미제공 시장은 빈 값 추정 금지 — availability로 명시.
- enum·필드는 골격 모델과 설계문서 계약에 일치. 이탈 시 설계문서 먼저 갱신.

## Test Requirements

- `/investor-flows` 통합 테스트(httpx) — 유형별 수급·정렬 신호·availability.
- net_value가 문자열로 직렬화되는지 검증.
- 기존 테스트를 약화하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`  (전체 — tests·alembic 포함. `mypy app`만으로는 CI를 재현하지 못한다.)
- `uv run pytest`

## Documentation Impact

- 설계문서 §3.2 계약과 구현 일치. 이탈 시 문서 먼저 갱신.

## ADR Need

불요. 기존 도메인·와이어 컨벤션을 따르는 read 엔드포인트 추가.

## Failure Record Need

불요.

## Risk Level

Low~Medium — read 엔드포인트 1개. Decimal 문자열 직렬화·정렬 판단 정확성에 주의.

## Expected Output

- schema·repository·service·router·테스트 커밋. PR 본문에 설계문서 링크와 계약 요약.
- 검증 3종 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치를 유지한다(자체 브랜치 생성 금지).
