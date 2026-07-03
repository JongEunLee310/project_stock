# Codex Handoff Task

## Source Issue

BE #189 (Epic BE #174 6.5단계). 설계 `docs/designs/073-context-builder-news-signals.md`. 기준 문서
`docs/knowledge/llm-data-pipeline.md` §5.4·§6.7·§7. 선행 6단계 `docs/designs/072-context-builder.md`.

## Task Summary

6단계(#187)에서 Core slice로 빈 리스트로 남겨둔 `SymbolCard.recent_news`·`SymbolCard.signals`를
실제 배선한다. 뉴스는 `NewsItemRepository.list_by_asset`, 시그널은 `SignalRepository.list_by_asset`
로 읽어 계약 타입(`RecentNewsItem`·`SignalItem`)으로 매핑하고, `data_quality.news_data_status`를
실제 가용성으로 전환한다. 계약·소스 도메인·마이그레이션·route는 건드리지 않고
`app/domains/llm_context/context_builder.py`의 매핑 로직과 테스트만 수정한다.

## Goal

- `build_symbol_context`가 자산 해석 시 `recent_news`·`signals`를 실제 데이터로 채운다.
- `data_quality.news_data_status`가 뉴스 존재 시 `valid`, 전무 시 `missing`으로 산출된다.
- 자산 미해석·뉴스/시그널 부재 시 예외 없이 빈 리스트로 degrade한다.
- CI 3종(ruff + mypy + pytest) 통과, alembic 단일 head `c3d4e5f60058` 유지(마이그레이션 없음).

## Background

계약은 이미 존재한다(`app/domains/llm_context/schema.py`):

- `RecentNewsItem`: `title: str`, `summary: str`, `source: str`, `published_at: datetime`,
  `trust_level: str` — 모두 required.
- `SignalItem`: `type: str`, `severity: str`, `reason: str` — 모두 required.

재사용할 기존 소스(모두 읽기 전용):

- 뉴스: `app/domains/news/repository.py` `NewsItemRepository.list_by_asset(asset_id: int)
  -> list[NewsItem]`(`created_at` 내림차순). `NewsItem` 필드: `title: str`, `summary: str | None`,
  `source: str`, `published_at: datetime | None`, `created_at: datetime`. `NewsItem`에는
  `trust_level`이 없다(스펙 §5.4엔 있으나 미영속).
- 시그널: `app/domains/signals/repository.py` `SignalRepository.list_by_asset(asset_id: int,
  include_expired: bool, offset: int = 0, limit: int | None = None) -> list[Signal]`(`created_at`
  내림차순, `include_expired=False`면 만료 제외). `Signal` 필드: `signal_type: str`, `score: int`
  (0~100), `risk_level: str | None`, `reason: str`.

`build_symbol_context`는 이미 `AssetRepository.get_by_symbol_market(symbol, market)`로 `asset`을
해석한다. 뉴스·시그널은 `asset.id`로 조회하므로 자산 해석 결과가 있을 때만 조회한다(Decision FF).

## Implementation Scope

수정 대상: `app/domains/llm_context/context_builder.py`, `tests/test_context_builder.py`.

`build_symbol_context` 변경:

- 기존에 `recent_news=[]`, `signals=[]`로 두던 부분을, `asset`이 not None이면 조회·매핑 결과로,
  None이면 빈 리스트로 채운다.
- `recent_news`: `NewsItemRepository.list_by_asset(asset.id)`의 최근 N건(`_RECENT_NEWS_LIMIT`,
  예: 5)을 `RecentNewsItem`으로 매핑.
- `signals`: `SignalRepository.list_by_asset(asset.id, include_expired=False,
  limit=_RECENT_SIGNAL_LIMIT)`(예: 5)를 `SignalItem`으로 매핑.

매핑 규칙:

- `RecentNewsItem`: `title`←`title`, `summary`←`summary or ""`, `source`←`source`,
  `published_at`←`published_at or created_at`, `trust_level`←`_DEFAULT_NEWS_TRUST_LEVEL`
  (상수, 예: `"unknown"`). 낙관적 기본값(`"high"`)은 쓰지 않는다(Decision GG).
- `SignalItem`: `type`←`signal_type`, `severity`←`risk_level` 우선, `None`이면 `score` 버킷 파생
  헬퍼로 결정(Decision HH), `reason`←`reason`.
- severity score 버킷(예): `score >= 70` → `"high"`, `score >= 40` → `"medium"`, 그 외 `"low"`.
  임계는 모듈 상수로 문서화한다.

`data_quality` 변경(`_build_data_quality`/`_price_data_status` 인근):

- `news_data_status`를 하드코딩 `MISSING`에서 산출로 전환: `symbol_cards` 중 어느 하나라도
  `recent_news`가 비어있지 않으면 `VALID`, 전무하면 `MISSING`.
- 상시 뉴스 경고 상수(`_NEWS_MISSING_WARNING`) 자동 추가를 제거하고, `news_data_status==MISSING`일
  때만 뉴스 부재 warning을 추가한다.
- 가격·포트폴리오 상태·경고 규칙은 6단계 그대로 유지한다.

상수 추가: `_RECENT_NEWS_LIMIT`, `_RECENT_SIGNAL_LIMIT`, `_DEFAULT_NEWS_TRUST_LEVEL`,
severity 버킷 임계 상수.

## Out of Scope

- 계약(`app/domains/llm_context/schema.py`) 변경.
- 소스 도메인(`app/domains/news/*`·`app/domains/signals/*`) 변경.
- `trust_level` 출처 신뢰도 정밀 산출·영속 필드 도입 — 별도 후속(Decision GG).
- `LLMContextBundle` 영속·route 노출 — 7단계 이후.
- 뉴스·시그널 배치 조회 최적화(현재 수동 소수 심볼 범위 밖).
- 신규 alembic revision.

## Protected Files

- `app/domains/llm_context/schema.py` — 계약 소비만, 변경 금지.
- `app/domains/news/*`·`app/domains/signals/*`·`app/domains/assets/*`·`app/domains/prices/*`·
  `app/domains/portfolios/*`·`app/domains/decision_logs/*`·`app/domains/features/*` — 참조만, 수정 금지.
- `app/domains/llm_analysis/*`·`app/adapters/llm/*` — 변경 금지.
- `alembic/versions/*` — 신규 revision 금지.
- route/`app/api/*` — 건드리지 않는다.

## Requirements

- `ContextBuilder`는 읽기 전용. 어떤 쓰기·커밋도 하지 않는다.
- 반환·중간 타입 이름에 `Dto`를 쓰지 않는다(projection 네이밍).
- 자산 미해석·뉴스/시그널 부재에서 예외를 던지지 않고 빈 리스트로 degrade한다.
- nullable 소스(`summary`·`published_at`·`risk_level`)는 required 계약에 안전 대체값으로 채운다.
- 타입 주석 완전화(mypy `no-untyped-def` 회피).

## Test Requirements

`tests/test_context_builder.py` 갱신·추가(`db` 세션 fixture 사용):

- 기존 `test_build_context_bundle_maps_available_sources`: 뉴스를 준비하면 `news_data_status`가
  `VALID`가 되도록 갱신하거나, 뉴스 배선 검증을 별도 테스트로 분리한다. 상시 뉴스 경고 문구가 더는
  무조건 붙지 않음을 반영한다.
- 뉴스 배선: 자산에 `NewsItem`을 생성하면 `recent_news`가 `RecentNewsItem`으로 채워지고,
  `summary=None`·`published_at=None`이 각각 `""`·`created_at`으로 안전 대체된다.
- 시그널 배선: 활성 `Signal`이 `SignalItem`으로 매핑되고, `risk_level=None`이면 `severity`가 score
  버킷으로 채워지며, 만료 시그널(`expires_at` 과거)은 제외된다.
- `news_data_status`: 뉴스 있으면 `VALID`, 전무 시 `MISSING` + 부재 warning.
- degradation: 자산 미해석 시 `recent_news`·`signals`가 빈 리스트.
- 필요한 엔티티(User·Asset·StockPriceBar·Portfolio·Position·DecisionLog·NewsItem·Signal)는 직접
  생성으로 준비한다. 외부 API 호출 없이 통과해야 한다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic heads`  # 단일 head c3d4e5f60058 확인(마이그레이션 없음)

## Documentation Impact

설계 `docs/designs/073-context-builder-news-signals.md`·본 핸드오프가 같은 PR에 포함된다. 지침서
§6.7·§7 서술은 이미 뉴스·시그널을 포함하므로 별도 갱신 불필요.

## ADR Need

불필요. 6단계에서 예고한 Core slice 후속 배선으로 기존 결정의 연장선이다.

## Failure Record Need

불필요. 신규 배선 구현이며 알려진 실패 패턴 대응이 아니다.

## Risk Level

Low-Medium. 기존 파일 1개(`context_builder.py`)와 테스트만 수정하고 소스·계약·마이그레이션 변경이
없어 회귀 위험은 낮다. 관건은 nullable 소스의 안전 대체(`summary`·`published_at`·`risk_level`),
`include_expired=False` 활성 필터, `news_data_status` 산출 전환의 정확성이다.

## Decisions 요약 (설계 073 참조)

- **FF. 자산 해석 조건부 조회**: `asset`이 있을 때만 뉴스·시그널 조회, 미해석 시 빈 리스트.
- **GG. trust_level 보수적 기본값**: `NewsItem` 미영속이라 상수 기본값(낙관적 값 금지).
- **HH. severity 결손 보정**: `risk_level` 우선, 결손 시 `score` 버킷 파생.
- **II. 활성 시그널만**: `include_expired=False`, 최근 N건 제한. 뉴스도 최근순 N건.
- **JJ. 계약·소스·마이그레이션 불변**: `context_builder.py`·테스트만 변경, 단일 head 유지.

## Expected Output

`context_builder.py` 매핑 로직 수정 + `tests/test_context_builder.py` 갱신·추가. 검증 명령 4종 결과와
함께 요약.
