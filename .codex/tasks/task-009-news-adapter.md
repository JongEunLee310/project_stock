# Codex Handoff Task

## Source Issue

Issue #10: 뉴스 수집 Adapter 기본 구조 구현

## Task Summary

뉴스 수집처 교체에 대비한 Adapter 추상 인터페이스를 정의하고, Mock과 RSS 두 가지 구현체를 제공한다. 수집 결과를 `raw_news_events`에 저장하는 Service 연동까지 포함한다.

## Goal

- Adapter 인터페이스를 통해 뉴스 데이터를 수집할 수 있다.
- 수집처를 교체해도 Service 로직이 변경되지 않는다.
- 수집 실패 시 에러 로그가 남는다.

## Background

- **설계 문서를 구현 전에 반드시 읽는다:** `docs/designs/010-news-adapter.md` — Adapter 경계·인터페이스·Service 시그니처
- task-008 완료 후 진행 — `raw_news_events` 테이블과 `RawNewsEventRepository`가 존재해야 한다.
- Adapter는 DB에 직접 의존하지 않는다. 수집 결과는 `NewsAdapterResult` dataclass로 반환하고, Service가 `RawNewsEventRepository`로 저장한다.
- RSS Adapter는 `feedparser` 라이브러리를 사용한다 — `pyproject.toml`에 의존성 추가 필요.
- 관심 종목 키워드는 `symbols: list[str]` 파라미터로 Adapter에 전달한다.

## Implementation Scope

- `pyproject.toml` — `feedparser>=6.0.0` 의존성 추가 (dependencies 섹션)
- `uv.lock` — lock 파일 재생성 (`uv lock`)
- `app/adapters/__init__.py`
- `app/adapters/news/__init__.py`
- `app/adapters/news/base.py` — `NewsAdapter` 추상 클래스, `NewsAdapterResult` dataclass
- `app/adapters/news/mock.py` — `MockNewsAdapter`
- `app/adapters/news/rss.py` — `RSSNewsAdapter`
- `app/domains/raw_news/service.py` — `RawNewsService.collect_and_save(adapter, symbols)` 메서드
- `tests/test_news_adapter.py` — Adapter 단위 테스트

## Out of Scope

- `news_items` 생성 로직 (Issue #14 AI 요약 연동 후 진행)
- Worker/Job enqueue (Issue #11)
- 인증 연동
- RSS 피드 URL 설정 관리 (config에 상수로 추가)

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

### NewsAdapterResult dataclass

```python
@dataclass
class NewsAdapterResult:
    title: str
    url: str
    body: str | None
    source: str
    published_at: datetime | None
    payload: dict | None
```

### NewsAdapter 추상 클래스

```python
class NewsAdapter(ABC):
    @abstractmethod
    def fetch(self, symbols: list[str]) -> list[NewsAdapterResult]: ...
```

### MockNewsAdapter

- `fetch()` 호출 시 심볼당 2개의 고정 더미 뉴스 반환
- 테스트 용도. 외부 네트워크 호출 없음.

### RSSNewsAdapter

- 생성자: `feed_urls: list[str]`
- `feedparser.parse(url)`로 각 피드를 파싱
- `entry.title`, `entry.link`, `entry.summary`, `entry.published_parsed`를 `NewsAdapterResult`로 변환
- `symbols` 중 하나라도 제목 또는 요약에 포함된 항목만 반환 (대소문자 무관)
- 피드 파싱 실패 시 `logger.error()`로 기록하고 해당 피드 건너뜀 (예외 미전파)

### RawNewsService.collect_and_save

- `adapter.fetch(symbols)` 호출
- 각 결과를 `RawNewsEventRepository.create_or_skip(result)` 로 저장 (중복 URL → skip)
- 저장된 건수 반환

## Test Requirements

- `tests/test_news_adapter.py`:
  - MockNewsAdapter: `fetch()` 결과 건수 검증 (심볼 2개 → 결과 4개)
  - RSSNewsAdapter: `feedparser.parse`를 mock 처리해 파싱 결과 검증
  - RSSNewsAdapter: 파싱 실패 시 예외 미전파 검증
  - `RawNewsService.collect_and_save`: Mock Adapter + 인메모리 DB로 저장 건수 검증

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_news_adapter.py -v
```

## Documentation Impact

없음.

## ADR Need

없음.

## Failure Record Need

없음.

## Risk Level

Low — 신규 모듈 추가. 기존 도메인 변경 최소. `feedparser` 의존성 추가는 `pyproject.toml` 변경을 수반하지만 CI 영향 없음.

## Expected Output

- 위 scope 파일 전체 신규 생성
- `pyproject.toml`에 `feedparser>=6.0.0` 추가
- `uv run pytest tests/test_news_adapter.py` 통과
- lint/typecheck 통과

## Rules

- 구현 전 설계 문서(`docs/designs/010-news-adapter.md`)를 읽고 인터페이스·시그니처를 설계 문서 기준으로 구현한다. 설계 문서와 충돌하는 구현은 금지한다.
- task-008 완료 확인 후 진행.
- Adapter는 DB Session을 직접 받지 않는다.
- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
