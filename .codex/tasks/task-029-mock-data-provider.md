# Codex Handoff Task

## Source Issue

Issue #49 (제목 Issue 29): `[BE] Mock Data Provider 구조 추가`

## Task Summary

외부 API 키 없이 백엔드를 기동할 수 있도록 시세/공시/포트폴리오 어댑터 경계를 추가(news는 기존 재사용)하고, 프로바이더별 개별 환경 플래그(`mock | real`)로 구현을 전환하는 팩토리를 도입한다. mock 구현은 결정적 샘플 데이터를 반환한다.

## Goal

- `app/adapters/{market,disclosure,portfolio}/`에 `base.py`(ABC) + `mock.py`가 존재한다.
- `app/core/config.py`에 `MARKET_PROVIDER`/`NEWS_PROVIDER`/`DISCLOSURE_PROVIDER`/`PORTFOLIO_PROVIDER`(기본 mock)가 있다.
- 팩토리가 플래그에 따라 provider를 반환하고, `real`은 `NotImplementedError`로 조기 실패한다.
- worker 잡이 `MockNewsAdapter()` 직접 생성 대신 팩토리를 경유한다.

## Background

- 설계 문서: `docs/designs/029-mock-data-provider.md`
- 기존 패턴: `app/adapters/news/{base.py,mock.py}`, `app/adapters/llm/{base.py,mock.py}` — ABC + `@dataclass(frozen=True)` 결과 DTO. 동일 패턴 따른다.
- 현행 와이어링: `app/worker/jobs/news.py`, `app/worker/jobs/analysis.py`가 `MockNewsAdapter()`/`MockLLMClient()`를 직접 인스턴스화.
- real 구현은 후속 이슈 범위 — 본 태스크는 mock + 전환 골격만.

## Implementation Scope

- `app/adapters/market/{__init__.py,base.py,mock.py}` (신규) — `MarketDataProvider` ABC + `MockMarketDataProvider`.
- `app/adapters/disclosure/{__init__.py,base.py,mock.py}` (신규) — `DisclosureProvider` + `MockDisclosureProvider`.
- `app/adapters/portfolio/{__init__.py,base.py,mock.py}` (신규) — `PortfolioProvider` + `MockPortfolioProvider`.
- `app/core/config.py` — 4개 provider 플래그(`Literal["mock","real"]`, 기본 `"mock"`).
- `app/adapters/factory.py` (신규) — `get_market_provider()`, `get_news_adapter()`, `get_disclosure_provider()`, `get_portfolio_provider()`.
- `app/worker/jobs/news.py`, `app/worker/jobs/analysis.py` — `MockNewsAdapter()` 직접 생성을 `get_news_adapter()` 경유로 교체.
- 샘플 데이터(상수 또는 `sample_data.py`).

## Out of Scope

- real(외부 API) provider 구현.
- 신규 도메인/엔드포인트/응답 API (mock 데이터를 소비하는 화면 API는 후속 이슈).
- LLM 어댑터 팩토리화는 선택 — news 와이어링만 필수, LLM은 동일 패턴으로 추가해도 무방(과확장 금지).
- DB 스키마 변경.

## Protected Files

변경하지 않는다:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- 각 `base.py`: `ABC` + `@abstractmethod` 시그니처 + `@dataclass(frozen=True)` 결과 DTO (news 패턴 동일). 비즈니스 로직 없음.
- 메서드(초안, 화면 요구에 맞춰 조정 가능):
  - `MarketDataProvider.get_quote(symbols: list[str]) -> list[QuoteResult]`
  - `DisclosureProvider.fetch(symbols: list[str]) -> list[DisclosureResult]`
  - `PortfolioProvider.fetch_holdings(account_ref: str) -> list[HoldingResult]`
- mock 구현은 입력에 대해 결정적(deterministic) 샘플 반환(기존 `MockNewsAdapter` 스타일).
- 팩토리: 해당 설정 플래그가 `mock`이면 mock 반환, `real`이면 `NotImplementedError("... real provider 미구현")`.
- 설정 검증(`mock|real`)은 시스템 경계인 설정 로딩에서만(`Literal` 타입).

## Test Requirements

- `tests/test_providers.py`(또는 적절 위치): 각 mock provider가 결정적 샘플 반환, 팩토리가 플래그별 올바른 타입 반환, `real` 플래그 시 `NotImplementedError`.
- worker 잡이 팩토리 경유로도 기존 동작 유지(기존 worker 테스트 통과).
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/029-mock-data-provider.md` 작성됨(변경 불필요).
- `.env.example`가 있으면 신규 provider 플래그 추가.

## ADR Need

없음 — 기존 어댑터 패턴 확장. 새 아키텍처 방향 아님.

## Failure Record Need

없음.

## Risk Level

Low~Medium — 신규 어댑터/설정 추가 + worker 와이어링 1곳 교체. 기존 mock 동작 유지로 회귀 표면 작음. Human Gate 불필요(DB 변경 없음).

## Expected Output

- 신규 어댑터 3종 + 팩토리 + 설정 플래그, worker 와이어링 교체, 샘플 데이터.
- 테스트 통과, lint/typecheck 통과.
- PR body에 `Closes #49`.

## Rules

- real provider 구현 금지(NotImplementedError 골격만).
- 과확장 금지 — 현재 필요한 어댑터/메서드만.
- 보호 파일 변경 금지.
- 가정과 검증 결과 보고.
