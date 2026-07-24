# Backend Conventions

백엔드(`app/`)의 코드 구조·문서화 컨벤션을 명문화한다. 전면 코드 분석(2026-07-24, 이슈 #420)에서 코드는 일관적이나 몇 가지 규약이 암묵적으로만 존재함을 확인했고, 재발 방지를 위해 이 문서에 규약을 고정한다.

기존 코드를 소급 강제하지 않으며, 신규 코드부터 적용한다.

## Domain Layout

도메인은 `app/domains/<name>/` 아래에 배치하며, 표준 레이어 파일은 다음과 같다.

- `model.py` — SQLAlchemy ORM 모델
- `repository.py` — 영속성 접근(쿼리)
- `schema.py` — Pydantic 요청·응답·projection 타입
- `service.py` — 비즈니스 로직
- `types.py` — 도메인 내부 공용 타입(선택)

### Repository 생략 규약

read-only projection·집계 전용 도메인은 `repository.py`를 두지 않고 `service.py`에서 직접 쿼리한다. 별도 영속성 계층을 두는 것이 부가 가치 없이 파일만 늘리기 때문이다. 현재 이 방식을 따르는 도메인은 `alert_engine`, `analysis`, `benchmark`, `catalysts`, `dashboard`, `research_coverage`, `asset_events`다.

쓰기(생성·수정·삭제)를 수행하거나 쿼리가 여러 service에서 재사용되면 `repository.py`를 도입한다.

### Service 분할 규약

한 도메인의 비즈니스 로직은 기본적으로 단일 `service.py`에 둔다. 관심사가 뚜렷이 갈리고 각 관심사가 독립적으로 커질 때만 접미사 파일(`<concern>_service.py`)로 분할한다. 예: `watchlists`의 `sparkline_service.py`·`trend_service.py`, `portfolios`의 `briefing_service.py`. 분할은 파일 크기가 아니라 관심사 경계를 기준으로 판단한다.

### 하위 구성요소 배치

도메인 하위에 응집된 구성요소 묶음을 둘 때는 파일명 prefix가 아니라 서브디렉터리로 분리한다. 기준 예시는 `signals/rules/`이며, `theses/conflicts/`(#419)가 같은 방식을 따른다.

## Docstring

### 언어

docstring 본문 산문은 한국어로 작성한다. 코드 기호(식별자·경로·enum 값·타입명)는 영어로 유지한다. 이는 문서 본문 언어 규약(`docs/harness/design-record-policy.md`)과 일관된다.

과거 `news_insights/*`에 영어 docstring이 다수 존재한다. 해당 파일을 손댈 때 한국어로 점진 이관하며, 이관만을 위한 대량 변경은 별도로 다루지 않는다.

### 작성 대상

전면 docstring을 강제하지 않는다. 다음 우선순위로 작성한다.

1. 계약이 코드만으로 드러나지 않는 함수 — WHY·인자·반환·예외를 설명해야 하는 것(복잡한 파이프라인·게이트웨이·규칙 평가 등).
2. service·repository의 public 메서드.
3. Pydantic schema·model 클래스는 필드가 자기설명적이므로 클래스 1줄 요약만 선택적으로 둔다. 전면 작성은 권장하지 않는다.

private helper(`_`로 시작)는 이름과 본문으로 의도가 드러나면 생략한다.

### 형식

Google 스타일을 따른다.

```
"""한 줄 요약.

필요 시 상세 설명 문단.

Args:
    param: 설명.

Returns:
    설명.

Raises:
    ExceptionType: 조건.
"""
```

### ruff pydocstyle 도입 순서

현재 docstring 커버리지가 낮아 `ruff`에 `pydocstyle`(`D`) 룰을 즉시 켜면 대량 위반이 발생한다. 다음 순서로 도입한다.

1. 위 작성 대상 1·2순위(복잡 함수·public service/repository 메서드)를 먼저 채운다.
2. 그다음 `pyproject.toml`의 `[tool.ruff.lint]`에 `select`와 `pydocstyle.convention = "google"`을 추가해 이후 회귀를 CI에서 방지한다.

도입 전까지는 이 문서가 규약의 근거이며, 리뷰에서 이 문서를 참조해 판단한다.

## Related Docs

- `docs/harness/design-record-policy.md` — 문서 본문 언어·문장 구조 원칙.
- `docs/harness/local-review-policy.md` — 리뷰 시 컨벤션 준수 확인.
- `docs/backend-v0.2.md` — 백엔드 통합 가이드와 Domain Map.
