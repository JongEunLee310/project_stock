# Design — Issue 267: research-summary 구조화 확장

FE 리서치 상세의 AI 브리핑을 "상세 분석을 읽기 전의 요약 지도"로 만들기 위해
research-summary 계약을 구조화한다. 현재는 headline·body 문단과 key_risks만
있다. FE 소비 이슈는 project_stock_frontend #145, 로드맵 에픽은 FE #152.

## Background

- `GET /api/v1/assets/{asset_id}/research-summary` —
  `ResearchSummaryResponse(asset_id, stance, stance_confidence, headline,
  body, key_risks, created_at)`.
- 소스는 `ResearchSummaryService`의 결정적 mock 템플릿(`_SUMMARY_TEMPLATES`,
  `asset.id % 2` 로테이션). 실 LLM 전환은 별도 로드맵이므로 이번 확장도
  템플릿에 신규 필드 콘텐츠를 추가하는 방식이다. DB·마이그레이션 없음.
- 확정 원칙(에픽 #152): 신뢰도는 수치 단독이 아니라 근거 문장과 함께,
  스탠스는 매매 명령이 아니라 검토 상태이므로 한 줄 설명을 동반한다.
- 리스크는 이름만이 아니라 "무엇이·왜·어떤 상황에서·무엇을 확인해야
  하는지"를 근거 불릿으로 동반한다.

## Schema 변경 — `app/domains/research_summary/schema.py`

기존 필드는 유지하고 신규 필드는 전부 기본값이 있는 optional로 추가한다
(하위 호환 — 기존 소비처 파손 없음).

- `ResearchSummaryResponse` 추가 필드:
  - `stance_comment: str | None = None` — 스탠스 한 줄 설명.
  - `positive_factors: list[str] = []` — 긍정 요인 불릿.
  - `caution_factors: list[str] = []` — 주의 요인 불릿.
  - `next_checks: list[str] = []` — 다음 확인 사항 불릿.
  - `confidence_basis: str | None = None` — 신뢰도 근거 문장.
- `ResearchRisk` 추가 필드:
  - `evidence: list[str] = []` — 리스크 근거 불릿.

네이밍 참고: reports 도메인의 `positive_factors`와 동일 리터럴을 재사용한다.
부정 축은 브리핑 의미(주의 환기)에 맞춰 `caution_factors`로 한다
(reports의 `negative_factors`와 의미가 달라 리터럴을 일치시키지 않는다).

## Service 변경 — `app/domains/research_summary/service.py`

- `_SummaryTemplate` TypedDict에 위 신규 키를 추가하고,
  `_SUMMARY_TEMPLATES` 두 템플릿에 한국어 콘텐츠를 채운다. 톤은 기존
  템플릿과 동일하게 단정 대신 점검 유도형 문장으로 한다.
  - 각 템플릿: `positive_factors`·`caution_factors`·`next_checks` 각 2~3개,
    `stance_comment`·`confidence_basis` 각 1문장, key_risks 항목별
    `evidence` 1~2개.
- `get_summary`의 응답 조립에 신규 필드 매핑을 추가한다. 로테이션 방식과
  기존 필드 값은 변경하지 않는다.

## API

- 엔드포인트·경로·인증 변경 없음. 응답 스키마만 확장된다.

## Test — `tests/`

- 기존 research-summary 테스트가 수정 없이 통과한다 (하위 호환 검증).
- 추가: 두 템플릿 각각에 대해 신규 필드가 비어 있지 않은 값으로 반환되는지,
  `evidence`가 key_risks 항목에 포함되는지, 결정성(같은 asset_id → 같은
  응답) 유지.

## Out of Scope

- 실 LLM 소스 전환.
- FE 렌더 (FE #145).
- reports·signals 등 다른 도메인 계약 변경.
- DB·마이그레이션 (없음).

## Open Questions

- 없음. 필드명(`caution_factors` 등)은 이 문서로 확정한다.
