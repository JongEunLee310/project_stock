# BE 설계: 에이전트 3 — 투자 가설 감시 — #465

상태: **설계 초안(Draft)** — 2026-10-13. 결정은 ADR-020(고정 워크플로)과 ADR-021(사용자별 결과 저장, 규칙
없는 `AlertEvent`)을 따른다. 하위 이슈 #485(3-1), #486(3-2), #487(3-3), FE #309.

이 문서는 판단 기록의 가설을 새 근거와 대조하는 에이전트의 대상, 근거 조립, LLM 계약, 저장, 알림, 노트,
실행 경로를 스켈레톤 수준으로 확정한다. 구현 코드와 쿼리는 담지 않는다. 출처가 없는 경계값은 "가정"으로
표기했다.

## 사용자 결정(2026-10-13)

| 항목 | 결정 |
|---|---|
| 감시 대상 | 판단 기록(`decision_logs`)만. 기존 `investment_theses`는 다루지 않음 |
| 허용 범위 | 알림과 노트만. 판단 기록(상태·근거·리스크·트리거)은 바꾸지 않음 |
| 실행 시점 | 일일 브리프 직후(같은 job에서 이어서) |
| 알림 경로 | 사용자별 `AlertEvent`(ADR-021) |

## 1. 코드·데이터 사실

| 사실 | 출처 | 설계 영향 |
|---|---|---|
| 판단 기록은 `user_id`, `target_type`, `target_id`, `symbol`, `decision_type`, `status`, `thesis`, `rationale`, `confidence_level`을 가진다 | `app/domains/decision_logs/model.py:15-55` | 감시 입력 |
| 리스크는 `decision_risks`(`risk_type`, `description`, `severity`)에 있다 | 같은 파일 `DecisionRisk` | 감시 입력 |
| 재검토 트리거 서비스는 `symbol`로 종목을 찾는다(`asset_repo.list_all(symbol=...)`) | `app/domains/decision_logs/review_trigger_service.py:93-95` | 같은 방식으로 종목 해석 |
| 판단 기록 작성 보조는 `DecisionAssistSnapshot`(`free_text_fields=("thesis","rationale","memo")`, AGGREGATED)을 쓴다 | `app/adapters/llm/privacy.py:58-60` | 같은 마스킹 방식 |
| 게이트웨이가 `PrivacyGate.mask`로 `free_text_fields`를 마스킹한다 | `app/adapters/llm/gateway.py:105-110` | projection 선언만으로 마스킹 |
| `AlertEvent`는 사용자별이고 `rule_id`가 필수다. 생성 선례는 `alert_engine` | `app/domains/alert_events/model.py`, `app/domains/alert_engine/service.py:109-140` | ADR-021 §2 확장 |
| FE 알림 화면은 `/alert-events`를 표시하고 `ruleId`를 "규칙 #N"으로 그린다 | FE `features/alerts/dto.ts:111-123`, `widgets/alert-detail/AlertDetail.tsx:256` | FE 후속 필요 |
| 일일 브리프는 종목·날짜당 하나(`DAILY_BRIEF`), 공시 분석은 `FILING_ANALYSIS`이고 브리프의 `filing_analyses`로 연결된다 | 설계 459, 464 | 근거 출처 |
| 실 DB의 판단 기록은 0건(2026-10-13) | 리뷰어 확인 | 실측은 예시 데이터로 |

## 2. 데이터 모델(#485)

### 2.1 `thesis_checks`(`app/domains/agents/thesis_watch/model.py`)

| 필드 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `id` | int | PK | |
| `user_id` | int | FK `users.id`, not null | 판단 기록 소유자 |
| `decision_id` | int | FK `decision_logs.id`, not null | |
| `asset_id` | int | FK `assets.id`, not null | |
| `check_date` | date | not null | 점검 기준일(KST, 브리프 날짜와 같음) |
| `verdict` | str(20) | not null | `ThesisVerdict` |
| `max_severity` | str(10) | nullable | 흔드는 근거 중 가장 높은 심각도 |
| `content` | JSON | not null | §4.3 `ThesisCheckContent` |
| `created_at` | timestamptz | not null | |

- unique: (`decision_id`, `check_date`). 같은 날 다시 실행하면 건너뛴다.
- 인덱스: (`user_id`, `check_date`)
- repository: `get(decision_id, check_date)`, `create(...)`(commit하지 않음), `list_by_user(user_id, limit)`
- 조회 API는 이번 범위 밖이다(노트와 알림으로 확인).

### 2.2 `alert_events` 확장(ADR-021 §2)

| 변경 | 내용 |
|---|---|
| `rule_id` | nullable로 변경 |
| `source` | str(20), not null, 기본 `RULE`. 값 `RULE`, `AGENT` |

- `AlertEventProjection.rule_id: int | None`, `source` 추가. 기존 규칙 엔진 동작은 바뀌지 않는다.
- 생성 함수 `AlertEventRepository.create_agent_event(user_id, asset_id, symbol, title, message, severity,
  evidence, dedup_key, triggered_at) -> AlertEvent | None` — `APP` 전달 기록 1건을 함께 만들고, (`user_id`,
  `dedup_key`) 중복이면 None. `target_type=SYMBOL`, `target_id=symbol`.

### 2.3 enum

| enum | 값 |
|---|---|
| `ThesisVerdict` | `CHALLENGED`(흔드는 근거가 우세), `MIXED`(흔드는 근거와 뒷받침 근거가 함께), `SUPPORTED`, `NO_RELEVANT_EVIDENCE` |
| `FindingRelation` | `CHALLENGES`, `SUPPORTS` |
| `FindingAspect` | `THESIS`, `RATIONALE`, `RISK` |
| `AlertEventSource` | `RULE`, `AGENT` |

## 3. 대상과 근거(#486)

### 3.1 대상

- `status=ACTIVE`, `target_type=SYMBOL`, `symbol`이 있는 판단 기록. `asset_ids`가 주어지면 그 종목들만.
- 종목은 `symbol`로 찾는다(재검토 트리거 서비스와 같은 방식). 찾지 못하면 `skipped_unresolved`.
- `thesis`와 `rationale`이 모두 비어 있으면 `skipped_no_thesis`.

### 3.2 근거

종목·점검일마다 한 번 조립해 그 종목의 판단 기록들이 함께 쓴다.

| 출처 | 내용 | 번호 |
|---|---|---|
| 당일 일일 브리프 | `new_developments`, `changes`, `risk_checks`의 텍스트와 인용된 원문 제목·매체 | `B1`부터 |
| 브리프에 연결된 공시 분석(`filing_analyses`) | 리포트의 `HIGH`·`MEDIUM` 변화 제목과 요약 | `F1`부터 |

- 브리프가 없거나(`no_news`이고 공시 분석도 없음) 근거가 0건이면 LLM을 부르지 않고 `skipped_no_evidence`로
  센다. 저장도 하지 않는다.
- 근거 수 상한 30건(가정). 넘으면 공시 분석, `risk_checks`, `changes`, `new_developments` 순으로 남긴다.

## 4. LLM 계약(#486)

### 4.1 입력 projection `ThesisWatchSnapshot(CloudSafePayload)`

- sensitivity `AGGREGATED`, `free_text_fields = ("thesis", "rationale", "risks")`
  - 리스크 설명은 문자열 목록이므로 마스킹이 목록 원소에 적용되는지 확인하고, 안 되면 한 문자열로 합친다(#486에서 확정).
- 필드: `symbol`, `asset_name`, `decision_type`, `confidence_level`, `decided_days_ago`(판단 시점과의 거리, 날짜
  대신), `thesis`, `rationale`, `risks`(유형·심각도·설명), `evidence`(번호, 출처 종류, 텍스트)
- 사용자 식별자, 판단 기록 id, 보유 정보는 싣지 않는다.

### 4.2 출력 `ThesisCheckResult`

- `verdict: ThesisVerdict`, `headline: str`
- `findings: list[{relation, aspect, summary, severity, citations}]` — `citations` 원소 `^[BF]\d+$`
- `limitations: str | None`

규칙(가정)

- 모든 finding은 근거 번호를 하나 이상 인용한다. 없는 번호는 제거하고, 인용이 남지 않은 finding은 버린다.
- `verdict`는 검증 후 finding으로 다시 계산한다. `CHALLENGES`만 있으면 `CHALLENGED`, 둘 다 있으면 `MIXED`,
  `SUPPORTS`만 있으면 `SUPPORTED`, 없으면 `NO_RELEVANT_EVIDENCE`. LLM이 낸 값과 다르면 보정 수에 센다.
- 매수·매도 권유 금지. 가설이 "틀렸다"고 단정하지 않고 "점검할 근거"로 표현한다.

### 4.3 저장 `ThesisCheckContent`

- 검증된 `headline`, `findings`, `limitations`, `evidence`(번호별 출처: 브리프 리포트 id, 공시 분석 리포트 id,
  원문 제목·URL), `citation_corrections`, `verdict_corrected: bool`
- 사용자 원문(`thesis`·`rationale`)은 저장하지 않는다. 판단 기록에서 다시 읽을 수 있다.

### 4.4 배선

- `LLMTaskType.THESIS_WATCH`, 라우트 `TaskRoute(launch="cloud", future_primary="local")`(가정. 사용자 텍스트를
  다루므로 로컬 이관 우선 후보)
- 프롬프트 `app/adapters/llm/prompts/thesis_watch.py`(`PROMPT_VERSION="v1"`)
- 호출 실패는 그 판단 기록만 `failed`로 기록한다.

## 5. 워크플로와 알림(#486)

`ThesisWatchAgent.run(asset_ids: list[int] | None = None, check_date: date | None = None) -> ThesisWatchResult`

| 단계 | 책임 |
|---|---|
| 1 | 대상 판단 기록 수집(§3.1) |
| 2 | 종목별 근거 조립(§3.2), 이미 점검한 (`decision_id`, `check_date`)는 건너뜀 |
| 3 | 판단 기록마다 LLM 호출, 검증 |
| 4 | `thesis_checks` 저장, 판단 기록 단위 commit |
| 5 | 알림: `verdict`가 `CHALLENGED`·`MIXED`이고 `CHALLENGES` finding 중 `HIGH`가 있으면 `AlertEvent`(source `AGENT`) 1건. dedup `thesis-watch:{decision_id}:{check_date}`. 제목 "{symbol} 판단 기록 점검 필요", 메시지는 헤드라인 |
| 6 | 노트(§6, #487) |

- 결과: `checked`, `skipped_existing`, `skipped_no_evidence`, `skipped_unresolved`, `skipped_no_thesis`, `failed`,
  `llm_calls`, `alerts_created`, `notes_written`, `note_failures`
- 판단 기록 하나의 실패가 다른 기록을 막지 않는다.
- 알림 메시지에는 사용자 가설 원문을 넣지 않는다(헤드라인은 LLM 요약). 알림 자체가 사용자 본인에게만 보인다.

## 6. Obsidian 노트(#487)

- 경로 `stock-agent/theses/{SYMBOL}/{check_date}-decision-{decision_id}.md`. `verdict`가 `NO_RELEVANT_EVIDENCE`이면
  쓰지 않는다.
- frontmatter: `symbol`, `decision_id`, `check_date`, `verdict`, `max_severity`, `tags: [stock-agent, thesis-watch]`
- 본문: 헤드라인, `[[{SYMBOL}]]`, 당일 일일 노트 wikilink, `## 흔드는 근거`, `## 뒷받침하는 근거`(심각도 순, 각주),
  `## 한계`, `## 근거`(각주 정의), 생성 안내("판단 기록은 바꾸지 않았습니다. 매수·매도 권유가 아닙니다.")
- vault는 사용자 로컬이므로 노트에 판단 기록 요약을 담아도 된다. 다만 가설 원문 전체는 싣지 않고 판단 기록
  링크 대신 id만 적는다(앱 링크 형식이 정해지면 바꾼다).

## 7. 실행 경로(#486)

- `run_daily_research_job`이 에이전트 1 실행 뒤 같은 job 안에서 `ThesisWatchAgent.run(asset_ids, check_date=브리프
  날짜)`를 실행한다. 에이전트 1 결과가 실패해도 에이전트 3은 실행한다(브리프가 있는 종목만 근거가 생김).
- job metadata에 `thesis_watch` 결과 요약을 남긴다. timeout은 기존 3600초를 그대로 쓴다.
- 수동 스크립트 `scripts/run_thesis_watch.py --asset-id N --date YYYY-MM-DD`

## 8. 테스트 전략

- 모델: unique, FK, `alert_events` 마이그레이션(기존 행 `source=RULE`, `rule_id` 유지)
- `AlertEvent`: 규칙 엔진 경로 불변, 에이전트 이벤트 생성·중복, 응답 `rule_id` null·`source`
- projection: `free_text_fields`, 마스킹 적용(게이트웨이 경유 시 placeholder), 사용자 식별자 미포함
- 근거 조립: 번호, 상한과 우선순위, 근거 없음 건너뜀
- 검증: 없는 번호, verdict 재계산과 보정 표시
- 워크플로: 대상 필터(ACTIVE·SYMBOL), 종목 해석 실패, 중복 건너뜀, 알림 조건, 판단 기록 불변(실행 전후 비교)
- job 체인: 에이전트 1 실패 시에도 실행, metadata
- 실측(리뷰 단계): 실 DB 복제본에 예시 판단 기록 2~3건(예: NVDA "중국 매출 회복" 가설)을 넣고 실제 LLM으로 확인

## 9. 하위 이슈

| 이슈 | 범위 |
|---|---|
| #485 | `thesis_checks`, `alert_events` 확장(ADR-021), repository(§2) |
| #486 | 근거 조립, LLM 계약, 워크플로, 알림, job 체인, 스크립트(§3·§4·§5·§7) |
| #487 | Obsidian 노트(§6) |
| FE #309 | `AlertEventDto.rule_id` nullable·`source` 반영, 에이전트 출처 표시 |

## 10. Open Questions

| # | 질문 | 처리 |
|---|---|---|
| OQ1 | 마스킹이 목록 필드에 적용되는가 | #486에서 확인 |
| OQ2 | 근거가 헤드라인 수준 뉴스라 판정이 얕을 수 있다 | 실측에서 확인. 공시 분석이 있는 날 품질 비교 |
| OQ3 | 판단 기록이 많은 사용자의 LLM 비용 | 판단 기록당 하루 1회, 근거 있는 날만. 상한은 실사용 후 |

## 11. 범위 밖

- 판단 기록 상태 전이, 근거·리스크 추가(ADR-021 §3)
- 기존 `investment_theses`와 `ThesisConflictRule`
- 점검 결과 조회 API와 FE 화면(알림 표시 보정 외)
