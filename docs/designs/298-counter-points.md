# 298 — research-summary counter_view 구조화 (counter_points 추가)

Status: Handoff Ready

## 1. 배경

FE 반대 관점 카드 재설계(project_stock_frontend#188)의 선행 작업입니다.
현재 `counter_view: list[str]`은 문자열 나열이라 FE에서 불릿 목록 외의
표시가 어렵습니다. 근거 유형·강도·출처를 담는 구조화 필드를 additive로
추가합니다.

- 이슈: #298
- 연계: FE #188

## 2. 범위

포함:

- `app/domains/research_summary/schema.py` — `CounterPoint` 모델,
  `ResearchSummaryResponse.counter_points` 필드 추가.
- `app/domains/research_summary/service.py` — mock 템플릿 2종에
  `counter_points` 데이터 추가, 응답 조립 반영.
- 테스트 갱신.

제외: `counter_view` 제거(FE 전환 후 후속 이슈), LLM 실생성 연동,
DB 변경 없음(mock 단계).

## 3. 변경

### schema.py

- `CounterBasisType` — `str` 기반 Enum:
  `VALUATION | FUNDAMENTALS | COMPETITION | MACRO | SENTIMENT`
- `CounterPointStrength` — `str` 기반 Enum: `WEAK | MODERATE | STRONG`
- `CounterPoint(BaseModel)`:
  - `id: str`
  - `claim: str` — 반대 주장 한 문장
  - `basis: str` — 뒷받침 근거 설명
  - `basis_type: CounterBasisType`
  - `strength: CounterPointStrength`
  - `source_label: str | None = None` — 출처 표시 라벨 (mock 단계 null 허용)
- `ResearchSummaryResponse.counter_points: list[CounterPoint] =
  Field(default_factory=list)` — `counter_view` 아래에 additive 추가.
  기존 필드·순서 변경 없음.

### service.py

- `_SummaryTemplate`에 `counter_points` 항목 추가 (TypedDict).
- 템플릿 2종에 각 2건씩 counter_points 부여 — 기존 counter_view 문구와
  의미가 일치하도록 작성:
  - BUY_CANDIDATE: 가격 선반영(VALUATION·MODERATE), 경쟁 심화
    (COMPETITION·WEAK) 계열.
  - WATCH: 개선세가 예상보다 강함(FUNDAMENTALS·MODERATE), 우려 선반영
    (SENTIMENT·WEAK) 계열.
  - `source_label`은 "AI 분석"으로 통일.
- `get_summary` 응답 조립에 `counter_points` 포함
  (`CounterPoint.model_validate`).

## 4. Risks / Notes

- additive 변경 — 기존 FE(counter_view 소비)는 영향 없음.
- enum 값은 FE와 계약이므로 리터럴 출처를 이 문서로 명시한다
  (quality-process-policy 규율).

## 5. 테스트

- 기존 research_summary 테스트에 counter_points 필드 단언 추가:
  템플릿별 건수·필드 구성, enum 값 직렬화(대문자 문자열).
- 검증 3종: `uv run ruff check .` · `uv run mypy .` · `uv run pytest`.

## 6. 관련 링크

- 이슈 #298, FE #188
