# 068 · LLM 데이터 파이프라인 2단계 — Raw 저장 구조 보강 (processing_status)

Status: Draft
작성: Claude Code (orchestrator)
관련: Epic BE #174(LLM 사전 데이터 수집·가공 파이프라인 v0.1), 구현 이슈 BE #179,
Milestone 데이터 수집 파이프라인 — 백엔드(#5). 기준 문서 `docs/knowledge/llm-data-pipeline.md`
(6.2·11절 2단계). 1단계 설계 `docs/designs/067-llm-data-contracts.md`(계약 정의).

## 1. 배경

1단계는 수집 경계 projection `RawProviderResponse`와 `ProcessingStatus` enum
(`app/domains/ingestion/schema.py`)을 **정의만** 했다. 실제 원본 저장 테이블
(`raw_prices`·`raw_news_events`)에는 아직 가공 진행 상태를 표현할 자리가 없다. 2단계는 이
enum을 두 원본 테이블에 반영해, 각 원본 행이 이후 정규화·검증 파이프라인에서 어느 단계까지
처리됐는지를 나타내게 한다.

지침 6.2는 원본 행이 `fetched → normalized → failed` 상태를 가져 재처리·역추적이 가능해야
한다고 요구한다. 본 단계는 그 **상태 컬럼과 저장 구조**만 세운다. 상태를 실제로 전이시키는
로직(정규화 성공 시 `normalized`, 검증 실패 시 `failed`)은 3·4단계 몫이다.

## 2. 범위

포함:

- `raw_prices`·`raw_news_events` 모델에 `processing_status` 컬럼 신설(기본 `fetched`).
- 두 컬럼 추가 + 기존 행 `fetched` backfill 마이그레이션(단일 revision).
- 1단계 `ingestion.schema.ProcessingStatus` enum 재사용(병렬 enum 신설 금지).
- 가공 대기 행 질의를 위한 인덱스.
- 컬럼 기본값·backfill·enum 정합 회귀 테스트.

비포함(후속 단계):

- 상태 전이 로직(`normalized`/`failed` 세팅) — 3단계 Normalizer·4단계 Validator.
- 상태별 조회 repository 메서드·재처리 잡 — 3단계에서 소비처와 함께 정의.
- 통합 원본 테이블 신설 — 1단계 Decision A 유지, 미신설.
- Normalizer·Validator·Feature·ContextBuilder·Gateway 로직, route 노출.

## 3. 컬럼 설계

두 테이블에 동일 형태로 추가한다. enum 값은 프로젝트 관례(`decision_logs`가 enum `.value`를
문자열로 저장)를 따라 문자열로 저장하고, DB 네이티브 enum 타입은 쓰지 않는다.

| 컬럼 | 타입 | 제약/기본 | 설명 |
| --- | --- | --- | --- |
| processing_status | String(20) | `server_default="fetched"`, NOT NULL, indexed | `ProcessingStatus` 값 저장 |

- 값 출처: `app/domains/ingestion/schema.ProcessingStatus`(`fetched`/`normalized`/`failed`/
  `skipped_duplicate`). 신규 enum을 만들지 않고 이 enum을 재사용한다.
- `server_default="fetched"`로 두어 기존 행이 마이그레이션 시 자동 backfill 되고, 신규
  insert도 값 미지정 시 `fetched`가 된다. 수집 서비스(`save_raw`)는 현재 값을 넘기지 않으므로
  로직 변경 없이 기본값이 적용된다.
- 인덱스: 3단계 이후 "가공 대기(`fetched`) 행" 질의를 대비해 각 테이블에 단일 컬럼 인덱스를
  둔다(`ix_raw_prices_processing_status`, `ix_raw_news_events_processing_status`).

## 4. Decisions

- **E. skipped_duplicate는 영속 행 상태가 아니다**: dedup 검출 시 `save_raw`가 `None`을
  반환하고 행을 저장하지 않는다(`raw_prices/service.py`, `raw_news` 동일). 따라서 컬럼에 실제로
  저장되는 값은 `fetched`/`normalized`/`failed`뿐이다. `skipped_duplicate`는 enum에는 유지하되
  수집 결과 텔레메트리·`RawProviderResponse` projection 반환값 의미로만 쓰고, 행 상태 컬럼의
  기대 도메인에서는 제외한다. 이 때문에 DB CHECK 제약으로 값을 강제하지 않는다(문자열 저장 +
  애플리케이션 계층 정합).
- **F. 상태 전이 배선은 2단계 범위 밖**: insert 시 `fetched` 기본값까지만 세운다.
  `normalized`(정규화 성공)·`failed`(검증 실패) 전이는 소비처인 3단계 Normalizer·4단계
  Validator가 담당한다. 2단계에서 서비스·잡 로직에 상태 전이를 넣지 않는다.
- **G. 두 테이블 개별 컬럼, 통합 미이행**: 1단계 Decision A대로 통합 원본 테이블을 만들지
  않으므로, 상태 컬럼도 두 테이블에 각각 추가한다. 수집 데이터가 확정돼 공통 테이블로 합칠 때
  이 컬럼도 함께 이관한다.

## 5. 테스트

- 신규 `RawPrice`·`RawNewsEvent` 저장 시 `processing_status`가 `fetched`로 채워진다(서비스
  경유 insert에서 기본값 확인).
- 마이그레이션 up 후 기존(=컬럼 없던) 행이 `fetched`로 backfill 된다(회귀). down이 컬럼·인덱스를
  깨지 않고 되돌린다.
- `processing_status`에 `normalized`/`failed`를 명시 저장·조회할 수 있다(상태 표현 가능성 확인,
  전이 로직 아님).
- CI 3종(ruff + mypy + pytest) 통과. 신규 컬럼 타입 주석 완전화(mypy).

## 6. ADR 판단

불필요. 기존 테이블에 상태 컬럼 하나를 추가하는 통상 마이그레이션이며, 1단계에서 합의한 enum·
분리 원칙(#175/#176)을 따르는 연장선이다. Decision E(`skipped_duplicate` 비영속)와 인덱스 정책은
설계 리뷰에서 이견이 있으면 조정하되 ADR 승격 대상은 아니다.
