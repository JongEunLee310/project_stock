# Design: research_queue 후속 라운드 — PENDING_ANALYSIS 상태·방어 정리 (#293·#294)

- Status: Accepted
- Issues: #293, #294
- 선행: docs/designs/266-research-queue-contract.md (PR #292 리뷰 후속)

## 1. 배경

PR #292 로컬 리뷰에서 확인된 세 가지 후속을 한 라운드로 처리합니다.

- Q1(#293): `last_updated_at`이 `None`인 자산이 `ANALYZED`로 분류되는 문제.
- S1(#294): `_build_summary`와 `_apply_filter`가 `utc_now()`를 각각 호출해 UTC 자정 경계에서 불일치 가능.
- S2(#294): `_top_signal_type`이 우선순위 목록 외 시그널 타입을 `min()` 결과로 노출.

## 2. 계약 변경 (#293 — additive enum 값)

`ResearchStatus`에 `PENDING_ANALYSIS` 값을 추가합니다.

```
class ResearchStatus(str, Enum):
    ANALYZED         = "ANALYZED"
    NEEDS_ATTENTION  = "NEEDS_ATTENTION"
    COLLECTING       = "COLLECTING"
    INSUFFICIENT     = "INSUFFICIENT"
    STALE            = "STALE"
    PENDING_ANALYSIS = "PENDING_ANALYSIS"   # 신규
```

### 판정 우선순위 개정 (§4.1 개정)

| 조건 | 상태 |
| --- | --- |
| 활성 시그널에 `RISK_ALERT`·`THESIS_BROKEN` 있음 | `NEEDS_ATTENTION` |
| `completeness_pct < 30` | `INSUFFICIENT` |
| `completeness_pct < 70` | `COLLECTING` |
| `last_updated_at is None` | `PENDING_ANALYSIS` (신규) |
| `last_updated_at`이 30일 이전 | `STALE` |
| 나머지 | `ANALYZED` |

근거: 완성도가 낮은 자산은 기존 규칙(INSUFFICIENT/COLLECTING)이 우선한다.
정량 축(가격·재무·밸류에이션)은 확보했지만 분석 활동 기록(뉴스·리포트·시그널)이
전혀 없는 자산만 `PENDING_ANALYSIS`로 분류된다.

### summary 카운트 반영

`PENDING_ANALYSIS`는 "리서치 결과를 신뢰할 수 없는 상태"이므로
`_NEEDS_RESEARCH_STATUSES`에 포함한다 (needs_research 카운트·필터에 반영).

## 3. 방어 정리 (#294 — 계약 변경 없음)

- `list_queue` 진입 시점에 `now = utc_now()`·`today_start`를 한 번 계산해
  `_build_summary`·`_apply_filter`에 인수로 전달 — 시그니처 변경은 내부 메서드에
  한정.
- `_top_signal_type`: `WATCHLIST_STATUS_PRIORITY` 순회 후 일치가 없으면
  `min()` fallback 대신 `None` 반환.

## 4. 문서 영향

- `docs/designs/266-research-queue-contract.md` §4.1 표에 위 개정 반영.
- `docs/api/frontend-api-spec.md` research-queue 계약의 `research_status`
  값 목록에 `PENDING_ANALYSIS` 추가.

## 5. Test / Verification

- `last_updated_at=None` + 완성도 ≥ 70 → `PENDING_ANALYSIS`.
- `last_updated_at=None` + 완성도 < 70 → 기존 규칙 우선 (`COLLECTING`).
- `PENDING_ANALYSIS`가 needs_research 카운트·`needs_research` 필터에 포함.
- 우선순위 외 타입만 존재 → `signal_type=None`.
- 자정 경계 단일화: `list_queue`가 `utc_now()`를 한 번만 호출함을 검증
  (monkeypatch 호출 횟수 또는 동등 단언).
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest`
