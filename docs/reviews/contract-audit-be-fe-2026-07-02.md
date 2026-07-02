# BE↔FE API 계약 불일치 점검 기록 (2026-07-02)

## Status

Recorded

## 배경

BE(`project_stock`)와 FE(`project_stock_frontend`) 사이 API 계약이 실제로 맞는지 점검했다.
각 스택이 독립적으로 기동·빌드되는지 확인하는 smoke test는 통과했으나, smoke test는
요청·응답 스키마의 필드 단위 정합성까지는 검증하지 못한다. 그래서 BE의 OpenAPI 스키마와
FE의 DTO·adapter를 직접 대조했다.

대조 기준은 다음과 같다.

- BE는 실행 중인 애플리케이션에서 생성한 OpenAPI 스펙(`components.schemas`, 각 path의 `response_model`)을 사용했다.
- FE는 `src/shared/api/*`(client·envelope·paging)와 각 `src/features/*/dto.ts`·`adapters.ts`를 사용했다.
- FE의 base URL은 `VITE_API_BASE_URL=http://localhost:8000/api/v1`이므로, FE 경로는 BE의 `/api/v1` 접두사에 대응시켜 비교했다.

## 이상 없는 영역

- **경로·메서드**: FE가 호출하는 경로 전부가 BE 엔드포인트(총 51개)에 존재한다. 누락이나 오타는 없다.
- **Envelope**: FE `ApiEnvelope`(`data`, `message`, `error`, `meta`)가 BE `ApiResponse`와 일치하고,
  `ApiMeta`(`page`, `size`, `total`)가 BE `PageMeta`와 일치한다.
- **Pagination**: FE가 보내는 `page`·`size`·`sort`(`-field` 형식) 파라미터가 BE `PaginationParams`·`sort_param` 규약과 맞는다.
- **expand=asset**: `signals`·`watchlist items`·`alert-candidates` 목록은 BE가 `list[Any]`로 응답하므로,
  FE가 기대하는 중첩 `asset` 객체가 `response_model`에 의해 제거되지 않는다. 정상이다.

## 계약 불일치

FastAPI는 `response_model`에 정의되지 않은 필드를 응답에서 제거한다. 따라서 FE가 읽는 필드가
BE 스키마에 없으면 FE는 `undefined`를 받고, FE는 대부분 `?? 기본값`으로 방어하고 있어 화면에
빈 값이나 기본값이 조용히 표시된다. 런타임 크래시는 발생하지 않으며, 이런 종류의 불일치는
smoke test로는 드러나지 않는다.

| # | 심각도 | 엔드포인트 | 불일치 내용 | 사용자 영향 |
|---|--------|-----------|------------|------------|
| 1 | High | `GET /assets/{id}/research-summary` | BE `ResearchSummaryResponse`는 `asset_id`, `positive_factors`, `negative_factors`, `items_to_verify`, `sources`, `updated_at`를 반환한다. FE `ResearchSummaryDto`는 `stance`, `stance_confidence`, `headline`, `body`, `key_risks`, `created_at`를 기대한다. 겹치는 필드가 사실상 없다. | 리서치 요약이 항상 `판단 보류`·`리서치 요약 없음`으로, `keyRisks`는 빈 배열로 표시된다 |
| 2 | High | `GET /assets/{id}/buy-checklist` | BE item은 `key`, `label`, `status`, `detail` 구조다. FE item은 `id`, `label`, `description`, `checked`를 기대한다. `label`만 살아남는다. | 체크리스트 설명이 공란이고 모든 항목이 미체크 상태로 표시된다 |
| 3 | Medium | `GET /assets/{id}/detail` | FE가 읽는 `market_cap`·`next_earnings_date`가 BE `AssetDetailResponse`에 없다. FE는 `updated_at`을 읽지만 BE는 `as_of`로 내려준다(이름 불일치). 반대로 BE의 `price`·`previous_close`·`change`·`change_percent`·`currency`는 FE가 사용하지 않는다. | 시가총액·다음 실적일·갱신 시각이 항상 비어 보인다 |
| 4 | Medium | `GET /reports` | FE `ReportDto`가 기대하는 `title`·`source`가 BE `ResearchReportResponse`에 없다. | 리포트 제목이 undefined로 표시된다 |
| 5 | Medium | `GET /auth/me` | BE `UserResponse`는 `id`, `email`, `is_active`를 반환한다. FE `MeDto`는 `id`, `email`, `username`, `created_at`를 기대한다. | 설정 화면에서 사용자명이 `사용자`·`-`로 표시된다 |
| 6 | Low | `GET /theses/latest` | FE `ThesisDto`가 기대하는 `title`이 BE `ThesisResponse`에 없다. | thesis 제목이 undefined로 표시된다 |
| 7 | Low | `GET /alerts` | FE `AlertDto`가 기대하는 `title`이 BE `AlertResponse`에 없다(typed 응답이라 제거된다). | 알림 제목이 undefined로 표시될 수 있다 |
| 8 | Low | `GET /assets`, `GET /assets/{id}` | FE가 읽는 `sector`가 BE `AssetResponse`에 없다. | portfolio에는 `UNKNOWN` fallback이 있어 영향이 작다 |

## 해석

1·2·6번(research·thesis) 묶음은 FE가 AI 정성 계약을 먼저 반영한 상태로 보인다.
정량 파생 mock은 소진되었고 남은 영역이 정성·AI 계약이라는 기존 정리와 맞물린다.
BE의 `research-summary`·`buy-checklist` 응답 스키마가 아직 FE가 기대하는 정성 형태로
정의되지 않았다.

5번(`/auth/me`)은 사용자에게 바로 보이는 값이므로 우선순위가 상대적으로 높다.

## 권장 대응

각 항목은 BE와 FE 중 어느 쪽을 계약 기준으로 삼을지 합의가 필요하다.

- **BE 조정 후보**: `UserResponse`에 `username`·`created_at` 추가(5번), `AssetDetailResponse`의 `as_of`를 `updated_at`으로 정렬하거나 FE가 `as_of`를 읽도록 합의(3번), research 도메인(`research-summary`·`buy-checklist`·`reports`·`theses`)의 정성 응답 스키마 확정(1·2·4·6번).
- **FE 조정 후보**: BE 계약을 그대로 둘 경우 `MeDto`를 `is_active` 기준으로 정렬, research DTO·adapter를 BE 현재 스키마에 맞춰 재작성.

## 후속

- BE issue: JongEunLee310/project_stock#163 — response_model 필드 정렬.
- FE issue: JongEunLee310/project_stock_frontend#101 — DTO/adapter 정렬.
