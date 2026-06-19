# 033 Decision Checklist API

## Scope

매수 전 사용자가 스스로 확인할 수 있는 4개 체크 항목과 판단 메모 저장 API를 제공한다. 자동 주문 또는 자동 매매 동작은 포함하지 않는다.

## Data Model

`buy_checklist_notes`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `user_id` | FK users | Yes | 인증 사용자 |
| `asset_id` | FK assets | Yes | 대상 종목 |
| `memo` | `Text` | No | 사용자 판단 메모 |
| `checked_item_keys` | `JSON list[str]` | Yes | 기본값 `[]` |
| `decided_at` | `DateTime` | No | 현재 체크리스트가 완료 상태가 된 시각 |

`user_id + asset_id` is unique.

## API

`GET /api/v1/assets/{asset_id}/buy-checklist`

- Auth: Required
- Response: `asset_id`, `items`, `memo`, `checked_item_keys`, `is_complete`, `decided_at`

`PUT /api/v1/assets/{asset_id}/buy-checklist`

- Auth: Required
- Request: `memo?`, `checked_item_keys`
- Response: same as GET after saving

## Completion Rule

`is_complete` is true only when the memo has non-whitespace text and all required item keys are checked:

- `valuation`
- `news_overheated`
- `portfolio_concentration`
- `earnings_disclosure`

`decided_at` remains `null` while the checklist is incomplete. It is set when the checklist first becomes complete and is preserved while subsequent saves keep it complete.

## Decisions

- Notes are scoped to the authenticated user, so another user receives their own empty checklist state.
- Rule output is intentionally simple and deterministic; future signal/portfolio integration can refine item details without adding automatic trading behavior.
