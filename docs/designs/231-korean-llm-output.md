# Design: LLM 한국어 출력 지시 (#231)

## Status

Implemented

## Context

openai-oauth 프록시로 실제 LLM 경로를 연결해 확인한 결과, 종목 추천 rationale과
관심종목 AI 관찰메모가 영어로 출력된다. `app/adapters/llm/prompts/`의 시스템
프롬프트 7종이 모두 영어이고 출력 언어 지시가 없기 때문이다. mock provider에서는
고정 응답이라 드러나지 않았다.

## Verified Facts (2026-07-08, feat/231-korean-llm-output 기준)

- 프롬프트 파일 7종: `stock_recommendation.py`, `watchlist_observation.py`,
  `dashboard_briefing.py`, `portfolio_briefing.py`, `news_summary.py`,
  `analysis.py`, `thesis_conflict.py` — 상수 4종은 `*_SYSTEM_PROMPT` 문자열,
  나머지 3종은 `build_*_system_prompt()` 함수가 JSON Schema를 삽입해 조립.
- 기존 테스트는 gateway 호출 시 전달된 `system_prompt`를 캡처만 하고 내용을
  단언하지 않는다 (`tests/test_watchlist_recommendations.py:198` 등에서
  `_prompt`로 폐기). 프롬프트 문구 변경으로 깨지는 테스트 없음.
- 추천 서비스는 LLM 응답의 `symbol`을 후보 목록과 문자열 비교해 필터링한다
  (`app/domains/watchlists/recommendations_service.py`). symbol이 번역되면
  추천 결과가 유실된다.

## Decisions

- **공통 지시문 상수 1개**: `app/adapters/llm/prompts/` 안에 한국어 출력 지시문
  상수를 두고 7종 프롬프트가 공유한다 (파일 위치는 `__init__.py` 또는 신규
  `language.py` 중 구현 시 선택). 문구 취지: "자연어 필드(rationale, note,
  summary, headline, body, risk_checks 등)는 한국어로 작성한다. JSON 키,
  symbol, enum 값은 원문 그대로 유지한다."
- **적용 방식**: 상수 4종은 문자열 말미에 이어 붙이고, 함수 3종은 반환 문자열에
  포함한다. 프롬프트 구조·기존 지시 내용은 변경하지 않는다.
- **테스트**: 7종 프롬프트(함수형은 호출 결과)가 공통 지시문을 포함하는지
  단언하는 테스트를 추가한다.

## Out of Scope

- FE 변경, mock 응답 한국어화 (mock은 결정적 테스트 픽스처 — 유지)
- 프롬프트 품질 개선·재작성
- 사용자별 언어 설정 (다국어 요구가 생기면 별도 설계)
