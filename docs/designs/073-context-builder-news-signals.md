# 073 · LLM 데이터 파이프라인 6.5단계 — ContextBuilder 뉴스·시그널 배선

Status: Draft
작성: Claude Code (orchestrator)
관련: Epic BE #174(LLM 사전 데이터 수집·가공 파이프라인 v0.1), 구현 이슈 BE #189,
Milestone 데이터 수집 파이프라인 — 백엔드(#5). 기준 문서 `docs/knowledge/llm-data-pipeline.md`
(§5.4·§6.7·§7). 선행 설계 `docs/designs/072-context-builder.md`(6단계 Decision AA — 뉴스·시그널은
6.5 후속으로 분리).

## 1. 배경

6단계(#187, PR #188)에서 `ContextBuilder`가 `LLMContextBundle`을 조립하되, Core slice 범위로
`SymbolCard.recent_news`·`SymbolCard.signals`를 빈 리스트로 두고 `news_data_status=missing`
경고를 상시 표기했다(Decision AA). 6.5단계는 이 두 소스를 실제로 배선한다. 뉴스는
`NewsItemRepository.list_by_asset`, 시그널은 `SignalRepository.list_by_asset`로 각각 읽어
계약 타입(`RecentNewsItem`·`SignalItem`)으로 매핑하고, `news_data_status`를 실제 가용성으로
전환한다.

계약(`RecentNewsItem`: title·summary·source·published_at·trust_level, `SignalItem`:
type·severity·reason)은 1단계에서 이미 정의돼 있다. 이번 단계는 계약을 채우는 매핑 로직만
추가하며, 소스 도메인(news·signals)은 읽기 전용으로 재사용한다.

두 소스는 `build_symbol_context`가 이미 수행하는 자산 조회(`asset_id`)에 의존하므로, 자산이
해석될 때만 조회한다. 자산 미해석·소스 결손 시 6단계와 동일하게 예외 없이 빈 리스트로 degrade한다.

## 2. 범위

포함:

- `build_symbol_context`에 뉴스·시그널 조회·매핑 추가:
  - `recent_news`: `NewsItemRepository.list_by_asset(asset_id)` 최근 N건 → `RecentNewsItem` 매핑.
  - `signals`: `SignalRepository.list_by_asset(asset_id, include_expired=False)` 활성 N건 →
    `SignalItem` 매핑.
- `data_quality.news_data_status` 산출 전환: 번들 내 뉴스 존재 시 `valid`, 없으면 `missing`.
  상시 뉴스 경고 문구(`_NEWS_MISSING_WARNING`) 제거, missing일 때만 경고.
- 매핑 보정 헬퍼: `trust_level` 기본값 산출, `severity` 결손 보정(score 버킷), nullable 필드
  (summary·published_at) 안전 채움.
- 뉴스·시그널 배선·degradation·news_data_status 전환을 검증하는 단위 테스트 추가·갱신.

비포함(후속·변경 없음):

- 계약(`llm_context/schema.py`)·소스 도메인(news·signals)·마이그레이션·route 불변.
- `trust_level` 출처 기반 정밀 산출 — `NewsItem`에 미영속이라 보수적 기본값. 출처 신뢰도
  테이블·보강은 별도 후속(Decision GG).
- `LLMContextBundle` 영속·route 노출 — 7단계 `llm_analysis` 이후.
- 뉴스·시그널 조회의 성능 최적화(배치 조회) — 현재 수동 소수 심볼 범위 밖(S1 연장선).

## 3. 구성 요소

### 3.1 `build_symbol_context` 확장 (`app/domains/llm_context/context_builder.py`)

| 변경 | 책임 |
| --- | --- |
| `recent_news` 채움 | 자산 해석 시 `NewsItemRepository.list_by_asset(asset.id)` 최근 N건을 `RecentNewsItem`으로 매핑. 자산 미해석 시 `[]` |
| `signals` 채움 | 자산 해석 시 `SignalRepository.list_by_asset(asset.id, include_expired=False, limit=N)` → `SignalItem`으로 매핑. 자산 미해석 시 `[]` |

### 3.2 매핑 규칙

| 대상 필드 | 소스 | 규칙 |
| --- | --- | --- |
| `RecentNewsItem.title` | `NewsItem.title` | 직접 |
| `RecentNewsItem.summary` | `NewsItem.summary` | nullable → 빈 문자열 대체 |
| `RecentNewsItem.source` | `NewsItem.source` | 직접 |
| `RecentNewsItem.published_at` | `NewsItem.published_at` | nullable → `created_at` 대체 |
| `RecentNewsItem.trust_level` | (미영속) | 보수적 기본값 상수(예: `"unknown"`) |
| `SignalItem.type` | `Signal.signal_type` | 직접 |
| `SignalItem.severity` | `Signal.risk_level` | nullable → `score` 버킷 파생 |
| `SignalItem.reason` | `Signal.reason` | 직접 |

### 3.3 `data_quality.news_data_status` 산출

| 필드 | 규칙(6.5) |
| --- | --- |
| `news_data_status` | 번들 내 어느 심볼이든 뉴스 존재 시 `valid`, 전무하면 `missing` |
| `warnings` | 뉴스 `missing`일 때만 사유 표기(상시 문구 제거). 가격·포트폴리오 규칙은 6단계 유지 |

## 4. Decisions

- **FF. 자산 해석 조건부 조회**: 뉴스·시그널은 `asset_id`가 있어야 조회 가능하므로
  `build_symbol_context`의 자산 해석 결과가 있을 때만 조회한다. 자산 미해석 시 빈 리스트로 degrade
  (6단계 Decision DD 연장).
- **GG. trust_level 보수적 기본값**: `NewsItem`에 `trust_level`이 미영속(스펙 §5.4엔 존재)이므로
  이번 단계는 보수적 기본값 상수로 채운다. 출처 신뢰도 산출은 수집·검증 단계에서 영속 필드가
  생기는 시점의 후속으로 둔다. LLM이 신뢰도를 과신하지 않도록 낙관적 기본값("high")은 쓰지 않는다.
- **HH. severity 결손 보정**: `Signal.risk_level`이 nullable이라 `SignalItem.severity`(required)
  매핑 시 결손이면 `score` 버킷으로 파생한다. 버킷 임계는 상수로 문서화한다.
- **II. 활성 시그널만**: 만료 시그널은 LLM 맥락을 흐리므로 `include_expired=False`로 활성만 담고
  최근 N건으로 제한한다. 뉴스도 최근순 N건으로 제한한다.
- **JJ. 계약·소스·마이그레이션 불변**: 계약(`schema.py`)·news·signals 도메인·마이그레이션·route는
  건드리지 않는다. `context_builder.py` 매핑 로직과 테스트만 변경한다. 단일 head `c3d4e5f60058` 유지.

## 5. 마이그레이션

없음. 스키마 변경이 없다(Decision JJ). alembic 단일 head `c3d4e5f60058` 유지.

## 6. 테스트

- 뉴스 배선: 자산에 뉴스가 있으면 `recent_news`가 `RecentNewsItem`으로 채워지고 `summary`·
  `published_at` nullable이 안전 대체된다.
- 시그널 배선: 활성 시그널이 `SignalItem`으로 매핑되고, `risk_level` 결손 시 `severity`가 score
  버킷으로 채워지며 만료 시그널은 제외된다.
- `news_data_status`: 뉴스 존재 시 `valid`, 전무 시 `missing` + 경고. 상시 경고 문구가 사라진다.
- degradation: 자산 미해석·뉴스/시그널 부재 시 예외 없이 빈 리스트.
- 6단계 기존 테스트가 새 산출(뉴스 존재 시 `valid`)에 맞게 갱신되어도 그 외 단언은 유지된다.
- CI 3종(ruff + mypy + pytest) 통과.

## 7. ADR 판단

불필요. 6단계에서 예고한 Core slice 후속 배선이며, 계약·미영속·graceful degradation 등 기존
결정의 연장선이다. `trust_level` 영속화·출처 신뢰도 테이블은 필요가 구체화되는 수집·검증 단계에서
별도로 판단한다.
