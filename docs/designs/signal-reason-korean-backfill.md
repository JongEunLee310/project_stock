# 설계: 시그널 reason 한국어 전환 및 기존 시그널 key_points backfill

- Status: Approved (구두 승인 — 실사용 피드백 라운드)
- Author: Claude Code (Fable 5)
- Date: 2026-07-10
- Related: #260(key_points), PR #261, FE #135(4단계 연결)

## 배경

시그널 카드의 근거 텍스트가 구조화되지 않은 문장으로 보여 스캔이 어렵다는 실사용
피드백이 있었다. 원인은 두 가지다.

1. #260 머지 이전에 생성된 시그널(현재 6건)은 `key_points = NULL`이라 FE 카드가
   reason 폴백으로 렌더된다. 시그널 dedup 때문에 같은 뉴스로는 재생성되지 않아
   이 상태가 계속 유지된다.
2. `HighImpactNewsRule`의 reason이 영어 보일러플레이트
   (`High-impact news requires review: {summary}`)로 시작한다. "검토 필요"라는
   정보는 signal_type(RISK_ALERT)·risk_level 배지·key_points 불릿("뉴스 영향도는
   HIGH입니다")과 중복이라 문구 자체가 불필요하다.

ThesisConflictRule과 포트폴리오 집중도의 reason은 이미 한국어이므로 범위 밖이다.
FE는 불릿·폴백 렌더가 이미 동작하므로 변경이 없다.

## 변경 1 — HighImpactNewsRule reason 문구

`app/domains/signals/rules/high_impact_rule.py`

- 변경 전: `High-impact news requires review: {summary}`
- 변경 후: `영향도 {impact_level} 뉴스: {summary}`

impact_level(HIGH/CRITICAL)은 enum 값이므로 영어 그대로 둔다. key_points 불릿
3종(영향도·감성·요지)은 변경하지 않는다.

## 변경 2 — 데이터 마이그레이션 (backfill)

새 revision, down_revision = `c3d4e5f60062`.

### upgrade 책임

대상 행: `signals.reason`이 리터럴 접두어 `High-impact news requires review: `로
시작하는 행 전부.

각 대상 행에 대해:

- `summary` = reason에서 접두어를 제거한 나머지.
- `impact_level` = `risk_level` 컬럼 값 (해당 룰은 risk_level에 impact_level을
  그대로 저장한다). NULL이면 해당 행의 reason만 접두어 제거로 갱신하고
  key_points backfill은 건너뛴다.
- `reason` 갱신: 변경 1과 동일한 형식 `영향도 {impact_level} 뉴스: {summary}`.
- `key_points`가 NULL인 행만 backfill: 룰 생성 경로와 동일한 불릿을 재구성한다.
  - `뉴스 영향도는 {impact_level}입니다.`
  - `뉴스 감성은 {sentiment}입니다.` — `evidence` JSON의 sentiment가 non-null일
    때만.
  - `대상 뉴스 요지: {summary}`
  - 저장 형식은 기존 컬럼 규약(JSON 문자열 배열 직렬화)을 따른다.

구현은 connection 조회 → Python 변환 → 행별 UPDATE 방식으로 하고, ORM 모델을
import하지 않는다(마이그레이션 자립성).

### downgrade 책임

no-op. backfill된 key_points와 원래부터 있던 key_points를 구분할 수 없고, reason
원문은 접두어 재부착으로 복원 가능하지만 데이터 정리 마이그레이션의 되돌림
가치가 없다. no-op 사유를 docstring에 남긴다.

## 테스트

- 기존 HighImpactNewsRule 단위 테스트의 reason 리터럴 단언을 새 형식으로 갱신
  (HIGH·CRITICAL 두 경로).
- 마이그레이션 자체는 pytest 대상이 아니다. 검증 절차:
  - 리뷰 단계에서 스크래치 DB에 구형 행(접두어 reason + key_points NULL)을
    시드하고 `alembic upgrade head`로 변환 결과를 확인한다.
  - 머지 후 compose `stock_db`에 컨테이너 안
    `/app/.venv/bin/alembic upgrade head`를 수동 적용한다(이미지에 uv 없음,
    #261 머지 때 인시던트 참고).

## 검증

- `uv run ruff check .` / `uv run mypy .` / `NEWS_PROVIDER=mock uv run pytest`
