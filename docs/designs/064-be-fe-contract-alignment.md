# 064 · BE↔FE 응답 계약 정렬 (Contract Alignment)

Status: Draft
작성: Claude Code (orchestrator)
관련: BE #163, FE #101, 점검 기록 `docs/reviews/contract-audit-be-fe-2026-07-02.md`, 설계 041(계약 스냅샷 테스트)

## 1. 배경

2026-07-02 BE↔FE 계약 점검에서 응답 스키마의 필드 단위 불일치 8건이 확인되었다. FastAPI
`response_model`이 스키마 밖 필드를 제거하므로, FE가 기대하는 필드가 BE 스키마에 없으면 FE는
`undefined`를 받고 화면에 빈 값·기본값이 조용히 표시된다. 크래시가 없어 smoke test로는
드러나지 않는다.

계약 기준 방향은 **BE를 기준으로 확정**하기로 결정했다(사용자 합의). 즉 대부분의 조정을 BE
응답 스키마·서비스에서 수행하고, FE는 BE 확정 후 adapter를 검증·정리한다. research 정성
스키마는 FE가 이미 선반영한 형태(`stance`·`headline`·`body`·`key_risks`)를 BE가 채택한다.

중요한 관찰: FE DTO·adapter는 이미 목표 형태를 기대하며 `?? 기본값`으로 방어하고 있다.
따라서 본 BE 정렬이 머지되면 FE 측 변경은 fallback 제거·검증 수준으로 축소된다(FE #101).

## 2. 범위

포함(BE):

- 응답 스키마 8종 정렬: `UserResponse`, `ResearchSummaryResponse`, `BuyChecklistResponse` item,
  `AssetDetailResponse`, `ResearchReportResponse`, `ThesisResponse`, `AlertResponse`,
  `AssetResponse`.
- 관련 서비스의 응답 조립 로직 조정(mock/파생 값 생성 포함).
- market provider `QuoteResult`에 `market_cap`·`next_earnings_date` 필드 추가(+ mock 값).
- `tests/test_api_contract.py`의 해당 계약 상수·단언 갱신.
- `docs/api/frontend-api-spec.md`·`docs/api/contract-alignment.md` 갱신.

비포함(분리):

- FE 변경 — FE #101에서 BE 머지 후 진행.
- DB 스키마 변경(신규 컬럼·마이그레이션) — 본 정렬은 기존 컬럼·파생 값·mock으로 해결한다.
  실제 사용자 입력 `username`, 실데이터 report `title`/`source` 등은 후속 도메인 작업으로 남긴다.
- research-summary·buy-checklist의 실제 AI·데이터 파이프라인 — 형태(계약) 정렬만 수행하고
  값은 기존 mock 수준을 유지한다.
- 알림 실데이터 파생 규칙 재정의 — 기존 서비스 파생값 위에 `title`만 추가한다.

## 3. 항목별 정렬 정의

각 항목은 "BE 현재 → 목표(FE 기대)" 델타와 데이터 출처를 명시한다. 데이터 출처가 "파생"인
경우 신규 컬럼 없이 기존 값에서 계산한다.

| # | 심각도 | 엔드포인트 | 델타 | 데이터 출처 |
| --- | --- | --- | --- | --- |
| 1 | High | `GET /assets/{id}/research-summary` | factor-list 형태 → 정성 형태로 교체 | mock reshape |
| 2 | High | `GET /assets/{id}/buy-checklist` | item `{key,label,status,detail}` → `{id,label,description,checked}` | 기존 값 매핑 |
| 3 | Medium | `GET /assets/{id}/detail` | `+market_cap`, `+next_earnings_date`, `as_of`→`updated_at` | quote mock + 필드명 정렬 |
| 4 | Medium | `GET /reports` | `+title`, `+source` | `summary` 파생 / mock |
| 5 | Medium | `GET /auth/me` | `+username`, `+created_at` | email local-part 파생 / 기존 컬럼 |
| 6 | Low | `GET /theses/latest` | `+title` | `summary` 파생 |
| 7 | Low | `GET /alerts` | `+title` | 기존 파생값(`alert_type`/`symbol`) 조합 |
| 8 | Low | `GET /assets`, `GET /assets/{id}` | `+sector` | 기존 컬럼 노출 |

## 4. 스키마 변경

### 4.1 UserResponse (#5)

`app/domains/users/schema.py` — `UserResponse`:

| 필드 | 타입 | 변경 | 비고 |
| --- | --- | --- | --- |
| id | int | 유지 | |
| email | str | 유지 | |
| is_active | bool | 유지 | |
| username | str | 추가 | email local-part 파생(`email.split("@")[0]`), 본 단계는 컬럼 미도입 |
| created_at | UtcDatetime | 추가 | `User`는 `TimestampMixin`으로 `created_at` 보유, 노출만 추가 |

`/auth/me`는 `UserResponse.model_validate(current_user)`로 조립되므로, `username` 파생은
스키마의 computed field 또는 서비스/엔드포인트 매핑으로 채운다. `created_at`은 `from_attributes`로
자동 노출된다.

### 4.2 ResearchSummaryResponse (#1)

`app/domains/research_summary/schema.py` — 기존 factor-list 필드를 정성 필드로 교체한다.

`ResearchRisk(BaseModel)`(신규):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| id | str | 리스크 식별자 |
| title | str | 리스크 제목 |
| level | str | 위험도(FE `riskLevelLabels` 매핑 대상) |
| description | str | 설명 |

`ResearchSummaryResponse`:

| 필드 | 타입 | 변경 | 비고 |
| --- | --- | --- | --- |
| asset_id | int | 유지 | |
| stance | str | 추가 | 투자 견해 라벨 |
| stance_confidence | str | 추가 | decimal 문자열(FE `parseDecimal`) |
| headline | str | 추가 | |
| body | str | 추가 | |
| key_risks | list[ResearchRisk] | 추가 | |
| created_at | UtcDatetime | 추가 | |
| ~~positive_factors~~ | | 제거 | FE 미사용 |
| ~~negative_factors~~ | | 제거 | FE 미사용 |
| ~~items_to_verify~~ | | 제거 | FE 미사용 |
| ~~sources~~ | | 제거 | FE 미사용, `ResearchSummarySource`도 제거 |
| ~~updated_at~~ | | 제거 | `created_at`으로 대체 |

`ResearchSummarySource`는 소비처가 사라지므로 제거한다. `tests/test_api_contract.py`의
`RESEARCH_SUMMARY_SOURCE_CONTRACT`·openapi 컴포넌트 단언에서 `ResearchSummarySource`를 함께
정리한다.

### 4.3 BuyChecklist item (#2)

`app/domains/decision_checklist/schema.py` — `BuyChecklistItem`:

| 필드 | 타입 | 변경 | 비고 |
| --- | --- | --- | --- |
| id | str | 추가(기존 `key` 매핑) | 값은 기존 `ChecklistItemKey` 문자열 |
| label | str | 유지 | |
| description | str \| None | 추가(기존 `detail` 매핑) | |
| checked | bool | 추가(기존 `status` 매핑) | `status == "checked"` |
| ~~key~~ | | 제거 | `id`로 대체 |
| ~~status~~ | | 제거 | `checked`로 대체 |
| ~~detail~~ | | 제거 | `description`으로 대체 |

`BuyChecklistResponse`의 상위 필드(`asset_id`, `items`, `memo`, `checked_item_keys`,
`is_complete`, `decided_at`)는 유지한다. 쓰기 경로 `BuyChecklistNoteUpdate.checked_item_keys`는
기존 `ChecklistItemKey` 문자열을 계속 사용한다(FE가 `item.id`로 동일 문자열을 전송). `_REQUIRED_KEYS`·
`_ITEM_LABELS`·`_detail_for` 내부 로직은 유지하고, 응답 조립 시점에만 신규 필드로 매핑한다.

### 4.4 AssetDetailResponse (#3)

`app/domains/assets/schema.py` — `AssetDetailResponse`:

| 필드 | 타입 | 변경 | 비고 |
| --- | --- | --- | --- |
| market_cap | str \| None | 추가 | quote 파생 |
| next_earnings_date | str \| None | 추가 | quote 파생(ISO date) |
| updated_at | UtcDatetime | 추가(기존 `as_of` 대체) | 필드명 정렬 |
| ~~as_of~~ | | 제거 | `updated_at`으로 대체 |

기타 기존 필드(`price`·`per`·`peg`·`52w`·`target_*`·`sector` 등)는 유지한다. `market_cap`·
`next_earnings_date`는 `QuoteResult`에서 파생하므로 §4.8을 함께 적용한다.

### 4.5 ResearchReportResponse (#4)

`app/domains/reports/schema.py` — `ResearchReportResponse`:

| 필드 | 타입 | 변경 | 비고 |
| --- | --- | --- | --- |
| title | str | 추가 | `summary` 파생(예: 앞부분 요약/절단) |
| source | str \| None | 추가 | 본 단계 mock/`None` 허용 |

기존 필드는 유지한다. `title`은 컬럼 미도입 원칙에 따라 `summary`에서 파생한다. FE `ReportDto.title`은
required이므로 항상 비어있지 않은 문자열을 보장한다.

### 4.6 ThesisResponse (#6)

`app/domains/theses/schema.py` — `ThesisResponse`:

| 필드 | 타입 | 변경 | 비고 |
| --- | --- | --- | --- |
| title | str | 추가 | `summary` 파생 |

기존 필드는 유지한다.

### 4.7 AlertResponse (#7) · AssetResponse (#8)

`app/domains/alerts/schema.py` — `AlertResponse`에 `title: str | None` 추가. 기존 서비스가
파생하는 `symbol`·`alert_type`·`message`를 조합해 `title`을 생성한다.

`app/domains/assets/schema.py` — `AssetResponse`에 `sector: str | None` 추가. `Asset.sector`
컬럼이 이미 존재하므로 `from_attributes`로 노출만 추가한다.

### 4.8 QuoteResult (#3 지원)

`app/adapters/market/base.py` — `QuoteResult`:

| 필드 | 타입 | 변경 | 비고 |
| --- | --- | --- | --- |
| market_cap | Decimal \| None | 추가 | |
| next_earnings_date | str \| None | 추가 | ISO date 문자열 |

`app/adapters/market/mock.py` — 위 두 필드에 결정적 mock 값을 추가한다.

## 5. 서비스 영향

응답 조립부만 조정하며 도메인 규칙은 변경하지 않는다.

- `ResearchSummaryService.get_summary` — mock 템플릿을 정성 형태(stance/headline/body/key_risks)로
  재작성. `asset.id` 기반 결정적 선택은 유지해 테스트 안정성을 확보한다.
- `DecisionChecklistService._build_response` — item 조립 시 `id`=key, `description`=detail,
  `checked`=(status=="checked") 매핑.
- `AssetService.get_detail` — `updated_at`=quote.as_of, `market_cap`·`next_earnings_date`를
  quote에서 매핑.
- `AssetService.get`·`list` — `AssetResponse`에 `sector` 자동 노출(model_validate).
- reports·theses 서비스 — 응답 조립 시 `title`(·`source`) 파생.
- alerts 서비스 — 응답 조립 시 `title` 파생.
- users `/auth/me` — `username` 파생 매핑.

## 6. 테스트

`tests/test_api_contract.py` 갱신:

- `RESEARCH_SUMMARY_CONTRACT` — 정성 필드 집합으로 교체, `key_risks` 항목 계약(`ResearchRisk`) 추가.
- `RESEARCH_SUMMARY_SOURCE_CONTRACT` — 제거.
- `ASSET_DETAIL_CONTRACT` — `as_of`→`updated_at`, `market_cap`·`next_earnings_date` 추가.
- openapi 컴포넌트 단언 — `ResearchSummarySource` 제거, 필요 시 `ResearchRisk` 추가.
- 신규/보강: `/auth/me`(`username`·`created_at`), `/reports`(`title`), `/theses/latest`(`title`),
  `/alerts`(`title`), `/assets`(`sector`), `/assets/{id}/buy-checklist`(item 신규 shape) 계약 단언.
- 기존 `test_research_summary_response_contract`의 factor-list 단언 제거.

도메인 테스트(`tests/test_auth.py` 등)에서 응답 필드 변경으로 깨지는 단언이 있으면 함께 정렬한다.

## 7. 의존성 / 변경 파일

- `app/domains/users/schema.py`, `app/api/v1/endpoints/auth.py`(또는 users 서비스)
- `app/domains/research_summary/schema.py`, `.../service.py`
- `app/domains/decision_checklist/schema.py`, `.../service.py`
- `app/domains/assets/schema.py`, `.../service.py`
- `app/domains/reports/schema.py`, 해당 서비스
- `app/domains/theses/schema.py`, 해당 서비스
- `app/domains/alerts/schema.py`, 해당 서비스
- `app/adapters/market/base.py`, `app/adapters/market/mock.py`
- `tests/test_api_contract.py`
- `docs/api/frontend-api-spec.md`, `docs/api/contract-alignment.md`

## 8. ADR / 실패 기록 판단

- ADR: 불필요. 기존 계약 스냅샷 테스트(설계 041)·envelope 규약을 따르는 필드 정렬이며 아키텍처
  결정 변경이 없다. 다만 "정성 스키마를 FE 선반영 형태로 채택"·"파생값으로 계약 정렬(컬럼 미도입)"은
  본 설계 문서에 결정으로 기록한다.
- 실패 기록: 불필요.

## 9. 비범위 / 후속

- FE #101 — BE 머지 후 adapter fallback 제거·검증, `contract-alignment.md` FE 측 갱신.
- 실데이터 컬럼 도입(`username`, report `title`/`source` 등) — 실제 입력·수집 파이프라인이 생기는
  시점의 후속 도메인 작업.
- research-summary·buy-checklist 실제 AI/데이터 연동 — 형태 정렬 후 별도 마일스톤.
