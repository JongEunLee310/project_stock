# Codex Handoff Task

## Source Issue

https://github.com/JongEunLee310/project_stock/issues/231

## Task Summary

LLM 시스템 프롬프트 7종에 한국어 출력 지시를 추가해 추천 rationale·관찰메모 등 자연어 필드가 한국어로 출력되게 한다.

## Goal

- 시스템 프롬프트 7종 모두에 공통 한국어 출력 지시문이 포함된다.
- symbol·enum 값·JSON 키는 영어 원문 유지가 지시문에 명시된다.
- 검증 3종(ruff, mypy, pytest) 통과.

## Background

설계 문서: `docs/designs/231-korean-llm-output.md` — Verified Facts와 Decisions 확정. 대상 파일은 `app/adapters/llm/prompts/`의 7종:

- 상수형 4종: `stock_recommendation.py`(`STOCK_RECOMMENDATION_SYSTEM_PROMPT`), `watchlist_observation.py`, `dashboard_briefing.py`, `portfolio_briefing.py`
- 함수형 3종: `analysis.py`, `news_summary.py`, `thesis_conflict.py` (`build_*_system_prompt()`)

추천 서비스(`app/domains/watchlists/recommendations_service.py`)는 응답 symbol을 후보와 문자열 비교하므로, symbol이 한국어로 번역되면 추천이 유실된다. 지시문에 "JSON 키·symbol·enum 값은 원문 유지"를 반드시 포함한다.

## Implementation Scope

- `app/adapters/llm/prompts/` 안에 공통 한국어 출력 지시문 상수 1개 신설 (위치는 `__init__.py` 또는 신규 `language.py` 중 선택). 문구는 영어로 작성한다(프롬프트 본문이 영어이므로 일관성 유지). 취지: "Write all natural-language field values (rationale, note, summary, headline, body, risk_checks, ...) in Korean. Keep JSON keys, symbols, and enum values exactly as given."
- 상수형 프롬프트: 문자열 말미에 지시문을 포함.
- 함수형 프롬프트: 반환 문자열에 지시문을 포함.
- 기존 프롬프트 문구·구조는 변경하지 않는다 (지시문 추가만).
- 테스트 추가: 7종 프롬프트(함수형은 호출 결과 문자열)가 공통 지시문을 포함하는지 단언. 신규 파일 `tests/test_prompt_language.py` 권장.

## Out of Scope

- 프롬프트 문구 개선·재작성
- mock LLM 응답 변경
- FE 변경
- 사용자별 언어 설정

## Protected Files

없음. 보호 파일을 수정하지 않는다.

## Requirements

- 지시문은 단일 상수로 정의하고 7곳에서 재사용한다 (문구 중복 금지).
- 기존 테스트를 약화하거나 삭제하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

구현 완료 후 `docs/designs/231-korean-llm-output.md`의 Status를 `Implemented`로 갱신한다.

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Low — 프롬프트 문자열 추가와 테스트 신설이며 코드 경로 변경이 없다.

## Expected Output

- 변경 파일 목록 보고
- 검증 3종 실행 결과 보고
- 가정·잔여 위험 보고

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(feat/231-korean-llm-output)에서 그대로 작업한다. 새 브랜치를 만들지 않는다. 커밋하지 않는다.
