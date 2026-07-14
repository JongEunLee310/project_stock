# Design: 리뷰 후속 정리 라운드 (#309)

- Status: Accepted
- Issue: #309
- 출처: PR #283–#291 로컬 리뷰 비차단 소견

## 1. 범위

와이어 계약 변경이 없는 정리 8건 (7번만 태스크 리포트 additive).

| # | 출처 | 파일 | 내용 |
| --- | --- | --- | --- |
| 1 | PR #285 S1 | `app/api/v1/endpoints/assets.py` | earnings-summary description의 "deterministic mock" 문구를 실수집 반영 문구로 정정 |
| 2 | PR #286 S1 | `app/domains/valuation/history.py` | `continue` 이후 도달하지 않는 `if eps is not None` 필터 제거 |
| 3 | PR #291 S2 | `app/domains/signals/repository.py` | `prev_captured_at`에만 `type_coerce`를 쓰는 이유 한 줄 주석 |
| 4 | PR #283 S1 | `app/domains/benchmark/service.py` | 동일 (symbol, market) 시리즈의 `get_daily_closes` 중복 호출을 캐싱으로 제거 |
| 5 | PR #284 S1 | `app/adapters/market/mock.py` | `fcf_yield` 음수 범위가 의도임을 주석으로 명시 |
| 6 | PR #290 | `docs/knowledge/workflow.md` | env 접두사 없는 `uv run pytest` 통과 사실·conftest 두 단계 프로바이더 격리 한 줄 보강 |
| 7 | PR #287 S1 | 리포트 수집 태스크 | 리포트 저장 성공과 이벤트 수집 성공을 별도 카운터로 분리 (태스크 리포트 페이로드 additive) |
| 8 | PR #288 S1 | quote 캐시 설계 문서 | `as_of` 의미(캐시 저장 시각, TTL 60초 내 과거 가능) 명문화 |

## 2. Test / Verification

- 4: 동일 (symbol, market) 시리즈 구성 시 조회가 1회임을 검증.
- 7: 카운터 분리 후 기존 성공/실패 집계 회귀 없음 + 이벤트 실패 시 별도 카운터 검증.
- 나머지: 기존 테스트 회귀 없음.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest`
