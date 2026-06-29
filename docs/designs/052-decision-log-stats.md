# 052 · Decision Log Stats (판단 통계)

Status: Frozen
작성: Claude Code (orchestrator)
관련: FE 73 (decision-log-stats-wiring), DecisionLogPage mock 제거(`mockDecisionPatterns`, `mockReviewMemos`)

## 1. 배경

DecisionLogPage 우측 aside의 두 카드가 mock에 의존한다.

- "자주 나온 판단 패턴"(`mockDecisionPatterns`) — 판단 유형별 빈도 분포.
- "최근 복기 메모"(`mockReviewMemos`) — 회고 반성문(텍스트).

목록 API `GET /decision-logs`는 페이지네이션(기본 size=20)이라 FE 클라이언트 집계로는 전체 기간 분포를 진실되게 낼 수 없다. 회고 반성문은 대응 필드가 없으나, REVIEWED 상태 + `reviewed_at`로 "검토된 판단"은 진실되게 식별된다.

진실값 원칙(BE가 진실되게 계산 가능한 값만 노출)에 따라:

- 패턴 → `decision_type`별 전체 기간 count 집계.
- 복기 메모 → 회고 텍스트는 도입하지 않고, 최근 검토(REVIEWED)된 판단을 기존 필드로 노출. FE가 "최근 검토한 판단"으로 재해석.

읽기 전용 집계 엔드포인트 하나로 두 요구를 모두 충족한다. 마이그레이션·신규 모델 없음.

## 2. 범위

포함:

- 신규 읽기 전용 엔드포인트 `GET /api/v1/decision-logs/stats`.
- 응답 스키마 `DecisionLogStatsResponse`.
- 서비스 집계 메서드, 리포지토리 집계/조회 메서드.

비포함:

- 모델/마이그레이션 변경 없음.
- 회고 메모(`review_note`) 필드 신규 도입 없음.
- 기존 목록/단건/생성/수정 엔드포인트 동작 변경 없음.
- 의미 분류(테마/섹터 등) 하드코딩 없음.

## 3. 계약

### 3.1 엔드포인트

`GET /api/v1/decision-logs/stats`

- 인증: `get_current_user` (기존 도메인과 동일).
- 쿼리 파라미터: 없음(고정 정책). 최근 검토 건수 상한은 서버 상수.
- 응답: `ApiResponse[DecisionLogStatsResponse]` (`success` 래퍼).

### 3.2 응답 스키마 `DecisionLogStatsResponse`

| 필드 | 타입 | 책임 |
|------|------|------|
| `decision_type_counts` | `dict[str, int]` | 사용자 전체 판단의 `decision_type`값 → 건수. 0건 유형은 키 생략(존재하는 유형만). |
| `total` | `int` | 사용자 전체 판단 건수(= counts 합). FE 비율 계산 기준. |
| `recent_reviewed` | `list[ReviewedDecisionItem]` | 최근 검토된 판단 상위 N건(`reviewed_at` desc). |

`ReviewedDecisionItem`:

| 필드 | 타입 | 출처 |
|------|------|------|
| `id` | `int` | `DecisionLog.id` |
| `ticker` | `str` | `DecisionLog.ticker` |
| `company_name` | `str \| None` | `DecisionLog.company_name` |
| `decision_type` | `str` | `DecisionLog.decision_type` |
| `reason` | `str \| None` | `DecisionLog.reason` |
| `risk_note` | `str \| None` | `DecisionLog.risk_note` |
| `reviewed_at` | `UtcDatetime` | `DecisionLog.reviewed_at` |

`recent_reviewed`는 `reviewed_at IS NOT NULL`인 항목만 포함하므로 `reviewed_at`은 non-null.

### 3.3 서비스 `DecisionLogService.get_stats`

`get_stats(user_id: int) -> DecisionLogStatsResponse`

책임:

- `repo.count_by_decision_type(user_id)`로 유형별 건수 맵을 얻어 `decision_type_counts`/`total` 구성.
- `repo.list_recent_reviewed(user_id, limit=RECENT_REVIEWED_LIMIT)`로 최근 검토 항목을 얻어 `recent_reviewed` 구성.
- 신규 예외 없음. 0건이면 빈 맵·빈 리스트·`total=0`.

상수: `RECENT_REVIEWED_LIMIT = 5` (서비스 모듈 상수).

### 3.4 리포지토리

| 메서드 | 시그니처 | 책임 |
|--------|----------|------|
| `count_by_decision_type` | `(user_id: int) -> dict[str, int]` | `decision_type` GROUP BY count. 존재하는 유형만 반환. |
| `list_recent_reviewed` | `(user_id: int, limit: int) -> list[DecisionLog]` | `reviewed_at IS NOT NULL` 필터, `reviewed_at` desc 정렬, `limit` 적용. |

기존 `count_by_user`/`list_by_user` 패턴을 따른다. 시세 호출·외부 의존 없음.

## 4. 검증

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest -q` — 신규 테스트: 유형별 집계 정확성(다유형 혼재), `total` 일치, `recent_reviewed`가 reviewed만·정렬·limit 준수, 0건 빈 응답.

## 5. 비고

- 상단 요약 카드 4종(총 기록/이번 주/관망/매도검토)도 현재 첫 페이지 20건 기준이라 부정확하나, 본 설계 범위 밖(별도 후속). 단, `total`/`decision_type_counts`로 후속에서 교정 가능.
- `title`류 합성 없음. FE가 `decision_type` 라벨링·표시 담당.
