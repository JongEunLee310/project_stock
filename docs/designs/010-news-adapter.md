# Design: 뉴스 수집 Adapter (Issue #10)

## Adapter 경계

Adapter는 DB에 직접 의존하지 않는다. 수집 결과를 `NewsAdapterResult` dataclass로 반환하며, Service가 Repository를 통해 저장한다.

## NewsAdapterResult (dataclass)

| 필드 | 타입 |
|---|---|
| title | str |
| url | str |
| body | str \| None |
| source | str |
| published_at | datetime \| None |
| payload | dict \| None |

## NewsAdapter (추상 클래스)

- `fetch(symbols: list[str]) -> list[NewsAdapterResult]`

## 구현체

### MockNewsAdapter

- `fetch(symbols)` — 심볼당 고정 더미 뉴스 2건 반환. 네트워크 호출 없음.

### RSSNewsAdapter

- 생성자: `feed_urls: list[str]`
- `fetch(symbols)` — feedparser로 각 피드 파싱, 심볼 키워드 포함 항목만 반환, 실패 시 로그 후 건너뜀

## Service

### RawNewsService

- `collect_and_save(adapter: NewsAdapter, symbols: list[str]) -> int` — 수집 후 저장, 저장 건수 반환

## 외부 의존성

- `feedparser>=6.0.0` — RSS 파싱

## 의존성

- Issue #8 (RawNewsEvent 도메인) — 수집 결과 저장 대상
